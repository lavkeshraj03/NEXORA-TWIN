from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import ROLE_PERMISSIONS, may_manage_role
from app.core.security import current_user, rate_limit
from app.db.session import get_session
from app.models import AuditLog, Business, Membership, User
from app.schemas import AuditOut, BusinessInput, BusinessOut, MemberInput, MemberOut, PROFILE_MODULES, RoleInput

router = APIRouter(prefix="/businesses", tags=["Businesses"])


def access(db: Session, user: User, business_id: UUID, permission: str, lock: bool = False) -> tuple[Business, Membership]:
    # Lock before checking role on writes so concurrent role edits cannot use stale permissions.
    query = select(Business).where(Business.id == business_id)
    business = db.scalar(query.with_for_update() if lock else query)
    membership = db.get(Membership, (business_id, user.id), populate_existing=True)
    if business is None or membership is None:
        raise HTTPException(404, "Business not found")
    if permission not in ROLE_PERMISSIONS.get(membership.role, frozenset()):
        raise HTTPException(403, "Your role does not allow this action")
    return business, membership


def business_out(business: Business, membership: Membership) -> BusinessOut:
    fields = {field: getattr(business, field) for field in BusinessInput.model_fields}
    return BusinessOut(**fields, id=business.id, role=membership.role, permissions=sorted(ROLE_PERMISSIONS[membership.role]), created_at=business.created_at, updated_at=business.updated_at, data_status=business.data_status)


@router.get("/profiles")
def profiles(user: User = Depends(current_user)) -> dict[str, list[str]]:
    return PROFILE_MODULES


@router.get("", response_model=list[BusinessOut])
def list_businesses(user: User = Depends(current_user), db: Session = Depends(get_session)):
    rows = db.execute(select(Business, Membership).join(Membership, Membership.business_id == Business.id).where(Membership.user_id == user.id).order_by(Business.created_at, Business.id)).all()
    return [business_out(business, membership) for business, membership in rows]


@router.post("", response_model=BusinessOut, status_code=201)
def create_business(data: BusinessInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    rate_limit("business-create:" + str(user.id), 30, 3600)
    business = Business(**data.model_dump())
    db.add(business)
    db.flush()
    membership = Membership(business_id=business.id, user_id=user.id, role="owner")
    db.add(membership)
    db.add(AuditLog(business_id=business.id, user_id=user.id, event="business.created", target_id=str(business.id)))
    db.commit()
    return business_out(business, membership)


@router.get("/{business_id}", response_model=BusinessOut)
def get_business(business_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    return business_out(*access(db, user, business_id, "business:read"))


@router.put("/{business_id}", response_model=BusinessOut)
def update_business(business_id: UUID, data: BusinessInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    business, membership = access(db, user, business_id, "business:write", lock=True)
    if data.currency != business.currency and business.data_status == "has_data":
        raise HTTPException(409, "Currency cannot change after operational records exist; create a separate business for another currency")
    for key, value in data.model_dump().items():
        setattr(business, key, value)
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="business.updated", target_id=str(business_id)))
    db.commit()
    return business_out(business, membership)


@router.get("/{business_id}/members", response_model=list[MemberOut])
def members(business_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "team:read")
    rows = db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id).where(Membership.business_id == business_id).order_by(User.name, User.id)).all()
    return [MemberOut(user_id=member.id, name=member.name, email=member.email, role=membership.role) for member, membership in rows]


@router.post("/{business_id}/members", response_model=MemberOut, status_code=201)
def add_member(business_id: UUID, data: MemberInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    _, actor = access(db, user, business_id, "team:write", lock=True)
    if not may_manage_role(actor.role, data.role):
        raise HTTPException(403, "Only an owner can grant this role")
    target = db.scalar(select(User).where(User.email == data.email.lower()))
    if target is None:
        raise HTTPException(404, "Ask this teammate to create an account first")
    if db.get(Membership, (business_id, target.id)):
        raise HTTPException(409, "This account is already a member")
    db.add(Membership(business_id=business_id, user_id=target.id, role=data.role))
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="membership.added", target_id=str(target.id)))
    db.commit()
    return MemberOut(user_id=target.id, name=target.name, email=target.email, role=data.role)


def member_change(db: Session, user: User, business_id: UUID, target_id: UUID, new_role: str | None) -> Membership:
    _, actor = access(db, user, business_id, "team:write", lock=True)
    target = db.get(Membership, (business_id, target_id), populate_existing=True)
    if target is None:
        raise HTTPException(404, "Member not found")
    if not may_manage_role(actor.role, target.role) or (new_role is not None and not may_manage_role(actor.role, new_role)):
        raise HTTPException(403, "Only an owner can manage this role")
    if target.role == "owner" and new_role != "owner":
        owners = db.scalar(select(func.count()).select_from(Membership).where(Membership.business_id == business_id, Membership.role == "owner"))
        if owners == 1:
            raise HTTPException(409, "A business must retain at least one owner")
    return target


@router.patch("/{business_id}/members/{target_id}", status_code=204)
def change_role(business_id: UUID, target_id: UUID, data: RoleInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    target = member_change(db, user, business_id, target_id, data.role)
    target.role = data.role
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="membership.role_changed", target_id=str(target_id)))
    db.commit()


@router.delete("/{business_id}/members/{target_id}", status_code=204)
def remove_member(business_id: UUID, target_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    target = member_change(db, user, business_id, target_id, None)
    db.delete(target)
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="membership.removed", target_id=str(target_id)))
    db.commit()


@router.get("/{business_id}/audit-logs", response_model=list[AuditOut])
def audit_logs(business_id: UUID, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "audit:read")
    return db.scalars(select(AuditLog).where(AuditLog.business_id == business_id).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)).all()
