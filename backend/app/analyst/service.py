import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.businesses import access
from app.analyst.models import Investigation
from app.analyst.provider import get_model
from app.analyst.tools import CATALOG, RECOMMENDATIONS, invoke, states
from app.core.permissions import ROLE_PERMISSIONS
from app.documents.models import Document
from app.documents.provider import ProviderError
from app.documents.rag import visible_documents
from app.ml.datasets import closed_today, fingerprint
from app.ml.models import ModelRun
from app.models import AuditLog
from app.simulation.router import owned as owned_scenario
from app.twin.service import capture

VERSION = "1"
MAX_SOURCES = 5000
logger = logging.getLogger("nexora.analyst")


def evidence_access(db, business_id, user, row):
    _, member = access(db,user,business_id,"analyst:read")
    if row.captured_role in {"owner","administrator"} and member.role not in {"owner","administrator"}:
        raise HTTPException(403,"This investigation was captured with administrator access; start a new investigation for your current role")
    document_ids = {source["document_id"] for execution in row.executions for source in execution.get("output",{}).get("sources",[])}
    if document_ids:
        from uuid import UUID
        visible = set(str(value) for value in db.scalars(select(Document.id).where(*visible_documents(business_id,member.role),Document.id.in_([UUID(value) for value in document_ids]))))
        if visible != document_ids: raise HTTPException(403,"A cited document is no longer visible to your role")
    for execution in row.executions:
        if CATALOG[execution["tool"]][0] not in ROLE_PERMISSIONS[member.role]:
            raise HTTPException(403,"Your current role no longer permits this investigation's tool evidence")
    return member


def validate_selections(db, business_id, member, data):
    if data.document_ids:
        count = db.scalar(select(func.count()).select_from(Document).where(*visible_documents(business_id,member.role),Document.id.in_(data.document_ids)))
        if count != len(set(data.document_ids)): raise HTTPException(404,"Selected documents were not found in your visible business scope")
    for run_id,task in [(data.forecast_run_id,"sales"),(data.churn_run_id,"churn")]:
        if run_id and db.scalar(select(ModelRun.id).where(ModelRun.business_id==business_id,ModelRun.id==run_id,ModelRun.task==task,ModelRun.data_scope==data.model_data_scope)) is None:
            raise HTTPException(404,"Selected model was not found for this business, task and data scope")
    for run_id in data.scenario_run_ids: owned_scenario(db,business_id,run_id)


def summarize(row):
    return {"id":str(row.id),"question":row.question,"status":row.status,"created_at":row.created_at.isoformat(),"finished_at":row.finished_at.isoformat() if row.finished_at else None,"chat_model":row.chat_model}


def process(db,business_id,user,data,request_id):
    business,member=access(db,user,business_id,"analyst:ask",lock=True)
    if data.end>closed_today(business):raise HTTPException(422,"Reporting cannot extend beyond the current business-local day")
    if db.scalar(select(func.count()).select_from(Investigation).where(Investigation.business_id==business_id))>=30:
        raise HTTPException(422,"This release retains at most 30 investigations per business")
    validate_selections(db,business_id,member,data)
    payload=capture(db,business,data.start,data.end)
    inputs=payload["inputs"]
    if sum(len(rows) for rows in inputs["sources"].values())>MAX_SOURCES:
        raise HTTPException(422,f"The initial analyst supports at most {MAX_SOURCES} operational source records per business")
    if data.product_sku and not any(row["sku"]==data.product_sku for row in inputs["sources"]["products"]):
        raise HTTPException(404,"Product SKU not found in this captured business")
    model=get_model()
    row=Investigation(business_id=business_id,user_id=user.id,captured_role=member.role,question=data.question,request_id=request_id or str(uuid4()),
        implementation_version=VERSION,chat_model=model.chat_model,parameters=data.model_dump(mode="json"),inputs=inputs,input_hash=fingerprint(inputs),plan={},executions=[],status="running",response=None)
    db.add(row);db.flush()
    db.add(AuditLog(business_id=business_id,user_id=user.id,event="analyst.started",target_id=str(row.id)))
    db.commit()  # Do not hold the business write lock across provider calls.
    deadline=time.monotonic()+240
    current,previous=states(inputs)
    facts=[]

    def execute(name):
        access(db,user,business_id,"analyst:ask")
        access(db,user,business_id,CATALOG[name][0])
        model.budget(deadline)
        begun=datetime.now(timezone.utc);started=time.perf_counter()
        execution={"id":f"E{len(row.executions)+1}","tool":name,"permission":CATALOG[name][0],"started_at":begun.isoformat(),"arguments":{"reporting_period":{"start":data.start.isoformat(),"end":data.end.isoformat()}},"facts":[]}
        try:
            output,tool_facts,args=invoke(name,db,business_id,user,data,inputs,current,previous,model,deadline)
            for index,fact in enumerate(tool_facts,1):
                fact|={"id":f"{execution['id']}.F{index}","evidence_id":execution["id"]}
            facts.extend(tool_facts)
            execution|={"status":"completed","arguments":args,"output":output,"facts":tool_facts}
        except HTTPException as error:
            if error.status_code in {401,403}:raise
            execution|={"status":"failed","error":str(error.detail)[:300],"error_status":error.status_code}
        except (ProviderError,ValueError) as error:
            execution|={"status":"failed","error":str(error)[:300],"error_status":503 if isinstance(error,ProviderError) else 422}
        execution|={"finished_at":datetime.now(timezone.utc).isoformat(),"duration_ms":round((time.perf_counter()-started)*1000)}
        row.executions=row.executions+[execution]
        db.commit()

    try:
        execute("get_business_metrics")
        _,member=access(db,user,business_id,"analyst:ask")
        allowed={name:description for name,(permission,description) in CATALOG.items() if name!="get_business_metrics" and permission in ROLE_PERMISSIONS[member.role]}
        db.commit()
        plan=model.plan(data.question,allowed,{"model_data_scope":data.model_data_scope,"forecast_selected":bool(data.forecast_run_id),"churn_model_selected":bool(data.churn_run_id),"reviewed_scenarios_selected":len(data.scenario_run_ids),"document_scope_selected":bool(data.document_ids)},deadline)
        # Revalidate even for test/custom model adapters, before dispatch.
        if len(plan.tools)>3 or len(set(plan.tools))!=len(plan.tools) or any(name not in allowed for name in plan.tools):
            raise ProviderError("Invalid or unauthorized analyst tool plan")
        evidence_access(db,business_id,user,row)
        row.plan=plan.model_dump(mode="json");db.commit()
        for name in plan.tools:execute(name)
        access(db,user,business_id,"analyst:ask")
        evidence_access(db,business_id,user,row)
        recommendations={key:value for key,value in RECOMMENDATIONS.items() if key in {"review_sources","seek_more_evidence"}}
        successful={item["tool"] for item in row.executions if item["status"]=="completed"}
        optional={"query_sales":"inspect_product_mix","query_inventory":"review_stock","search_business_documents":"review_policy","run_sales_forecast":"review_model","predict_customer_churn":"review_model","run_what_if_simulation":"test_scenario","compare_scenarios":"test_scenario"}
        for tool,key in optional.items():
            if tool in successful:recommendations[key]=RECOMMENDATIONS[key]
        if current["metrics"]["operating_profit"] is None or previous["metrics"]["operating_profit"] is None:recommendations["check_cost_coverage"]=RECOMMENDATIONS["check_cost_coverage"]
        db.commit()
        selection=model.select(data.question,[{key:fact[key] for key in ["id","text","kind"]} for fact in facts],recommendations,deadline)
        lookup={fact["id"]:fact for fact in facts}
        if any(key not in lookup for key in selection.finding_ids) or any(key not in recommendations for key in selection.recommendation_ids) or bool(selection.finding_ids)!=selection.supported:
            raise ProviderError("The AI model selected unsupported evidence; no answer was saved")
        access(db,user,business_id,"analyst:ask")
        evidence_access(db,business_id,user,row)
        chosen=[lookup[key] for key in dict.fromkeys(selection.finding_ids)]
        # Keep the accounting bridge visible when the selected answer is financial.
        # This is an existing calculated fact, not a new model-authored claim.
        bridge=lookup.get("E1.F3")
        financial_context=any(fact["evidence_id"]=="E1" and fact["kind"]=="calculated_historical" for fact in chosen) or ("generate_business_report" in successful and any(fact["kind"]=="calculated_historical" for fact in chosen))
        if selection.supported and financial_context and bridge and bridge not in chosen:
            chosen=([bridge]+chosen)[:6]
        answer="\n\n".join(f"{fact['text']} [{fact['evidence_id']}]" for fact in chosen) if selection.supported else "The collected evidence does not establish an answer to this question. Review the tool results and supply additional relevant data."
        row.response={"answer":answer,"findings":chosen,"recommendations":[recommendations[key] for key in dict.fromkeys(selection.recommendation_ids)],"insufficient":not selection.supported,
            "demo_records":current["demo_records"],"data_updated_at":current["data_updated_at"],
            "synthesis_method":"Model-selected validated evidence, with the calculated comparison bridge retained for financial summaries.",
            "input_hash":row.input_hash,"evidence_hash":fingerprint(row.executions),"chat_model":model.chat_model,"usage":getattr(model,"usage",[]),"estimated_cost":None,
            "limitations":["Observed relationships and accounting changes do not establish causes. No consequential action was taken.","Reporting dates are the explicit UI selection; words such as this month in a question do not override those dates.","Financial tools include all real and labelled demo records, matching Overview. Model tools use the selected real/demo scope at their original cutoff.","Findings are model-selected server-calculated facts or exact document excerpts. Valid references do not establish that the selected evidence fully answers the question; human review is still needed.","Operational values are frozen at capture; document/model/scenario tools record their separate retrieval time and saved version. No automatic training, activation, new assumptions or operational updates occur."]}
        row.status="partial" if any(item["status"]=="failed" for item in row.executions) else "completed"
        row.finished_at=datetime.now(timezone.utc)
        db.add(AuditLog(business_id=business_id,user_id=user.id,event="analyst.completed",target_id=str(row.id)))
        db.commit()
        return row,None
    except Exception as error:
        db.rollback()
        if isinstance(error,HTTPException):message,status=str(error.detail),error.status_code
        elif isinstance(error,ProviderError):message,status=str(error),503
        else:
            logger.error({"event":"analyst_failed","request_id":row.request_id,"exception_type":type(error).__name__})
            message,status="The analyst could not complete this investigation; inspect server logs",500
        row.status="failed";row.error=message[:300];row.finished_at=datetime.now(timezone.utc);row.response=None
        db.add(AuditLog(business_id=business_id,user_id=user.id,event="analyst.failed",target_id=str(row.id)))
        db.commit()
        return row,status
