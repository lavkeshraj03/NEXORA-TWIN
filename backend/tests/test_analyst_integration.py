import os
from types import SimpleNamespace
from uuid import UUID,uuid4

import pytest
from redis import Redis
from sqlalchemy import select,update,func
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.analyst.models import Investigation
from app.analyst.schemas import Plan,Selection
from app.core.config import get_settings
from app.core.security import token_digest
from app.documents.models import Document
from app.documents.provider import ProviderError
from app.ml.models import ModelRun
from test_identity_integration import accounts,create
from test_operations_integration import add,order,seed
from test_documents_integration import processing,upload
from app.documents import pipeline

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv("RUN_INTEGRATION")!="1",reason="Requires migrated PostgreSQL/Redis")]
PERIOD={"start":"2026-10-01","end":"2026-10-28"}


class FixtureModel:
    chat_model="fixture-only-analyst"
    usage=[]
    tools=["query_sales","query_expenses","query_inventory"]
    on_plan=None
    def budget(self,deadline):pass
    def plan(self,*args):
        if self.on_plan:self.on_plan()
        return Plan(tools=self.tools)
    def select(self,question,facts,recommendations,deadline):
        selected=[fact["id"] for fact in facts if fact["kind"]=="document_excerpt"] if "policy" in question.lower() else [fact["id"] for fact in facts[:6]]
        return Selection(supported=bool(selected),finding_ids=selected,recommendation_ids=[])


@pytest.fixture
def model(monkeypatch):
    instance=FixtureModel()
    monkeypatch.setattr("app.analyst.service.get_model",lambda:instance)
    return instance


def prepare(owner,headers):
    business=create(owner,headers)
    path=f"/api/v1/businesses/{business['id']}"
    seed(owner,headers,path)
    add(owner,headers,path,"orders",[order()])
    add(owner,headers,path,"expenses",[{"external_id":"E1","incurred_on":"2026-10-10","category":"rent","amount":"5.50","is_demo":True}])
    assert owner.put(path+"/expense-coverage",headers=headers,json={"start_date":PERIOD["start"],"end_date":PERIOD["end"],"complete":True}).status_code==200
    return path


def ask(owner,headers,path,expected=201,**changes):
    response=owner.post(path+"/analyst/investigations",headers=headers,json=PERIOD|{"question":"Why did recorded profit change?"}|changes)
    assert response.status_code==expected,response.text
    return response.json()


def test_calculated_evidence_trace_frozen_inputs_exports_and_no_business_writes(accounts,model):
    owner,_,headers,_,_,_,_=accounts
    path=prepare(owner,headers)
    before=owner.get(path+"/dashboard?start=2026-10-01&end=2026-10-28").json()
    result=ask(owner,headers,path)
    assert result["status"]=="completed" and "28.00" in result["response"]["answer"] and "10.50" in result["response"]["answer"]
    assert len(result["executions"])==4 and all(row["status"]=="completed" for row in result["executions"])
    assert all(row["id"].startswith("E") and row["permission"] for row in result["executions"])
    assert "does not establish a business cause" in result["response"]["answer"]
    assert "gross profit by 16.00" in result["response"]["answer"]
    after=owner.get(path+"/dashboard?start=2026-10-01&end=2026-10-28").json()
    assert before["metrics"]==after["metrics"] and before["counts"]==after["counts"] and before["data_updated_at"]==after["data_updated_at"]
    route=path+"/analyst/investigations/"+result["id"]
    saved=owner.get(route).json()
    assert owner.get(route+"/sources?resource=order_items").json()["total"]==1
    assert owner.get(route+"/sources?resource=password_hash").status_code==422
    exported=owner.get(route+"/export")
    assert exported.status_code==200 and "attachment" in exported.headers["content-disposition"] and result["input_hash"] in exported.text
    sale=owner.get(path+"/orders").json()["items"][0]
    owner.patch(path+"/orders/"+sale["id"],headers=headers,json={"status":"refunded","reason":"After analyst capture"})
    assert owner.get(route).json()==saved
    assert owner.get(route+"/sources?resource=orders").json()["items"][0]["status"]=="paid"
    assert any(row["event"]=="analyst.completed" for row in owner.get(path+"/audit-logs").json())


def test_private_history_tenant_roles_selected_ids_and_database_guard(accounts,model):
    owner,other,headers,other_headers,_,other_account,connection=accounts
    path=prepare(owner,headers)
    result=ask(owner,headers,path)
    route=path+"/analyst/investigations/"+result["id"]
    second=create(owner,headers,name="Separate")
    second_path=f"/api/v1/businesses/{second['id']}"
    for suffix in ["", "/sources", "/export"]:
        assert other.get(route+suffix).status_code==404
        assert owner.get(second_path+"/analyst/investigations/"+result["id"]+suffix).status_code==404
    owner.post(path+"/members",headers=headers,json={"email":other_account["user"]["email"],"role":"viewer"})
    assert other.get(route).status_code==404
    ask(other,other_headers,path,expected=403)
    owner.patch(path+"/members/"+other_account["user"]["id"],headers=headers,json={"role":"analyst"})
    personal=ask(other,other_headers,path)
    assert owner.get(path+"/analyst/investigations/"+personal["id"]).status_code==404
    assert len(other.get(path+"/analyst/investigations").json())==1
    assert owner.post(path+"/analyst/investigations",json=PERIOD|{"question":"Missing CSRF?"}).status_code==403
    ask(owner,headers,path,expected=404,forecast_run_id=str(uuid4()))
    ask(owner,headers,path,expected=404,document_ids=[str(uuid4())])
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        with pytest.raises(DBAPIError):
            db.execute(update(Investigation).where(Investigation.id==UUID(result["id"])).values(response={"answer":"Invented"}))
        db.rollback()


def test_provider_failure_invalid_tool_and_insufficient_evidence_are_explicit(accounts,model,monkeypatch):
    owner,_,headers,_,_,_,_=accounts
    path=prepare(owner,headers)
    monkeypatch.setattr(model,"plan",lambda *_:(_ for _ in ()).throw(ProviderError("Fixture provider unavailable")))
    failed=ask(owner,headers,path,expected=503)
    saved=owner.get(path+"/analyst/investigations/"+failed["investigation_id"]).json()
    assert saved["status"]=="failed" and saved["response"] is None and "unavailable" in saved["error"]
    monkeypatch.setattr(model,"plan",lambda *_:SimpleNamespace(tools=["execute_sql"]))
    failed=ask(owner,headers,path,expected=503)
    trace=owner.get(path+"/analyst/investigations/"+failed["investigation_id"]).json()["executions"]
    assert [item["tool"] for item in trace]==["get_business_metrics"]
    monkeypatch.setattr(model,"plan",lambda *_:Plan(tools=[]))
    monkeypatch.setattr(model,"select",lambda *_:Selection(supported=False,finding_ids=[],recommendation_ids=["seek_more_evidence"]))
    result=ask(owner,headers,path,question="What caused external competitor decisions?")
    assert result["response"]["insufficient"] is True and result["response"]["findings"]==[]
    assert "does not establish an answer" in result["response"]["answer"]


def test_missing_saved_model_is_a_partial_tool_failure_and_model_replay_is_read_only(accounts,model):
    from test_ml_integration import history,train
    owner,_,headers,_,_,_,connection=accounts
    business=create(owner,headers);path=f"/api/v1/businesses/{business['id']}"
    history(owner,headers,path)
    model.tools=["run_sales_forecast"]
    result=ask(owner,headers,path)
    assert result["status"]=="partial" and result["executions"][1]["status"]=="failed"
    trained=train(owner,headers,path)
    result=ask(owner,headers,path,forecast_run_id=trained["id"])
    output=result["executions"][1]["output"]
    assert output["run_id"]==trained["id"] and len(output["forecast"])==7 and output["source_changed"] is False
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        assert db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.business_id==UUID(business["id"])))==1
        assert db.get(ModelRun,UUID(trained["id"])).active is False


def test_concurrency_lease_and_source_limit_do_not_create_partial_rows(accounts,model,monkeypatch):
    owner,_,headers,_,identity,_,connection=accounts
    path=prepare(owner,headers)
    business_id=path.rsplit("/",1)[-1]
    key="nexora:analyst:lease:"+token_digest(f"{business_id}:{identity['user']['id']}")
    redis=Redis.from_url(get_settings().redis_url.get_secret_value())
    try:
        redis.set(key,"fixture-owned-lease",ex=30)
        ask(owner,headers,path,expected=409)
    finally:redis.delete(key);redis.close()
    monkeypatch.setattr("app.analyst.service.MAX_SOURCES",1)
    ask(owner,headers,path,expected=422)
    assert owner.get(path+"/analyst/investigations").json()==[]


def test_document_visibility_citations_and_later_revocation(processing,model):
    account_values,provider=processing
    owner,other,headers,other_headers,_,other_account,connection=account_values
    path=prepare(owner,headers)
    public=upload(owner,headers,path,text=b"Demo returns are accepted within thirty days with the receipt.")
    secret=upload(owner,headers,path,title="Administrator policy",visibility="administrators",text=b"Secret executive policy: supplier rebate is fifty percent.")
    pipeline.process_version(public["id"]);pipeline.process_version(secret["id"])
    model.provider=provider;model.tools=["search_business_documents"]
    owner.post(path+"/members",headers=headers,json={"email":other_account["user"]["email"],"role":"analyst"})
    result=ask(other,other_headers,path,question="What does the returns policy say?")
    assert result["response"]["findings"] and all(fact["citation"]["document_id"]==public["document_id"] for fact in result["response"]["findings"])
    assert all("Secret executive" not in fact["text"] for fact in result["response"]["findings"])
    ask(other,other_headers,path,expected=404,document_ids=[secret["document_id"]])
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        db.get(Document,UUID(public["document_id"])).visibility="administrators";db.commit()
    for suffix in ["", "/sources", "/export"]:
        assert other.get(path+"/analyst/investigations/"+result["id"]+suffix).status_code==403


def test_role_loss_during_provider_call_cannot_publish_an_answer(accounts,model):
    owner,other,headers,other_headers,_,other_account,_=accounts
    path=prepare(owner,headers)
    owner.post(path+"/members",headers=headers,json={"email":other_account["user"]["email"],"role":"administrator"})
    model.on_plan=lambda:owner.patch(path+"/members/"+other_account["user"]["id"],headers=headers,json={"role":"viewer"})
    result=ask(other,other_headers,path,expected=403)
    assert "investigation_id" in result
    assert other.get(path+"/analyst/investigations/"+result["investigation_id"]).status_code==403


def test_reviewed_scenarios_report_customer_queries_and_warmup_diagnostics(accounts,model):
    from test_twin_integration import save
    from test_simulation_integration import simulate
    owner,_,headers,_,_,_,_=accounts
    path=prepare(owner,headers)
    snapshot=save(owner,headers,path)
    left=simulate(owner,headers,path,snapshot,name="Baseline assumption")
    right=simulate(owner,headers,path,snapshot,name="Demand assumption",demand_change_pct="10")
    model.tools=["run_what_if_simulation","compare_scenarios","generate_business_report"]
    result=ask(owner,headers,path,scenario_run_ids=[left["id"],right["id"]])
    assert result["status"]=="completed"
    assert result["executions"][1]["output"]["result"]==left["result"]
    assert result["executions"][2]["output"]["changes"]["revenue"]["absolute_change"]=="2.80"
    assert result["executions"][3]["output"]["business"]["currency"]=="INR"
    add(owner,headers,path,"orders",[order("WARMUP",ordered_on="2026-08-01"),order("SPIKE",ordered_on="2026-10-27",quantity="100")])
    model.tools=["query_customers","detect_anomalies"]
    result=ask(owner,headers,path)
    assert result["status"]=="completed"
    assert result["executions"][1]["output"]["summary"]["active_in_period"]==1
    assert any(row["date"]=="2026-10-27" for row in result["executions"][2]["output"]["items"])


def test_financial_summary_retains_calculated_bridge_when_model_selects_only_totals(accounts,model,monkeypatch):
    owner,_,headers,_,_,_,_=accounts
    path=prepare(owner,headers)
    model.tools=[]
    monkeypatch.setattr(model,"select",lambda *_:Selection(supported=True,finding_ids=["E1.F1","E1.F2"],recommendation_ids=[]))
    result=ask(owner,headers,path)
    assert "gross profit by 16.00" in result["response"]["answer"]
    assert result["response"]["findings"][0]["id"]=="E1.F3"
