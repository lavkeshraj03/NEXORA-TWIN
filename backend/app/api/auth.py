import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import COOKIE, current_session, current_user, dummy_hash, hash_password, rate_limit, require_origin, token_digest, verify_password
from app.db.session import get_session
from app.models import AuditLog, AuthSession, User
from app.schemas import Credentials, Register, SessionOut, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


def session_response(user: User, response: Response, db: Session) -> SessionOut:
    token = secrets.token_urlsafe(32)
    session = AuthSession(token_hash=token_digest(token), user_id=user.id, csrf_token=secrets.token_urlsafe(32), expires_at=datetime.now(timezone.utc) + timedelta(hours=8))
    db.add(session)
    db.add(AuditLog(user_id=user.id, event="auth.session_created"))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=get_settings().environment == "production", samesite="lax", max_age=8 * 3600, path="/")
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token, expires_at=session.expires_at)


@router.post("/register", response_model=SessionOut, status_code=201, dependencies=[Depends(require_origin)])
def register(data: Register, request: Request, response: Response, db: Session = Depends(get_session)):
    ip = request.client.host if request.client else "unknown"
    rate_limit("register:" + ip, 5, 3600)
    user = User(email=data.email, name=data.name, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with that email already exists")
    db.add(AuditLog(user_id=user.id, event="auth.registered"))
    return session_response(user, response, db)


@router.post("/login", response_model=SessionOut, dependencies=[Depends(require_origin)])
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_session)):
    ip = request.client.host if request.client else "unknown"
    rate_limit("login-ip:" + ip, 120, 900)
    rate_limit("login-email:" + data.email, 20, 900)
    user = db.scalar(select(User).where(User.email == data.email))
    valid = verify_password(data.password, user.password_hash if user else dummy_hash())
    if user is None or not valid:
        db.add(AuditLog(event="auth.login_failed"))
        db.commit()
        raise HTTPException(401, "Email or password is incorrect")
    return session_response(user, response, db)


@router.get("/me", response_model=SessionOut)
def me(session: AuthSession = Depends(current_session), user: User = Depends(current_user)):
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token, expires_at=session.expires_at)


@router.post("/logout", status_code=204)
def logout(response: Response, session: AuthSession = Depends(current_session), db: Session = Depends(get_session)):
    db.add(AuditLog(user_id=session.user_id, event="auth.logged_out"))
    db.delete(session)
    db.commit()
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=get_settings().environment == "production", samesite="lax")
