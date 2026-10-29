import os
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.models import Customer, Order, OrderItem, Product
from app.ml.datasets import closed_today
from app.ml.models import ModelRun
from app.models import Business
from test_identity_integration import accounts, create
from test_operations_integration import add, seed

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Requires migrated PostgreSQL/Redis")]
START = date(2026, 5, 1)
END = START+timedelta(days=79)


def history(owner, headers, path):
    seed(owner, headers, path)
    # Existing seed masters are labelled demo; historical sale labels define the training scope.
    rows = [{"external_id": f"F{index}", "ordered_on": (START+timedelta(days=index)).isoformat(), "customer_external_id": "C1", "product_sku": "P1", "quantity": str(1+index%7), "unit_price": str(10+index), "unit_cost": "4", "tax_amount": "1"} for index in range(80)]
    add(owner, headers, path, "orders", rows)


def config(**changes):
    return {"task": "sales", "start": START.isoformat(), "end": END.isoformat(), "aggregation": "daily", "horizon": 7, "coverage_confirmed": True, "data_scope": "real"} | changes


def train(owner, headers, path, **changes):
    response = owner.post(path+"/ml/forecasts", headers=headers, json=config(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_training_saved_artifact_replay_provenance_and_monitoring(accounts):
    owner, _, headers, _, _, _, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    history(owner, headers, path)
    run = train(owner, headers, path)
    assert len(run["history"]) == 80 and run["history"][0]["value"] == "10.00"
    assert len(run["result"]["forecast"]) == 7 and len(run["dataset_hash"]) == 64
    assert set(run["result"]["candidates"]) == {"seasonal_naive", "ridge_autoregression"}
    saved = owner.get(path+"/ml/runs/"+run["id"]).json()
    assert saved["artifact"] == run["artifact"]
    replay = owner.post(path+f"/ml/runs/{run['id']}/predict", headers=headers, json={"horizon": 7})
    assert replay.status_code == 200 and replay.json()["forecast"] == run["result"]["forecast"]
    sources = owner.get(path+f"/ml/runs/{run['id']}/sources?limit=1").json()
    assert sources["total"] == 80 and sources["items"][0]["date"] == START.isoformat()
    assert owner.get(path+f"/ml/runs/{run['id']}/monitor").json()["source_changed"] is False
    record = next(item for item in owner.get(path+"/orders?sort=reference&limit=100").json()["items"] if item["external_id"] == "F0")
    assert owner.patch(path+"/orders/"+record["id"], headers=headers, json={"status": "refunded", "reason": "Full return after model run"}).status_code == 200
    assert owner.get(path+f"/ml/runs/{run['id']}/monitor").json()["source_changed"] is True
    assert owner.get(path+f"/ml/runs/{run['id']}").json()["history"][0]["value"] == "10.00"


def test_training_scope_isolation_roles_and_active_unique_constraint(accounts):
    owner, other, headers, other_headers, _, other_account, connection = accounts
    business, second = create(owner, headers), create(owner, headers, name="Separate")
    path = f"/api/v1/businesses/{business['id']}"
    history(owner, headers, path)
    run = train(owner, headers, path)
    route = path+"/ml/runs/"+run["id"]
    assert other.get(route).status_code == 404
    assert owner.get(f"/api/v1/businesses/{second['id']}/ml/runs/{run['id']}").status_code == 404
    assert owner.post(path+"/members", headers=headers, json={"email": other_account["user"]["email"], "role": "viewer"}).status_code == 201
    assert other.get(route).status_code == 200
    assert other.post(path+"/ml/forecasts", headers=other_headers, json=config()).status_code == 403
    assert other.post(route+"/activate", headers=other_headers).status_code == 403
    assert owner.post(route+"/activate", headers=headers).status_code == 200
    newer = train(owner, headers, path, horizon=10)
    assert owner.post(path+f"/ml/runs/{newer['id']}/activate", headers=headers).status_code == 200
    assert owner.get(route).json()["active"] is False
    assert sum(item["active"] for item in owner.get(path+"/ml/runs").json()) == 1
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        original = db.get(ModelRun, UUID(run["id"]))
        original.active = True
        with pytest.raises(IntegrityError) as failure:
            db.flush()
        assert failure.value.orig.diag.constraint_name == "uq_active_model"
        db.rollback()


def test_demo_paid_only_data_and_insufficient_history(accounts):
    owner, _, headers, _, _, _, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    history(owner, headers, path)
    add(owner, headers, path, "orders", [{"external_id": "DEMO", "ordered_on": START.isoformat(), "customer_external_id": "C1", "product_sku": "P1", "quantity": "1000", "unit_price": "1000", "is_demo": True}, {"external_id": "PENDING", "ordered_on": START.isoformat(), "customer_external_id": "C1", "product_sku": "P1", "quantity": "1000", "unit_price": "1000", "status": "pending"}])
    run = train(owner, headers, path)
    assert run["history"][0]["value"] == "10.00" and run["source_count"] == 80
    response = owner.post(path+"/ml/forecasts", headers=headers, json=config(data_scope="demo"))
    assert response.status_code == 422 and "Insufficient" in response.text
    assert owner.post(path+"/ml/forecasts", headers=headers, json=config(coverage_confirmed=False)).status_code == 422
    assert owner.post(path+"/ml/forecasts", headers=headers, json=config(end=START.isoformat())).status_code == 422
    assert len(owner.get(path+"/ml/runs").json()) == 1


def test_product_demand_and_inventory_risk_are_distinct(accounts):
    owner, _, headers, _, _, _, connection = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    history(owner, headers, path)
    run = train(owner, headers, path, task="demand", product_sku="P1")
    assert run["history"][0]["value"] == "1.000" and run["task"] == "demand"
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        today = closed_today(db.get(Business, UUID(business["id"])))
    add(owner, headers, path, "orders", [{"external_id": "RECENT", "ordered_on": (today-timedelta(days=1)).isoformat(), "customer_external_id": "C1", "product_sku": "P1", "quantity": "28", "unit_price": "10"}])
    response = owner.get(path+"/ml/inventory-risk?product_sku=P1&lead_days=30")
    assert response.status_code == 200, response.text
    risk = response.json()
    assert risk["calculation_type"] == "deterministic_inventory_risk"
    assert risk["daily_rate"] == "1.000" and risk["current_stock"] == "20.000" and risk["shortfall"] == "10.000"
    assert risk["demo_stock_present"] is True
    assert owner.get(path+"/ml/inventory-risk?product_sku=FOREIGN").status_code == 404
    assert owner.post(path+"/ml/forecasts", headers=headers, json=config(task="demand", product_sku="FOREIGN")).status_code == 404


def test_churn_uses_historical_outcomes_and_saves_current_estimates(accounts):
    owner, _, headers, _, account, _, connection = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    business_id = UUID(business["id"])
    end = date(2026, 10, 20)
    with Session(connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
        product = Product(business_id=business_id, sku="CHURN", name="Customer service", unit_price=Decimal(10), unit_cost=Decimal(4))
        db.add(product)
        db.flush()
        for index in range(80):
            customer = Customer(business_id=business_id, external_id=f"CH{index}", name="Synthetic test customer")
            db.add(customer)
            db.flush()
            dates = [end-timedelta(days=60+index%10+1)]
            if index < 40: dates.append(end-timedelta(days=53))
            if index%2 == 0: dates.append(end-timedelta(days=23))
            for number, day in enumerate(dates):
                order = Order(business_id=business_id, customer_id=customer.id, external_id=f"CH{index}-{number}", ordered_on=day, status="paid", currency="INR")
                db.add(order)
                db.flush()
                db.add(OrderItem(business_id=business_id, order_id=order.id, product_id=product.id, quantity=Decimal(1), unit_price=Decimal(10), unit_cost=Decimal(4), discount_amount=Decimal(0), tax_amount=Decimal(0)))
        db.commit()
    response = owner.post(path+"/ml/churn", headers=headers, json={"end": end.isoformat(), "inactivity_days": 30, "coverage_confirmed": True})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["algorithm"] == "logistic_inactivity" and run["result"]["evaluation"]["observations"] == 80
    assert len(run["result"]["predictions"]) == 80 and run["artifact"]["features"][0] == "purchase_recency_days"
    assert owner.get(path+f"/ml/runs/{run['id']}/monitor").json()["source_changed"] is False
