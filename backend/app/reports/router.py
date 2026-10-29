from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.api.businesses import access
from app.core.exporting import csv_bytes,pdf_bytes
from app.core.security import current_user,rate_limit
from app.data.service import json_ready
from app.db.session import get_session
from app.ml.datasets import fingerprint
from app.models import AuditLog,User
from app.reports.models import GeneratedReport
from app.reports.schemas import ReportInput
from app.reports.service import VERSION,generate_payload,owned,export_rows,export_lines

router=APIRouter(prefix="/businesses/{business_id}/reports",tags=["Business reports"])


def detail(row):
    return json_ready({"id":row.id,"name":row.name,"kind":row.kind,"created_at":row.created_at,"content_hash":row.content_hash,"implementation_version":row.implementation_version,"payload":row.payload})


@router.post("",status_code=201)
def generate(business_id:UUID,data:ReportInput,user:User=Depends(current_user),db:Session=Depends(get_session)):
    access(db,user,business_id,"reports:create",lock=True)
    rate_limit(f"report-generate:{business_id}:{user.id}",20,3600)
    if db.scalar(select(func.count()).select_from(GeneratedReport).where(GeneratedReport.business_id==business_id))>=40:raise HTTPException(422,"This release retains at most forty reports per business")
    payload,role=generate_payload(db,business_id,user,data)
    row=GeneratedReport(business_id=business_id,user_id=user.id,captured_role=role,name=data.name,kind=data.kind,implementation_version=VERSION,payload=payload,content_hash=fingerprint(payload))
    db.add(row);db.flush();db.add(AuditLog(business_id=business_id,user_id=user.id,event="report.generated",target_id=str(row.id)));db.commit()
    return detail(row)


@router.get("")
def history(business_id:UUID,user:User=Depends(current_user),db:Session=Depends(get_session)):
    _,member=access(db,user,business_id,"reports:read")
    query=select(GeneratedReport.id,GeneratedReport.name,GeneratedReport.kind,GeneratedReport.created_at,GeneratedReport.content_hash).where(GeneratedReport.business_id==business_id,GeneratedReport.user_id==user.id)
    if member.role not in {"owner","administrator"}:query=query.where(GeneratedReport.captured_role.not_in(["owner","administrator"]))
    return json_ready([dict(row) for row in db.execute(query.order_by(GeneratedReport.created_at.desc(),GeneratedReport.id.desc()).limit(40)).mappings()])


@router.get("/{report_id}")
def saved(business_id:UUID,report_id:UUID,user:User=Depends(current_user),db:Session=Depends(get_session)):
    return detail(owned(db,business_id,user,report_id))


@router.get("/{report_id}/export/{format}")
def export(business_id:UUID,report_id:UUID,format:str,user:User=Depends(current_user),db:Session=Depends(get_session)):
    row=owned(db,business_id,user,report_id)
    if format=="csv":raw,media=csv_bytes(export_rows(row.payload)),"text/csv"
    elif format=="pdf":
        try:raw=pdf_bytes(export_lines(row.payload))
        except ValueError as error:raise HTTPException(422,str(error))
        media="application/pdf"
    else:raise HTTPException(422,"Export format must be csv or pdf")
    db.add(AuditLog(business_id=business_id,user_id=user.id,event="report.exported",target_id=str(row.id)));db.commit()
    return Response(raw,media_type=media,headers={"Content-Disposition":f'attachment; filename="report-{report_id}.{format}"',"Cache-Control":"no-store"})
