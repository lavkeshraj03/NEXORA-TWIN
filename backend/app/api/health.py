from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

router = APIRouter(tags=["Health"])
SCHEMA_REVISION = "0009_insights"


class Check(BaseModel):
    status: Literal["healthy", "unavailable"]
    detail: str


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    checked_at: datetime
    version: str = "0.1.0"
    checks: dict[str, Check]


def probe_database() -> tuple[Check, Check, Check]:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            vector = conn.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            has_table = conn.scalar(text("SELECT to_regclass('public.alembic_version')"))
            revision = conn.scalar(text("SELECT version_num FROM alembic_version")) if has_table else None
        return (
            Check(status="healthy", detail="PostgreSQL connection verified"),
            Check(status="healthy" if vector else "unavailable", detail=f"pgvector {vector}" if vector else "pgvector extension is not installed"),
            Check(status="healthy" if revision == SCHEMA_REVISION else "unavailable", detail="Schema is current" if revision == SCHEMA_REVISION else "Run Alembic migrations"),
        )
    except Exception:
        # Do not expose credentials, driver exceptions or network topology.
        unavailable = Check(status="unavailable", detail="Database checks failed; inspect server configuration")
        return unavailable, unavailable, unavailable


def probe_redis() -> Check:
    try:
        with Redis.from_url(get_settings().redis_url.get_secret_value(), socket_connect_timeout=2, socket_timeout=2) as client:
            client.ping()
        return Check(status="healthy", detail="Redis connection verified")
    except Exception:
        return Check(status="unavailable", detail="Redis is unavailable")


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive", "service": "nexora-api", "version": "0.1.0"}


@router.get("/health/ready", response_model=Readiness, responses={503: {"model": Readiness}})
def readiness():
    database, vector, migrations = probe_database()
    checks = {"database": database, "pgvector": vector, "migrations": migrations, "redis": probe_redis()}
    ready = all(check.status == "healthy" for check in checks.values())
    result = Readiness(status="ready" if ready else "not_ready", checked_at=datetime.now(timezone.utc), checks=checks)
    return JSONResponse(status_code=200 if ready else 503, content=result.model_dump(mode="json"))
