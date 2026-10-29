import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.models import AuthSession, User

COOKIE = "nexora_session"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return f"scrypt$32768$8$3${salt}${result.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if (algorithm, n, r, p) != ("scrypt", "32768", "8", "3"):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


@lru_cache
def dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_origin(request: Request):
    if request.headers.get("origin") not in get_settings().allowed_origins:
        raise HTTPException(403, "Origin is not allowed")


def rate_limit(key: str, limit: int, seconds: int):
    # Atomic increment and expiration; no unbounded counters if a process fails.
    script = "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]); end; return n"
    try:
        with Redis.from_url(get_settings().redis_url.get_secret_value(), socket_connect_timeout=2, socket_timeout=2) as redis:
            count = redis.eval(script, 1, "nexora:auth:" + token_digest(key), seconds)
    except Exception:
        raise HTTPException(503, "Authentication rate-limit service is unavailable")
    if int(count) > limit:
        raise HTTPException(429, "Too many attempts; try again later")


def current_session(request: Request, db: Session = Depends(get_session)) -> AuthSession:
    token = request.cookies.get(COOKIE, "")
    if not 20 <= len(token) <= 128:
        raise HTTPException(401, "Sign in to continue")
    session = db.get(AuthSession, token_digest(token))
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(401, "Your session has expired; sign in again")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        if not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), session.csrf_token.encode()):
            raise HTTPException(403, "CSRF validation failed")
    return session


def current_user(session: AuthSession = Depends(current_session), db: Session = Depends(get_session)) -> User:
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return user
