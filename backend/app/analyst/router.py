import csv
import io
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from redis import Redis
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.businesses import access
from app.analyst.models import Investigation
from app.analyst.schemas import InvestigationInput
from app.analyst.service import VERSION, evidence_access, process, summarize
from app.core.config import get_settings
from app.core.security import current_user, rate_limit, token_digest
from app.data.service import json_ready
from app.db.session import get_session
from app.ml.datasets import fingerprint
from app.models import User

router=APIRouter(prefix="/businesses/{business_id}/analyst",tags=["AI business analyst"])


def owned(db,business_id,user,run_id):
    row=db.scalar(select(Investigation).where(Investigation.id==run_id,Investigation.business_id==business_id,Investigation.user_id==user.id))
    if row is None:raise HTTPException(404,"Investigation not found")
    evidence_access(db,business_id,user,row)
    if row.implementation_version!=VERSION or fingerprint(row.inputs)!=row.input_hash:
        raise HTTPException(409,"Investigation source integrity/version check failed")
    if row.response and fingerprint(row.executions)!=row.response["evidence_hash"]:
        raise HTTPException(409,"Investigation tool evidence integrity check failed")
    return row


@router.post("/investigations",status_code=201)
def investigate(business_id:UUID,data:InvestigationInput,request:Request,user:User=Depends(current_user),db:Session=Depends(get_session)):
    access(db,user,business_id,"analyst:ask")
    rate_limit(f"analyst:{business_id}:{user.id}",10,3600)
    key="nexora:analyst:lease:"+token_digest(f"{business_id}:{user.id}")
    token=uuid4().hex
    redis=Redis.from_url(get_settings().redis_url.get_secret_value(),socket_connect_timeout=2,socket_timeout=2)
    try:
        if not redis.set(key,token,nx=True,ex=300):raise HTTPException(409,"An investigation is already running for your account in this business")
    except HTTPException:raise
    except Exception:raise HTTPException(503,"The analyst execution coordinator is unavailable") from None
    try:
        row,status=process(db,business_id,user,data,getattr(request.state,"request_id",None))
        if status:
            return JSONResponse(status_code=status,content={"error":{"code":"analyst_failed","message":row.error},"investigation_id":str(row.id)})
        return summarize(row)|{"parameters":row.parameters,"response":row.response,"executions":row.executions,"input_hash":row.input_hash,"captured_at":row.inputs["captured_at"]}
    finally:
        try:redis.eval("if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end; return 0",1,key,token)
        except Exception:pass  # Lease expires; never release another request's token.
        redis.close()


@router.get("/investigations")
def history(business_id:UUID,user:User=Depends(current_user),db:Session=Depends(get_session)):
    _,member=access(db,user,business_id,"analyst:read")
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=5)
    db.execute(update(Investigation).where(Investigation.business_id==business_id,Investigation.user_id==user.id,Investigation.status=="running",Investigation.created_at<cutoff).values(status="failed",error="The investigation was interrupted; start a new investigation",finished_at=datetime.now(timezone.utc)))
    db.commit()
    query=select(Investigation.id,Investigation.question,Investigation.status,Investigation.created_at,Investigation.finished_at,Investigation.chat_model).where(Investigation.business_id==business_id,Investigation.user_id==user.id)
    if member.role not in {"owner","administrator"}:query=query.where(Investigation.captured_role.not_in(["owner","administrator"]))
    return json_ready([dict(row) for row in db.execute(query.order_by(Investigation.created_at.desc(),Investigation.id.desc()).limit(30)).mappings()])


@router.get("/investigations/{run_id}")
def detail(business_id:UUID,run_id:UUID,user:User=Depends(current_user),db:Session=Depends(get_session)):
    access(db,user,business_id,"analyst:read")
    row=owned(db,business_id,user,run_id)
    return summarize(row)|{"parameters":row.parameters,"response":row.response,"executions":row.executions,"input_hash":row.input_hash,"captured_at":row.inputs["captured_at"],"error":row.error,"request_id":row.request_id}


@router.get("/investigations/{run_id}/sources")
def sources(business_id:UUID,run_id:UUID,resource:str="orders",limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0,le=5000),user:User=Depends(current_user),db:Session=Depends(get_session)):
    access(db,user,business_id,"analyst:read")
    row=owned(db,business_id,user,run_id)
    records=row.inputs["sources"].get(resource)
    if records is None:raise HTTPException(422,"Unknown source resource")
    return {"items":records[offset:offset+limit],"total":len(records),"source_hash":fingerprint(records),"definition":"Frozen operational input values at this investigation's capture, independent of later edits."}


@router.get("/investigations/{run_id}/export")
def export(business_id:UUID,run_id:UUID,user:User=Depends(current_user),db:Session=Depends(get_session)):
    access(db,user,business_id,"analyst:read")
    row=owned(db,business_id,user,run_id)
    if not row.response:raise HTTPException(409,"Only completed investigation findings can be exported")
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(["AI investigation — recorded evidence, not established causation"])
    entries={"business":row.inputs["business"]["name"],"question":row.question,"status":row.status,"reporting_dates":{"start":row.parameters["start"],"end":row.parameters["end"]},"captured_at":row.inputs["captured_at"],"chat_model":row.chat_model,"input_hash":row.input_hash,"response":row.response,"tool_executions":row.executions}
    for key,value in entries.items():
        cell=json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
        writer.writerow([key,"'"+cell if cell.lstrip().startswith(("=","+","-","@")) else cell])
    return Response(output.getvalue(),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="investigation-{run_id}.csv"',"Cache-Control":"no-store"})
