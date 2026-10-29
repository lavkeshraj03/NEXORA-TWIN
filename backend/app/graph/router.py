from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.businesses import access
from app.core.exporting import csv_bytes
from app.core.security import current_user,rate_limit
from app.db.session import get_session
from app.graph.models import GraphBuild
from app.graph.service import build,load,summary,node_out,edge_out
from app.models import User

router=APIRouter(prefix="/businesses/{business_id}/knowledge-graph",tags=["Knowledge graph"])


@router.post("/refresh")
def refresh(business_id:UUID,user:User=Depends(current_user),db:Session=Depends(get_session)):
    access(db,user,business_id,"graph:build")
    rate_limit(f"graph-refresh:{business_id}:{user.id}",10,3600)
    row,unchanged=build(db,business_id,user)
    row,nodes,edges=load(db,business_id,user,row.id)
    return summary(row,nodes,edges)|{"unchanged":unchanged}


@router.get("")
def overview(business_id:UUID,build_id:UUID|None=None,user:User=Depends(current_user),db:Session=Depends(get_session)):
    return summary(*load(db,business_id,user,build_id))


@router.get("/builds")
def history(business_id:UUID,user:User=Depends(current_user),db:Session=Depends(get_session)):
    access(db,user,business_id,"graph:read")
    rows=db.scalars(select(GraphBuild).where(GraphBuild.business_id==business_id).order_by(GraphBuild.created_at.desc(),GraphBuild.id.desc()).limit(5))
    return [{"id":str(row.id),"created_at":row.created_at.isoformat()} for row in rows]


@router.get("/nodes")
def nodes(business_id:UUID,build_id:UUID|None=None,kind:str|None=Query(None,max_length=24),search:str=Query("",max_length=160),limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0,le=11000),user:User=Depends(current_user),db:Session=Depends(get_session)):
    row,items,_=load(db,business_id,user,build_id)
    matching=[node for node in items if (not kind or node.kind==kind) and (not search or search.casefold() in node.label.casefold() or search.casefold() in node.source_key.casefold())]
    return {"build_id":str(row.id) if row else None,"items":[node_out(node) for node in matching[offset:offset+limit]],"total":len(matching),"limit":limit,"offset":offset}


@router.get("/nodes/{node_id}")
def neighborhood(business_id:UUID,node_id:UUID,build_id:UUID,relationship:str|None=Query(None,max_length=40),limit:int=Query(12,ge=1,le=50),offset:int=Query(0,ge=0,le=30000),user:User=Depends(current_user),db:Session=Depends(get_session)):
    row,nodes,edges=load(db,business_id,user,build_id)
    lookup={node.id:node for node in nodes};selected=lookup.get(node_id)
    if selected is None:raise HTTPException(404,"Graph node not found")
    incident=[edge for edge in edges if (edge.source_id==node_id or edge.target_id==node_id) and (not relationship or edge.relationship==relationship)]
    priority={"supplies":0,"has_balance":1,"contains":2,"places":3,"has_movement":4}
    incident.sort(key=lambda edge:(priority.get(edge.relationship,5),str(edge.id)))
    page=incident[offset:offset+limit]
    connected={edge.source_id for edge in page}|{edge.target_id for edge in page}
    connected.discard(node_id)
    return {"build_id":str(row.id),"node":node_out(selected,True),"neighbors":[node_out(lookup[key]) for key in sorted(connected,key=str)],"edges":[edge_out(edge) for edge in page],"total_connections":len(incident),"limit":limit,"offset":offset,"definition":"A bounded neighborhood of captured, source-backed relationships. Document visibility is checked at read time."}


@router.get("/export")
def export(business_id:UUID,build_id:UUID|None=None,user:User=Depends(current_user),db:Session=Depends(get_session)):
    row,nodes,edges=load(db,business_id,user,build_id)
    if row is None:raise HTTPException(404,"Refresh the knowledge graph first")
    rows=[["NEXORA TWIN relationship snapshot",row.manifest["captured_at"]],["methodology",row.manifest["methodology"]],["record_type","id","kind_or_relationship","label","from","to","source_resource","source_id","source_sha256"]]
    for node in nodes:rows.append(["node",node.id,node.kind,node.label,"","",node.source["resource"],node.source["id"],node.source["sha256"]])
    for edge in edges:rows.append(["edge",edge.id,edge.relationship,"",edge.source_id,edge.target_id,edge.provenance["resource"],edge.provenance["id"],edge.provenance["sha256"]])
    return Response(csv_bytes(rows),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="knowledge-graph-{row.id}.csv"',"Cache-Control":"no-store"})
