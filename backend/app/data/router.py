import csv
import io
import json
import re
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.businesses import access
from app.core.security import current_user
from app.data.imports import MAX_BYTES, batch_out, commit_batch, create_batch, validate_batch
from app.data.models import Expense, ExpenseCoverage, ImportBatch, Order, Product
from app.data.schemas import ConfirmInput, CoverageInput, MappingInput, SCHEMAS, StatusInput
from app.data.service import LABELS, MODELS, dashboard, invalidate_expense_coverage, json_ready, period, persist_rows, record_dict, reference_context, require_resource, validate_rows
from app.db.session import get_session
from app.models import AuditLog, User
from app.schemas import Input
from pydantic import Field

router = APIRouter(prefix="/businesses/{business_id}",tags=["Operational data"])


class RowsInput(Input):
    rows: list[dict] = Field(min_length=1,max_length=100)


def csv_text(rows: list[dict]) -> str:
    def safe(value):
        if isinstance(value,(list,dict)):
            value=json.dumps(value)
        text="" if value is None else str(value)
        if text.lstrip().startswith(("=","+","-","@")) and not re.fullmatch(r"-?\d+(\.\d+)?",text):
            return "'"+text
        return text
    output=io.StringIO()
    columns=list(dict.fromkeys(key for row in rows for key in row))
    writer=csv.DictWriter(output,fieldnames=columns)
    writer.writeheader()
    writer.writerows({key:safe(row.get(key)) for key in columns} for row in rows)
    return output.getvalue()


def csv_response(rows,filename):
    return Response(csv_text(rows),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="{filename}"'})


@router.get("/data-schema")
def data_schema(business_id: UUID,user: User=Depends(current_user),db: Session=Depends(get_session)):
    business,_=access(db,user,business_id,"data:read")
    resources={}
    for resource,schema in SCHEMAS.items():
        if resource=="inventory" and "inventory" not in business.modules:
            continue
        specification=schema.model_json_schema()
        fields=[]
        for name,definition in specification["properties"].items():
            actual=next((item for item in definition.get("anyOf",[]) if item.get("type")!="null"),definition)
            kind="enum" if "enum" in actual else "date" if actual.get("format")=="date" else "boolean" if actual.get("type")=="boolean" else "decimal" if actual.get("type") in {"number","integer"} else "string"
            fields.append({"name":name,"label":name.replace("_"," "),"type":kind,"required":name in specification.get("required",[]),"options":actual.get("enum",[]),"default":definition.get("default")})
        resources[resource]={"label":LABELS[business.business_type].get(resource,resource.title()),"fields":fields}
    return {"resources":resources,"max_import_rows":1000,"max_upload_bytes":MAX_BYTES,"currency":business.currency}


@router.get("/dashboard")
def get_dashboard(business_id: UUID,start: date|None=None,end: date|None=None,user: User=Depends(current_user),db: Session=Depends(get_session)):
    business,_=access(db,user,business_id,"data:read")
    start,end=period(business,start,end)
    try:
        return dashboard(db,business,start,end)
    except ValueError as failure:
        raise HTTPException(422,str(failure))


@router.put("/expense-coverage")
def expense_coverage(business_id: UUID,data: CoverageInput,user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:write",lock=True)
    coverage=db.get(ExpenseCoverage,(business_id,data.start_date,data.end_date))
    if coverage is None:
        coverage=ExpenseCoverage(business_id=business_id,**data.model_dump(),confirmed_by=user.id)
        db.add(coverage)
    else:
        coverage.complete=data.complete
        coverage.confirmed_by=user.id
    db.add(AuditLog(business_id=business_id,user_id=user.id,event="expenses.coverage_confirmed" if data.complete else "expenses.coverage_retracted"))
    db.commit()
    return {"complete":coverage.complete,"start_date":data.start_date,"end_date":data.end_date}


@router.post("/imports")
async def upload_import(business_id: UUID,request: Request,resource: str=Query(max_length=20),filename: str=Query(min_length=1,max_length=200),user: User=Depends(current_user),db: Session=Depends(get_session)):
    require_resource(resource)
    raw=bytearray()
    async for chunk in request.stream():
        if len(raw)+len(chunk)>MAX_BYTES:
            raise HTTPException(413,"Upload exceeds 2 MiB")
        raw.extend(chunk)
    def process():
        business,_=access(db,user,business_id,"data:write",lock=True)
        return create_batch(db,business,user,resource,filename,bytes(raw))
    return await run_in_threadpool(process)


@router.get("/imports")
def import_history(business_id: UUID,limit: int=Query(20,ge=1,le=100),offset: int=Query(0,ge=0),user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:read")
    records=db.scalars(select(ImportBatch).where(ImportBatch.business_id==business_id).order_by(ImportBatch.created_at.desc()).limit(limit).offset(offset)).all()
    return [batch_out(batch) for batch in records]


def owned_batch(db,business_id,batch_id):
    batch=db.scalar(select(ImportBatch).where(ImportBatch.business_id==business_id,ImportBatch.id==batch_id))
    if batch is None:
        raise HTTPException(404,"Import not found")
    return batch


@router.get("/imports/{batch_id}")
def get_import(business_id: UUID,batch_id: UUID,user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:read")
    return batch_out(owned_batch(db,business_id,batch_id))


@router.post("/imports/{batch_id}/validate")
def validate_import(business_id: UUID,batch_id: UUID,data: MappingInput,user: User=Depends(current_user),db: Session=Depends(get_session)):
    business,_=access(db,user,business_id,"data:write",lock=True)
    batch=owned_batch(db,business_id,batch_id)
    validate_batch(db,business,batch,data.mapping)
    db.commit()
    return batch_out(batch)


@router.post("/imports/{batch_id}/commit")
def confirm_import(business_id: UUID,batch_id: UUID,data: ConfirmInput,user: User=Depends(current_user),db: Session=Depends(get_session)):
    business,_=access(db,user,business_id,"data:write",lock=True)
    batch=owned_batch(db,business_id,batch_id)
    if batch.status!="committed" and batch.updated_at!=data.preview_updated_at:
        raise HTTPException(409,"The preview changed; reload and review it before confirming")
    return commit_batch(db,business,user,batch)


@router.get("/imports/{batch_id}/errors")
def import_errors(business_id: UUID,batch_id: UUID,user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:read")
    return csv_response(owned_batch(db,business_id,batch_id).errors,"import-errors.csv")


@router.get("/{resource}/export")
def export_records(business_id: UUID,resource: str,user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:read")
    require_resource(resource)
    model=MODELS[resource]
    records=db.scalars(select(model).where(model.business_id==business_id).order_by(model.created_at,model.id).limit(10001)).all()
    if len(records)>10000:
        raise HTTPException(422,"Exports currently support up to 10000 records")
    context=reference_context(db,business_id)
    return csv_response([record_dict(db,resource,item,context) for item in records],resource+".csv")


@router.get("/transactions")
def transactions(business_id: UUID,limit: int=Query(25,ge=1,le=100),offset: int=Query(0,ge=0),user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:read")
    # A traceable projection; never add these amounts to order/expense metrics again.
    records=[]
    context=reference_context(db,business_id)
    for model,resource,kind in [(Order,"orders","sale"),(Expense,"expenses","operating_expense")]:
        source=db.scalars(select(model).where(model.business_id==business_id,model.status=="paid").order_by(model.created_at.desc(),model.id.desc()).limit(offset+limit)).all()
        for item in source:
            record=record_dict(db,resource,item,context)
            records.append({"id":record["id"],"source":resource,"external_id":record["external_id"],"date":record.get("ordered_on",record.get("incurred_on")),"kind":kind,"amount":record.get("net_sales",record.get("amount")),"currency":record["currency"],"is_demo":record["is_demo"],"created_at":record["created_at"]})
    records.sort(key=lambda item:(item["created_at"],item["id"]),reverse=True)
    return {"items":records[offset:offset+limit],"offset":offset,"limit":limit,"definition":"Current paid sales and operating expenses; source projection, not a separate accounting ledger."}


@router.get("/{resource}")
def list_records(business_id: UUID,resource: str,search: str=Query("",max_length=100),status: str|None=Query(None,max_length=20),sort: str=Query("newest",pattern="^(newest|oldest|reference)$"),limit: int=Query(25,ge=1,le=100),offset: int=Query(0,ge=0),user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:read")
    require_resource(resource)
    model=MODELS[resource]
    query=select(model).where(model.business_id==business_id)
    reference=getattr(model,"sku" if resource=="products" else "external_id")
    if search:
        term="%"+search.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        predicate=reference.ilike(term,escape="\\")
        if hasattr(model,"name"):
            predicate=predicate|model.name.ilike(term,escape="\\")
        query=query.where(predicate)
    if status and hasattr(model,"status"):
        query=query.where(model.status==status)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    ordering=reference.asc() if sort=="reference" else model.created_at.asc() if sort=="oldest" else model.created_at.desc()
    records=db.scalars(query.order_by(ordering,model.id).limit(limit).offset(offset)).all()
    context=reference_context(db,business_id)
    return {"items":[record_dict(db,resource,item,context) for item in records],"total":total,"offset":offset,"limit":limit}


@router.post("/{resource}",status_code=201)
def create_records(business_id: UUID,resource: str,data: RowsInput,user: User=Depends(current_user),db: Session=Depends(get_session)):
    business,_=access(db,user,business_id,"data:write",lock=True)
    parsed,errors,context=validate_rows(db,business,resource,data.rows)
    if errors:
        raise HTTPException(422,"; ".join(f"Row {item['row']}, {item['field']}: {item['message']}" for item in errors[:10]))
    count=persist_rows(db,business,resource,parsed,context)
    db.add(AuditLog(business_id=business_id,user_id=user.id,event="data."+resource+".created"))
    db.commit()
    return {"created_rows":count}


@router.get("/{resource}/{record_id}")
def record_details(business_id: UUID,resource: str,record_id: UUID,user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:read")
    require_resource(resource)
    record=db.scalar(select(MODELS[resource]).where(MODELS[resource].business_id==business_id,MODELS[resource].id==record_id))
    if record is None:
        raise HTTPException(404,"Record not found")
    return record_dict(db,resource,record)


@router.patch("/{resource}/{record_id}")
def update_status(business_id: UUID,resource: str,record_id: UUID,data: StatusInput,user: User=Depends(current_user),db: Session=Depends(get_session)):
    access(db,user,business_id,"data:write",lock=True)
    if resource not in {"orders","expenses"}:
        raise HTTPException(422,"This record is immutable; add a correction using a new external identifier")
    model=MODELS[resource]
    record=db.scalar(select(model).where(model.business_id==business_id,model.id==record_id))
    if record is None:
        raise HTTPException(404,"Record not found")
    transitions={"pending":{"paid","cancelled"},"paid":{"refunded"} if resource=="orders" else {"voided"},"cancelled":set(),"refunded":set(),"voided":set()}
    if data.status not in transitions[record.status]:
        raise HTTPException(409,"This status transition is not allowed")
    if resource == "expenses":
        invalidate_expense_coverage(db, business_id, [record.incurred_on])
    record.status=data.status
    record.status_reason=data.reason
    db.add(AuditLog(business_id=business_id,user_id=user.id,event="data."+resource+"."+data.status,target_id=str(record.id)))
    db.commit()
    return record_dict(db,resource,record)
