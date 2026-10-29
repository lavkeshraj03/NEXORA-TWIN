import os
from datetime import date
from uuid import UUID,uuid4
import io

import pytest
from pypdf import PdfReader
from sqlalchemy import select,update,func
from sqlalchemy.exc import DBAPIError,IntegrityError
from sqlalchemy.orm import Session

from app.documents import pipeline
from app.documents.models import Document
from app.graph.models import KnowledgeNode,KnowledgeEdge,GraphBuild
from app.reports.models import GeneratedReport
from test_identity_integration import accounts,create
from test_operations_integration import seed,add,order
from test_twin_integration import save
from test_documents_integration import processing,upload
from test_analyst_integration import model,ask
from test_simulation_integration import simulate

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv("RUN_INTEGRATION")!="1",reason="Requires migrated PostgreSQL/Redis")]


def prepare(owner,headers):
    business=create(owner,headers);path=f"/api/v1/businesses/{business['id']}"
    seed(owner,headers,path);add(owner,headers,path,"orders",[order()])
    return path


def graph(owner,headers,path):
    response=owner.post(path+"/knowledge-graph/refresh",headers=headers)
    assert response.status_code==200,response.text
    return response.json()


def report(owner,headers,path,kind="revenue_expenses",**fields):
    response=owner.post(path+"/reports",headers=headers,json={"name":"Demo report","kind":kind}|fields)
    assert response.status_code==201,response.text
    return response.json()


def test_graph_real_relationships_provenance_pagination_idempotence_and_old_state(accounts):
    owner,_,headers,_,_,_,_=accounts
    path=prepare(owner,headers)
    first=graph(owner,headers,path)
    assert first["node_count"]>5 and first["edge_count"]>first["node_count"]
    assert first["demo_nodes"]>0 and first["unchanged"] is False
    again=graph(owner,headers,path)
    assert again["build"]["id"]==first["build"]["id"] and again["unchanged"] is True
    product=owner.get(path+"/knowledge-graph/nodes?kind=product&search=P1").json()["items"][0]
    route=path+f"/knowledge-graph/nodes/{product['id']}?build_id={first['build']['id']}"
    neighborhood=owner.get(route).json()
    relations={edge["relationship"] for edge in neighborhood["edges"]}
    assert {"contains","supplies","has_movement","has_balance"}<=relations
    assert neighborhood["node"]["source"]["values"]["sku"]=="P1"
    assert owner.get(route+"&limit=1").json()["total_connections"]==neighborhood["total_connections"]
    assert len(owner.get(route+"&limit=1").json()["edges"])==1
    assert owner.get(path+"/knowledge-graph/export").status_code==200
    add(owner,headers,path,"customers",[{"external_id":"C2","name":"Next recorded customer"}])
    changed=graph(owner,headers,path)
    assert changed["build"]["id"]!=first["build"]["id"]
    assert changed["node_count"]==first["node_count"]+1
    assert owner.get(path+"/knowledge-graph?build_id="+first["build"]["id"]).json()["node_count"]==first["node_count"]


def test_graph_permissions_live_document_visibility_and_composite_fks(processing):
    account_values,_=processing
    owner,other,headers,other_headers,_,other_account,connection=account_values
    path=prepare(owner,headers)
    public=upload(owner,headers,path,title="Team policy")
    private=upload(owner,headers,path,title="Restricted executive policy",visibility="administrators")
    build=graph(owner,headers,path)
    docs=owner.get(path+"/knowledge-graph/nodes?kind=document").json()["items"]
    assert len(docs)==2
    owner.post(path+"/members",headers=headers,json={"email":other_account["user"]["email"],"role":"viewer"})
    assert other.post(path+"/knowledge-graph/refresh",headers=other_headers).status_code==403
    visible=other.get(path+"/knowledge-graph/nodes?kind=document").json()
    assert visible["total"]==1 and visible["items"][0]["label"]=="Team policy"
    hidden=next(row for row in docs if row["label"]=="Restricted executive policy")
    assert other.get(path+f"/knowledge-graph/nodes/{hidden['id']}?build_id={build['build']['id']}").status_code==404
    assert "Restricted executive policy" not in other.get(path+"/knowledge-graph/export").text
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        db.get(Document,UUID(public["document_id"])).visibility="administrators";db.commit()
    assert other.get(path+"/knowledge-graph/nodes?kind=document").json()["total"]==0
    second=create(owner,headers,name="Other tenant")
    assert owner.get(f"/api/v1/businesses/{second['id']}/knowledge-graph?build_id={build['build']['id']}").status_code==404
    other_build=graph(owner,headers,f"/api/v1/businesses/{second['id']}")
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        original=db.scalar(select(KnowledgeNode).where(KnowledgeNode.build_id==UUID(build["build"]["id"])))
        other_root=db.scalar(select(KnowledgeNode).where(KnowledgeNode.build_id==UUID(other_build["build"]["id"])))
        invalid=KnowledgeEdge(id=uuid4(),business_id=UUID(second["id"]),build_id=other_root.build_id,source_id=original.id,target_id=other_root.id,relationship="invalid",provenance={})
        db.add(invalid)
        with pytest.raises(IntegrityError) as failure:db.flush()
        assert failure.value.orig.diag.constraint_name=="fk_edge_tenant_source"
        db.rollback()
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        with pytest.raises(DBAPIError):db.execute(update(KnowledgeNode).where(KnowledgeNode.id==UUID(hidden["id"])).values(label="Rewrite captured evidence"))
        db.rollback()


def test_financial_and_monthly_reports_are_frozen_with_valid_csv_pdf_and_roles(accounts):
    owner,other,headers,other_headers,_,other_account,connection=accounts
    path=prepare(owner,headers);snapshot=save(owner,headers,path)
    created=report(owner,headers,path,snapshot_id=snapshot["id"])
    assert created["payload"]["metadata"]["result_kind"]=="calculated_historical"
    financial={row[0]:row[1] for row in created["payload"]["sections"][0]["rows"]}
    assert financial["revenue"]=="28.00" and financial["operating_profit"] is None
    route=path+"/reports/"+created["id"]
    pdf=owner.get(route+"/export/pdf")
    assert pdf.status_code==200 and pdf.headers["content-type"]=="application/pdf"
    text="\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "28.00" in text and "Incomplete / undefined" in text
    assert owner.get(route+"/export/csv").text.find(snapshot["content_hash"])>=0
    assert owner.get(route+"/export/html").status_code==422
    assert other.get(route).status_code==404
    separate=create(owner,headers,name="Other report business")
    assert owner.get(f"/api/v1/businesses/{separate['id']}/reports/{created['id']}").status_code==404
    assert owner.post(f"/api/v1/businesses/{separate['id']}/reports",headers=headers,json={"name":"Wrong source","kind":"revenue_expenses","snapshot_id":snapshot["id"]}).status_code==404
    owner.post(path+"/members",headers=headers,json={"email":other_account["user"]["email"],"role":"viewer"})
    assert other.get(route).status_code==404
    assert other.post(path+"/reports",headers=other_headers,json={"name":"Denied","kind":"revenue_expenses","snapshot_id":snapshot["id"]}).status_code==403
    assert owner.post(path+"/reports",headers=headers,json={"name":"Partial month","kind":"monthly","snapshot_id":snapshot["id"]}).status_code==422
    month=save(owner,headers,path,"Closed September",start="2026-09-01",end="2026-09-30")
    assert report(owner,headers,path,"monthly",snapshot_id=month["id"])["payload"]["metadata"]["reporting_period"]["days"]==30
    sale=owner.get(path+"/orders").json()["items"][0]
    owner.patch(path+"/orders/"+sale["id"],headers=headers,json={"status":"refunded","reason":"After report"})
    assert owner.get(route).json()==created
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        with pytest.raises(DBAPIError):db.execute(update(GeneratedReport).where(GeneratedReport.id==UUID(created["id"])).values(payload={"invented":1}))
        db.rollback()


def test_inventory_forecast_and_scenario_reports_use_saved_sources(accounts):
    from test_ml_integration import history,train
    owner,_,headers,_,_,_,_=accounts
    business=create(owner,headers);path=f"/api/v1/businesses/{business['id']}"
    history(owner,headers,path)
    snapshot=save(owner,headers,path)
    risk=report(owner,headers,path,"inventory_risk",snapshot_id=snapshot["id"],lead_days=14,incoming_units="3",safety_units="2")
    assert risk["payload"]["sections"][0]["rows"][0][4]=="3"
    model_run=train(owner,headers,path)
    forecast=report(owner,headers,path,"sales_forecast",model_run_id=model_run["id"],horizon=7)
    assert forecast["payload"]["metadata"]["result_kind"]=="forecast_estimates"
    assert forecast["payload"]["sections"][0]["rows"][0][1]==model_run["result"]["forecast"][0]["prediction"]
    assert owner.get(path+"/ml/runs/"+model_run["id"]).json()["active"] is False
    snapshot=save(owner,headers,path,"Sales history",start="2026-05-01",end="2026-07-19")
    left=simulate(owner,headers,path,snapshot,name="Baseline")
    right=simulate(owner,headers,path,snapshot,name="Assumed demand",demand_change_pct="10")
    comparison=report(owner,headers,path,"scenario_comparison",scenario_run_ids=[left["id"],right["id"]])
    assert comparison["payload"]["metadata"]["result_kind"]=="hypothetical_simulation"
    assert "not actual" in comparison["payload"]["sections"][0]["note"]


def test_investigation_report_keeps_private_document_access_live(processing,model):
    account_values,provider=processing
    owner,other,headers,other_headers,_,other_account,connection=account_values
    path=prepare(owner,headers)
    doc=upload(owner,headers,path,text=b"Returns require the original receipt within thirty days.")
    pipeline.process_version(doc["id"])
    owner.post(path+"/members",headers=headers,json={"email":other_account["user"]["email"],"role":"analyst"})
    model.provider=provider;model.tools=["search_business_documents"]
    investigation=ask(other,other_headers,path,question="What does the returns policy say?")
    saved=report(other,other_headers,path,"investigation",investigation_id=investigation["id"])
    route=path+"/reports/"+saved["id"]
    assert owner.get(route).status_code==404
    assert other.get(route+"/export/pdf").status_code==200
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        db.get(Document,UUID(doc["document_id"])).visibility="administrators";db.commit()
    for suffix in ["","/export/csv","/export/pdf"]:assert other.get(route+suffix).status_code==403


def test_saved_inactivity_report_copies_estimates_and_never_trains(accounts):
    from app.ml.models import ModelRun
    from app.ml.datasets import fingerprint
    owner,_,headers,_,identity,_,connection=accounts
    path=prepare(owner,headers);business_id=UUID(path.rsplit("/",1)[-1])
    # Test-only saved artifact fixture; genuine Nexa classifier verification is live.
    dataset={"start":"2026-06-01","end":"2026-10-28","sources":[]}
    result={"predictions":[{"customer_id":str(uuid4()),"external_id":"C1","estimated_inactivity_probability":0.25}],"evaluation":{"precision":0.5,"observations":1},"baseline":{"precision":0.5,"observations":1},"definition":"Fixture inactivity proxy","limitations":["Test artifact only; not production predictions"]}
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        run=ModelRun(business_id=business_id,created_by=UUID(identity["user"]["id"]),task="churn",data_scope="demo",algorithm="fixture-only",implementation_version="1",dataset=dataset,dataset_hash=fingerprint(dataset),artifact={},config={"end":"2026-10-28","currency":"INR","timezone":"Asia/Kolkata"},result=result)
        db.add(run);db.commit();run_id=str(run.id)
    saved=report(owner,headers,path,"customer_inactivity",model_run_id=run_id)
    assert saved["payload"]["metadata"]["result_kind"]=="inactivity_estimates"
    assert saved["payload"]["sections"][0]["rows"][0][2]==0.25
    assert len(owner.get(path+"/ml/runs").json())==1


def test_graph_and_report_retention_caps_are_atomic(accounts):
    owner,_,headers,_,identity,_,connection=accounts
    path=prepare(owner,headers)
    for index in range(5):
        add(owner,headers,path,"customers",[{"external_id":f"NEW-{index}","name":f"Customer {index}"}])
        graph(owner,headers,path)
    add(owner,headers,path,"customers",[{"external_id":"OVER","name":"Extra source"}])
    assert owner.post(path+"/knowledge-graph/refresh",headers=headers).status_code==422
    assert len(owner.get(path+"/knowledge-graph/builds").json())==5
    snapshot=save(owner,headers,path)
    first=report(owner,headers,path,snapshot_id=snapshot["id"])
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        original=db.get(GeneratedReport,UUID(first["id"]))
        db.add_all([GeneratedReport(business_id=original.business_id,user_id=original.user_id,captured_role=original.captured_role,name=original.name,kind=original.kind,implementation_version=original.implementation_version,payload=original.payload,content_hash=original.content_hash) for _ in range(39)])
        db.commit()
    assert owner.post(path+"/reports",headers=headers,json={"name":"Over cap","kind":"revenue_expenses","snapshot_id":snapshot["id"]}).status_code==422
    assert len(owner.get(path+"/reports").json())==40
