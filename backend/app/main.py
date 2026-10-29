import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.health import router
from app.api.auth import router as auth_router
from app.api.businesses import router as businesses_router
from app.data.router import router as data_router
from app.documents.router import router as documents_router
from app.ml.router import router as ml_router
from app.twin.router import router as twin_router
from app.simulation.router import router as simulation_router
from app.analyst.router import router as analyst_router
from app.graph.router import router as graph_router
from app.reports.router import router as reports_router
from app.core.config import get_settings
from app.core.body_limit import BodyLimitMiddleware

logger = logging.getLogger("nexora.requests")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NEXORA TWIN API", version="0.1.0", docs_url="/api/docs" if settings.environment != "production" else None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"], expose_headers=["X-Request-ID"])

    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        logger.info(json.dumps({"event": "request", "request_id": request.state.request_id, "method": request.method, "status": response.status_code, "duration_ms": round((perf_counter() - started) * 1000, 2)}))
        return response

    def error(request: Request, status: int, code: str, message: str):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(request, exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error(request, 422, "validation_error", "Request validation failed")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error(json.dumps({"event": "unhandled_error", "request_id": getattr(request.state, "request_id", None), "exception_type": type(exc).__name__}))
        return error(request, 500, "internal_error", "An unexpected error occurred")

    app.include_router(router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(businesses_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(ml_router, prefix="/api/v1")
    app.include_router(twin_router, prefix="/api/v1")
    app.include_router(simulation_router, prefix="/api/v1")
    app.include_router(analyst_router, prefix="/api/v1")
    app.include_router(graph_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(data_router, prefix="/api/v1")
    return app


app = create_app()
