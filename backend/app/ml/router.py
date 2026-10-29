from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.businesses import access
from app.core.security import current_user, rate_limit
from app.data.service import json_ready
from app.db.session import get_session
from app.ml.datasets import closed_today, fingerprint, product_for, series
from app.ml.forecasting import metrics
from app.ml.models import ModelRun
from app.ml.service import churn_dataset, forecast_rows, stock_risk, summary, train_churn, train_series
from app.models import AuditLog, User
from app.schemas import Input

router = APIRouter(prefix="/businesses/{business_id}/ml", tags=["Forecasting and models"])


class ForecastInput(Input):
    task: Literal["sales", "demand"] = "sales"
    start: date
    end: date
    aggregation: Literal["daily", "weekly"] = "daily"
    horizon: int = Field(default=7, ge=1, le=30)
    product_sku: str | None = Field(default=None, min_length=1, max_length=80)
    data_scope: Literal["real", "demo"] = "real"
    coverage_confirmed: Literal[True]

    @model_validator(mode="after")
    def valid_task(self):
        if (self.task == "demand") != bool(self.product_sku):
            raise ValueError("Demand requires a product SKU; sales forecasts use all products")
        if self.aggregation == "weekly" and self.horizon > 12:
            raise ValueError("Weekly forecasts support at most 12 weeks")
        return self


class ChurnInput(Input):
    end: date
    inactivity_days: int = Field(default=30, ge=14, le=90)
    data_scope: Literal["real", "demo"] = "real"
    coverage_confirmed: Literal[True]


def owned_run(db, business_id, run_id):
    run = db.scalar(select(ModelRun).where(ModelRun.business_id == business_id, ModelRun.id == run_id))
    if run is None:
        raise HTTPException(404, "Model run not found")
    return run


def training_allowed(db, business_id, user):
    rate_limit(f"ml-train:{business_id}:{user.id}", 10, 3600)
    if db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.business_id == business_id)) >= 20:
        raise HTTPException(422, "This release retains at most 20 model runs per business")


@router.post("/forecasts", status_code=201)
def train_forecast(business_id: UUID, data: ForecastInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    business, _ = access(db, user, business_id, "ml:train", lock=True)
    training_allowed(db, business_id, user)
    product = product_for(db, business_id, data.product_sku) if data.product_sku else None
    try:
        run = train_series(db, business, user, data, product)
        db.add(AuditLog(business_id=business_id, user_id=user.id, event="ml.forecast_trained"))
        db.commit()
        return summary(run, True)
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.post("/churn", status_code=201)
def train_inactivity(business_id: UUID, data: ChurnInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    business, _ = access(db, user, business_id, "ml:train", lock=True)
    training_allowed(db, business_id, user)
    try:
        run = train_churn(db, business, user, data)
        db.add(AuditLog(business_id=business_id, user_id=user.id, event="ml.churn_trained"))
        db.commit()
        return summary(run, True)
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.get("/runs")
def list_runs(business_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "ml:read")
    runs = db.scalars(select(ModelRun).where(ModelRun.business_id == business_id).order_by(ModelRun.created_at.desc(), ModelRun.id).limit(limit).offset(offset)).all()
    return [summary(run) for run in runs]


@router.get("/runs/{run_id}")
def get_run(business_id: UUID, run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "ml:read")
    return summary(owned_run(db, business_id, run_id), True)


@router.get("/runs/{run_id}/sources")
def source_records(business_id: UUID, run_id: UUID, on: date | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "ml:read")
    run = owned_run(db, business_id, run_id)
    end = on + timedelta(days=6 if run.config.get("aggregation") == "weekly" else 0) if on else None
    rows = [row for row in run.dataset["sources"] if on is None or on.isoformat() <= row["date"] <= end.isoformat()]
    return {"items": rows[offset:offset+limit], "total": len(rows), "limit": limit, "offset": offset, "definition": "Immutable source values used for this run; current records may have changed"}


@router.post("/runs/{run_id}/activate")
def activate(business_id: UUID, run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "ml:deploy", lock=True)
    run = owned_run(db, business_id, run_id)
    if run.implementation_version != "1" or fingerprint(run.dataset) != run.dataset_hash:
        raise HTTPException(409, "Model integrity/version check failed")
    db.execute(update(ModelRun).where(ModelRun.business_id == business_id, ModelRun.task == run.task, ModelRun.data_scope == run.data_scope, ModelRun.product_id == run.product_id).values(active=False))
    run.active = True
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="ml.model_activated", target_id=str(run.id)))
    db.commit()
    return summary(run, True)


class PredictInput(Input):
    horizon: int = Field(default=7, ge=1, le=30)


@router.post("/runs/{run_id}/predict")
def model_predict(business_id: UUID, run_id: UUID, data: PredictInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "ml:read")
    run = owned_run(db, business_id, run_id)
    if run.task == "churn":
        raise HTTPException(422, "Churn predictions belong to the saved cutoff; train a new run for a later cutoff")
    if run.implementation_version != "1" or fingerprint(run.dataset) != run.dataset_hash:
        raise HTTPException(409, "Model integrity/version check failed")
    if run.config["aggregation"] == "weekly" and data.horizon > 12:
        raise HTTPException(422, "Weekly forecasts support at most 12 weeks")
    try:
        return {"run_id": str(run.id), "origin": run.config["end"], "forecast": forecast_rows(run.dataset, run.result, run.artifact, data.horizon), "definition": "Inference from the saved JSON artifact; no retraining or data refresh occurs"}
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.get("/runs/{run_id}/monitor")
def monitor(business_id: UUID, run_id: UUID, coverage_confirmed: bool = False, user: User = Depends(current_user), db: Session = Depends(get_session)):
    business, _ = access(db, user, business_id, "ml:read", lock=True)
    run = owned_run(db, business_id, run_id)
    if run.task == "churn":
        current = churn_dataset(db, business, ChurnInput(end=run.config["end"], inactivity_days=run.config["inactivity_days"], data_scope=run.data_scope, coverage_confirmed=True))
        return {"run_id": str(run.id), "source_changed": fingerprint(current) != run.dataset_hash, "metrics": None, "definition": "Historical source check only; future churn outcomes require a later labelled run"}
    current = series(db, business, date.fromisoformat(run.config["start"]), date.fromisoformat(run.config["end"]), run.config["aggregation"], run.task, run.data_scope, run.product_id)
    actuals, predictions = [], []
    if coverage_confirmed:
        for point in run.result["forecast"]:
            start = date.fromisoformat(point["date"])
            end = start + timedelta(days=6 if run.config["aggregation"] == "weekly" else 0)
            if end >= closed_today(business):
                break
            observed = series(db, business, start, end, run.config["aggregation"], run.task, run.data_scope, run.product_id)
            actuals.append(float(observed["points"][0]["value"]))
            predictions.append(float(point["prediction"]))
    return {"run_id": str(run.id), "source_changed": fingerprint(current) != run.dataset_hash, "observed_periods": len(actuals), "metrics": metrics(actuals, predictions) if actuals else None, "definition": "Future-outcome metrics require explicit confirmation that the observed forecast window is fully imported. No automatic retraining."}


@router.get("/inventory-risk")
def inventory_risk(business_id: UUID, product_sku: str = Query(min_length=1, max_length=80), lead_days: int = Query(7, ge=1, le=180), incoming: Decimal = Query(Decimal(0), ge=0, le=1000000000, decimal_places=3), safety: Decimal = Query(Decimal(0), ge=0, le=1000000000, decimal_places=3), data_scope: Literal["real", "demo"] = "real", user: User = Depends(current_user), db: Session = Depends(get_session)):
    business, _ = access(db, user, business_id, "ml:read", lock=True)
    if "inventory" not in business.modules:
        raise HTTPException(422, "Inventory risk requires an enabled inventory module")
    product = product_for(db, business_id, product_sku)
    return stock_risk(db, business, product, data_scope, lead_days, incoming, safety)
