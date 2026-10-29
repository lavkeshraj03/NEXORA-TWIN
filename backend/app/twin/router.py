from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.businesses import access
from app.core.security import current_user, rate_limit
from app.db.session import get_session
from app.data.service import json_ready
from app.ml.datasets import closed_today, fingerprint
from app.models import AuditLog, User
from app.schemas import Input
from app.twin.models import TwinSnapshot
from app.twin.service import VERSION, capture, compare, summary, verified

router = APIRouter(prefix="/businesses/{business_id}/twin", tags=["Digital twin"])


class SnapshotInput(Input):
    name: str = Field(min_length=1, max_length=100)
    start: date
    end: date

    @model_validator(mode="after")
    def dates(self):
        if not self.name.strip():
            raise ValueError("Enter a snapshot name")
        if self.end < self.start or (self.end-self.start).days > 365:
            raise ValueError("Choose a reporting period of 1–366 days")
        self.name = self.name.strip()
        return self


def owned(db, business_id, snapshot_id):
    row = db.scalar(select(TwinSnapshot).where(TwinSnapshot.business_id == business_id, TwinSnapshot.id == snapshot_id))
    if row is None:
        raise HTTPException(404, "Snapshot not found")
    return row


@router.get("/current")
def current(business_id: UUID, start: date, end: date, user: User = Depends(current_user), db: Session = Depends(get_session)):
    business, _ = access(db, user, business_id, "twin:read", lock=True)
    if end < start or (end-start).days > 365 or end > closed_today(business):
        raise HTTPException(422, "Choose 1–366 reporting days ending no later than the current business-local day")
    return {"state": capture(db, business, start, end)["state"], "integrity": "live_calculation"}


@router.post("/snapshots", status_code=201)
def create_snapshot(business_id: UUID, data: SnapshotInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    business, _ = access(db, user, business_id, "twin:write", lock=True)
    if data.end > closed_today(business):
        raise HTTPException(422, "Snapshot reporting cannot extend beyond the current business-local day")
    rate_limit(f"twin-create:{business_id}:{user.id}", 20, 3600)
    if db.scalar(select(func.count()).select_from(TwinSnapshot).where(TwinSnapshot.business_id == business_id)) >= 50:
        raise HTTPException(422, "This release retains at most 50 snapshots per business")
    payload = capture(db, business, data.start, data.end)
    snapshot = TwinSnapshot(business_id=business_id, created_by=user.id, name=data.name, implementation_version=VERSION, content_hash=fingerprint(payload), payload=payload)
    db.add(snapshot)
    db.flush()
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="twin.snapshot_created", target_id=str(snapshot.id)))
    db.commit()
    return summary(snapshot) | {"state": payload["state"]}


@router.get("/snapshots")
def snapshots(business_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "twin:read")
    # History must not load 50 potentially large evidence payloads into memory.
    query = select(TwinSnapshot.id, TwinSnapshot.name, TwinSnapshot.created_at, TwinSnapshot.content_hash,
        TwinSnapshot.implementation_version, TwinSnapshot.payload["state"]["period"].label("period"),
        TwinSnapshot.payload["state"]["business"]["currency"].as_string().label("currency"),
        TwinSnapshot.payload["state"]["demo_records"].as_integer().label("demo_records"))
    return json_ready([dict(row) for row in db.execute(query.where(TwinSnapshot.business_id == business_id).order_by(TwinSnapshot.created_at.desc(), TwinSnapshot.id.desc()).limit(50)).mappings()])


@router.get("/compare")
def comparison(business_id: UUID, left: UUID, right: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "twin:read")
    return compare(verified(owned(db, business_id, left)), verified(owned(db, business_id, right))) | {"left_id": str(left), "right_id": str(right)}


@router.get("/snapshots/{snapshot_id}")
def detail(business_id: UUID, snapshot_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "twin:read")
    row = owned(db, business_id, snapshot_id)
    return summary(row) | {"state": verified(row), "integrity": "verified_and_reproduced"}


@router.get("/snapshots/{snapshot_id}/sources")
def sources(business_id: UUID, snapshot_id: UUID, resource: str = "orders", limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=20000), user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "twin:read")
    row = owned(db, business_id, snapshot_id)
    verified(row)
    records = row.payload["inputs"]["sources"].get(resource)
    if records is None:
        raise HTTPException(422, "Unknown snapshot source resource")
    return {"items": records[offset:offset+limit], "total": len(records), "limit": limit, "offset": offset, "source_hash": fingerprint(records), "definition": "Saved source values at capture; later operational changes do not rewrite these records."}
