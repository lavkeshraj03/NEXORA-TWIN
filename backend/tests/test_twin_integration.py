import os
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.ml.datasets import closed_today, fingerprint
from app.models import Business
from app.twin.models import TwinSnapshot
from app.twin.service import compare, verified
from test_identity_integration import accounts, create
from test_operations_integration import add, order, seed

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Requires migrated PostgreSQL/Redis")]
PERIOD = {"start": "2026-10-01", "end": "2026-10-28"}


def save(owner, headers, path, name="Review", **changes):
    response = owner.post(path+"/twin/snapshots", headers=headers, json=PERIOD | {"name": name} | changes)
    assert response.status_code == 201, response.text
    return response.json()


def test_snapshot_replays_after_refund_stock_change_and_source_provenance(accounts):
    owner, _, headers, _, _, _, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    seed(owner, headers, path)
    add(owner, headers, path, "orders", [order(), order("PENDING", status="pending")])
    add(owner, headers, path, "expenses", [{"external_id":"E1", "incurred_on":"2026-10-10", "category":"rent", "amount":"5.50", "is_demo":True}])
    assert owner.put(path+"/expense-coverage", headers=headers, json={"start_date":PERIOD["start"], "end_date":PERIOD["end"], "complete":True}).status_code == 200
    snapshot = save(owner, headers, path)
    route = path+"/twin/snapshots/"+snapshot["id"]
    first = owner.get(route).json()
    state = first["state"]
    assert first["integrity"] == "verified_and_reproduced"
    assert state["metrics"] == owner.get(path+"/dashboard?start=2026-10-01&end=2026-10-28").json()["metrics"]
    assert state["metrics"]["operating_profit"] == "10.50" and state["inventory_value"] == "80.00"
    assert state["orders"]["pending"] == 1 and state["demo_records"] > 0
    assert state["forecasts"] == [] and state["customers"]["retention_pct"] is None
    source = owner.get(route+"/sources?resource=order_items&limit=1").json()
    assert source["total"] == 2 and len(source["items"]) == 1
    item_id = state["metric_provenance"]["revenue"]["sources"]["order_items"][0]
    assert item_id in {row["id"] for row in owner.get(route+"/sources?resource=order_items").json()["items"]}
    assert "email" not in owner.get(route+"/sources?resource=customers").json()["items"][0]
    old_order = next(row for row in owner.get(path+"/orders").json()["items"] if row["external_id"] == "O1")
    assert owner.patch(path+"/orders/"+old_order["id"], headers=headers, json={"status":"refunded", "reason":"Snapshot regression"}).status_code == 200
    add(owner, headers, path, "inventory", [{"external_id":"MOVE", "product_sku":"P1", "occurred_on":"2026-10-10", "quantity_delta":"-3", "reason":"sale"}])
    new = save(owner, headers, path, "After correction")
    assert new["state"]["metrics"]["revenue"] == "0.00" and new["state"]["inventory_value"] == "68.00"
    assert owner.get(route).json() == first
    comparison = owner.get(path+f"/twin/compare?left={snapshot['id']}&right={new['id']}").json()
    assert comparison["same_period"] and comparison["metrics"]["revenue"]["absolute_change"] == "-28.00"
    assert comparison["metrics"]["revenue"]["percentage_change"] == "-100.00"
    assert set(comparison["source_changes"]) >= {"orders", "inventory", "balances"}
    assert next(row for row in owner.get(route+"/sources?resource=orders").json()["items"] if row["external_id"] == "O1")["status"] == "paid"
    assert any(row["event"] == "twin.snapshot_created" for row in owner.get(path+"/audit-logs").json())


def test_snapshot_roles_tenant_routes_csrf_and_invalid_periods(accounts):
    owner, other, headers, other_headers, _, other_account, connection = accounts
    business, second = create(owner, headers), create(owner, headers, name="Other workspace")
    path, other_path = [f"/api/v1/businesses/{row['id']}" for row in [business, second]]
    snapshot = save(owner, headers, path)
    route = path+"/twin/snapshots/"+snapshot["id"]
    for suffix in ["/twin/snapshots", "/twin/current?start=2026-10-01&end=2026-10-28", "/twin/snapshots/"+snapshot["id"], "/twin/snapshots/"+snapshot["id"]+"/sources", f"/twin/compare?left={snapshot['id']}&right={snapshot['id']}"]:
        assert other.get(path+suffix).status_code == 404
    assert owner.get(other_path+"/twin/snapshots/"+snapshot["id"]).status_code == 404
    assert owner.get(other_path+f"/twin/compare?left={snapshot['id']}&right={snapshot['id']}").status_code == 404
    assert owner.post(path+"/twin/snapshots", json=PERIOD|{"name":"No CSRF"}).status_code == 403
    assert owner.post(path+"/members", headers=headers, json={"email":other_account["user"]["email"], "role":"viewer"}).status_code == 201
    assert other.get(route).status_code == 200
    assert other.get(route+"/sources").status_code == 200
    assert other.post(path+"/twin/snapshots", headers=other_headers, json=PERIOD|{"name":"Denied"}).status_code == 403
    assert owner.patch(path+"/members/"+other_account["user"]["id"], headers=headers, json={"role":"analyst"}).status_code == 204
    save(other, other_headers, path, "Analyst review")
    assert owner.get(route+"/sources?resource=passwords").status_code == 422
    assert owner.get(route+"/sources?limit=101").status_code == 422
    for changes in [{"start":"2026-10-29"}, {"name":" "}, {"start":"2024-01-01"}]:
        assert owner.post(path+"/twin/snapshots", headers=headers, json=PERIOD|{"name":"Bad"}|changes).status_code == 422
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        tomorrow = (closed_today(db.get(Business, UUID(business["id"])))+timedelta(days=1)).isoformat()
    assert owner.post(path+"/twin/snapshots", headers=headers, json={"name":"Future", "start":tomorrow,"end":tomorrow}).status_code == 422
    assert owner.get(path+f"/twin/current?start={tomorrow}&end={tomorrow}").status_code == 422
    assert owner.patch(route, headers=headers, json={"name":"Mutate"}).status_code == 405


def test_snapshot_empty_unknown_costs_currency_and_integrity(accounts, monkeypatch):
    owner, _, headers, _, _, _, connection = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    empty = save(owner, headers, path, "Empty")
    state = empty["state"]
    assert state["metrics"]["revenue"] == "0.00" and state["metrics"]["operating_profit"] is None
    assert state["health"][0]["status"] == "unknown"
    seed(owner, headers, path)
    add(owner, headers, path, "orders", [order(unit_cost=None)])
    missing = save(owner, headers, path, "Unknown cost")
    assert missing["state"]["metrics"]["cogs"] is None and missing["state"]["missing_cost_lines"] == 1
    result = compare(state, missing["state"])
    assert result["metrics"]["revenue"]["percentage_change"] is None
    assert result["metrics"]["cogs"]["absolute_change"] is None
    other_currency = deepcopy(state)
    other_currency["business"]["currency"] = "USD"
    with pytest.raises(HTTPException): compare(state, other_currency)
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        row = db.get(TwinSnapshot, UUID(empty["id"]))
        original = deepcopy(row.payload)
        row.payload = original | {"state": original["state"] | {"demo_records":999}}
        with pytest.raises(HTTPException, match="409"): verified(row)
        row.content_hash = fingerprint(row.payload)
        with pytest.raises(HTTPException, match="409"): verified(row)
        db.rollback()
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        with pytest.raises(DBAPIError):
            db.execute(update(TwinSnapshot).where(TwinSnapshot.id == UUID(empty["id"])).values(name="Rewrite evidence"))
        db.rollback()
    monkeypatch.setattr("app.twin.service.MAX_SOURCES", 1)
    assert owner.post(path+"/twin/snapshots", headers=headers, json=PERIOD|{"name":"Too large"}).status_code == 422
    assert len(owner.get(path+"/twin/snapshots").json()) == 2
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        original = db.get(TwinSnapshot, UUID(empty["id"]))
        db.add_all([TwinSnapshot(business_id=original.business_id, created_by=original.created_by, name=f"Retained {index}", implementation_version="1", content_hash=original.content_hash, payload=original.payload) for index in range(48)])
        db.commit()
    assert owner.post(path+"/twin/snapshots", headers=headers, json=PERIOD|{"name":"Over retention cap"}).status_code == 422
    assert len(owner.get(path+"/twin/snapshots").json()) == 50


def test_active_forecast_is_frozen_separate_from_actuals(accounts):
    from test_ml_integration import history, train
    owner, _, headers, _, _, _, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    history(owner, headers, path)
    model = train(owner, headers, path)
    assert owner.post(path+f"/ml/runs/{model['id']}/activate", headers=headers).status_code == 200
    snapshot = save(owner, headers, path)
    forecast = snapshot["state"]["forecasts"][0]
    assert forecast["run_id"] == model["id"] and forecast["result"] == model["result"]
    assert forecast["dataset_hash"] == model["dataset_hash"]
    another = train(owner, headers, path, horizon=10)
    assert owner.post(path+f"/ml/runs/{another['id']}/activate", headers=headers).status_code == 200
    assert owner.get(path+f"/twin/snapshots/{snapshot['id']}").json()["state"]["forecasts"][0] == forecast
