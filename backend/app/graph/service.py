from datetime import datetime,timezone
from uuid import UUID,uuid4,uuid5
from fastapi import HTTPException
from sqlalchemy import select,or_,and_,func
from app.api.businesses import access
from app.data.models import OrderItem,InventoryBalance
from app.data.service import MODELS,json_ready
from app.documents.models import Document
from app.graph.models import GraphBuild,KnowledgeNode,KnowledgeEdge
from app.ml.datasets import fingerprint
from app.models import AuditLog
from app.twin.service import scalar_row

MAX_SOURCES=10000
VERSION="1"


def compile_graph(business,sources,documents,build_id,captured_at):
    nodes,edges=[],[]
    tenant_id=UUID(str(business["id"]))
    def node(resource,row,kind,label):
        ref=str(row.get("id",row.get("product_id")))
        key=f"{resource}:{ref}"
        value={"id":uuid5(build_id,key),"business_id":tenant_id,"build_id":build_id,"kind":kind,"source_key":key,"label":label[:260],"source":{"resource":resource,"id":ref,"values":row,"sha256":fingerprint(row),"captured_at":captured_at,"verification":"structured_record"},"document_id":UUID(row["id"]) if kind=="document" else None,"visibility":row.get("visibility","team")}
        nodes.append(value);return value["id"]
    def edge(a,b,relationship,resource,row):
        key=f"{a}:{relationship}:{b}:{row.get('id',row.get('product_id',''))}"
        edges.append({"id":uuid5(build_id,key),"business_id":tenant_id,"build_id":build_id,"source_id":a,"target_id":b,"relationship":relationship,"provenance":{"resource":resource,"id":str(row.get("id",row.get("product_id",""))),"values":row,"sha256":fingerprint(row),"captured_at":captured_at,"verification":"structured_foreign_key"}})
    root=node("businesses",business,"business",business["name"])
    refs={}
    kinds={"customers":"customer","suppliers":"supplier","products":"product","orders":"order","inventory":"stock_movement","expenses":"expense","balances":"stock_balance"}
    for resource,kind in kinds.items():
        refs[resource]={}
        for row in sources[resource]:
            key=str(row.get("id",row.get("product_id")))
            reference=row.get("external_id",row.get("sku",key))
            label=f"{reference} · {row.get('name',kind.replace('_',' '))}"
            target=node(resource,row,kind,label);refs[resource][key]=target
            edge(root,target,"has_"+kind,resource,row)
    for row in sources["orders"]:
        edge(refs["customers"][row["customer_id"]],refs["orders"][row["id"]],"places","orders",row)
    for row in sources["order_items"]:
        edge(refs["orders"][row["order_id"]],refs["products"][row["product_id"]],"contains","order_items",row)
    for row in sources["products"]:
        if row.get("supplier_id"):edge(refs["suppliers"][row["supplier_id"]],refs["products"][row["id"]],"supplies","products",row)
    for row in sources["inventory"]:
        edge(refs["products"][row["product_id"]],refs["inventory"][row["id"]],"has_movement","inventory",row)
    for row in sources["balances"]:
        edge(refs["products"][row["product_id"]],refs["balances"][row["product_id"]],"has_balance","balances",row)
    for row in documents:
        target=node("documents",row,"document",row["title"])
        edge(root,target,"has_document","documents",row)
    return nodes,edges


def build(db,business_id,user):
    business,_=access(db,user,business_id,"graph:build",lock=True)
    remaining=MAX_SOURCES;sources={}
    for resource,model in dict(MODELS,order_items=OrderItem,balances=InventoryBalance).items():
        rows=db.scalars(select(model).where(model.business_id==business_id).order_by(*model.__table__.primary_key.columns).limit(remaining+1)).all()
        if len(rows)>remaining:raise HTTPException(422,f"Graph snapshots support at most {MAX_SOURCES} operational source records")
        remaining-=len(rows);sources[resource]=[scalar_row(row) for row in rows]
    docs=db.scalars(select(Document).where(Document.business_id==business_id).order_by(Document.id).limit(101)).all()
    if len(docs)>100:raise HTTPException(422,"Graph snapshots support at most 100 document metadata records")
    documents=[json_ready({"id":row.id,"business_id":row.business_id,"title":row.title,"visibility":row.visibility,"active_version":row.active_version}) for row in docs]
    identity=json_ready({"id":business.id,"name":business.name,"business_type":business.business_type,"currency":business.currency,"timezone":business.timezone})
    source_hash=fingerprint({"business":identity,"sources":sources,"documents":documents})
    previous=db.scalar(select(GraphBuild).where(GraphBuild.business_id==business_id).order_by(GraphBuild.created_at.desc(),GraphBuild.id.desc()).limit(1))
    if previous and previous.source_hash==source_hash:return previous,True
    if db.scalar(select(func.count()).select_from(GraphBuild).where(GraphBuild.business_id==business_id))>=5:raise HTTPException(422,"This release retains at most five graph snapshots per business")
    build_id=uuid4();captured_at=datetime.now(timezone.utc).isoformat()
    nodes,edges=compile_graph(identity,sources,documents,build_id,captured_at)
    manifest={"captured_at":captured_at,"operational_sources":{key:{"records":len(rows),"sha256":fingerprint(rows)} for key,rows in sources.items()},"node_count":len(nodes),"edge_count":len(edges),"methodology":"Only stored foreign keys and business ownership. No inferred campaign influence, causal relationships or LLM extraction."}
    row=GraphBuild(id=build_id,business_id=business_id,created_by=user.id,implementation_version=VERSION,source_hash=source_hash,manifest=manifest,created_at=datetime.fromisoformat(captured_at))
    db.add(row);db.flush()
    db.add_all([KnowledgeNode(**node) for node in nodes]);db.flush()
    db.add_all([KnowledgeEdge(**edge) for edge in edges])
    db.add(AuditLog(business_id=business_id,user_id=user.id,event="graph.refreshed",target_id=str(row.id)))
    db.commit();return row,False


def load(db,business_id,user,build_id=None):
    _,member=access(db,user,business_id,"graph:read")
    query=select(GraphBuild).where(GraphBuild.business_id==business_id)
    query=query.where(GraphBuild.id==build_id) if build_id else query.order_by(GraphBuild.created_at.desc(),GraphBuild.id.desc()).limit(1)
    row=db.scalar(query)
    if row is None:
        if build_id:raise HTTPException(404,"Graph snapshot not found")
        return None,[],[]
    if row.implementation_version!=VERSION:raise HTTPException(409,"Unsupported graph implementation version")
    docs=select(Document.id).where(Document.business_id==business_id)
    conditions=[KnowledgeNode.business_id==business_id,KnowledgeNode.build_id==row.id]
    if member.role in {"owner","administrator"}:
        conditions.append(or_(KnowledgeNode.document_id.is_(None),KnowledgeNode.document_id.in_(docs)))
    else:
        docs=docs.where(Document.visibility=="team")
        conditions.append(or_(KnowledgeNode.document_id.is_(None),and_(KnowledgeNode.visibility=="team",KnowledgeNode.document_id.in_(docs))))
    nodes=db.scalars(select(KnowledgeNode).where(*conditions).order_by(KnowledgeNode.kind,KnowledgeNode.label,KnowledgeNode.id)).all()
    ids=[node.id for node in nodes]
    edges=db.scalars(select(KnowledgeEdge).where(KnowledgeEdge.business_id==business_id,KnowledgeEdge.build_id==row.id,KnowledgeEdge.source_id.in_(ids),KnowledgeEdge.target_id.in_(ids)).order_by(KnowledgeEdge.id)).all()
    return row,nodes,edges


def node_out(node,detail=False):
    output={"id":str(node.id),"kind":node.kind,"label":node.label,"source_key":node.source_key,"is_demo":bool(node.source["values"].get("is_demo"))}
    if detail:output["source"]=node.source
    return output


def edge_out(edge):
    return {"id":str(edge.id),"source_id":str(edge.source_id),"target_id":str(edge.target_id),"relationship":edge.relationship,"provenance":edge.provenance}


def summary(row,nodes,edges):
    if row is None:return {"build":None,"node_count":0,"edge_count":0,"kinds":{}}
    kinds={}
    for node in nodes:kinds[node.kind]=kinds.get(node.kind,0)+1
    return {"build":{"id":str(row.id),"created_at":row.created_at.isoformat(),"captured_at":row.manifest["captured_at"],"implementation_version":row.implementation_version},"node_count":len(nodes),"edge_count":len(edges),"kinds":kinds,"demo_nodes":sum(bool(node.source["values"].get("is_demo")) for node in nodes),"view_hash":fingerprint({"nodes":[str(node.id)+node.source["sha256"] for node in nodes],"edges":[str(edge.id)+edge.provenance["sha256"] for edge in edges]}),"methodology":row.manifest["methodology"]}
