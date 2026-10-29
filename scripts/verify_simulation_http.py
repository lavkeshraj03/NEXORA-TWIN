"""Live Next.js → API → PostgreSQL simulation acceptance with owned-record cleanup."""
import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import AuditLog, Business, Membership, User

BASE = "http://localhost:3000"


def main():
    prefix = "nexora-simulation-http-"+uuid4().hex
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    users, businesses, csrf = [], [], None

    def call(path, method="GET", body=None, expected=200):
        headers = {"Origin": BASE}
        if csrf: headers["X-CSRF-Token"] = csrf
        data = json.dumps(body).encode() if body is not None else None
        if data is not None: headers["Content-Type"] = "application/json"
        try:
            response = client.open(Request(BASE+"/api/backend/"+path, method=method, headers=headers, data=data), timeout=65)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            assert response.code == expected, f"{method} {path}: {response.code}: {content[:300]!r}"
            return json.loads(content) if content else None

    try:
        identity = call("auth/register", "POST", {"name":"Twin acceptance", "email":prefix+"@example.com", "password":secrets.token_urlsafe(32)}, 201)
        users.append(UUID(identity["user"]["id"]))
        csrf = identity["csrf_token"]
        for name in ["Twin HTTP check", "Separate twin HTTP check"]:
            business = call("businesses", "POST", {"name":name, "business_type":"retail", "country":"IN", "currency":"INR", "timezone":"Asia/Kolkata"}, 201)
            businesses.append(UUID(business["id"]))
        path, other = ["businesses/"+str(value) for value in businesses]
        end = datetime.now(ZoneInfo("Asia/Kolkata")).date()-timedelta(days=1)
        start = end-timedelta(days=29)
        period = {"start":start.isoformat(), "end":end.isoformat()}
        def add(resource, rows): return call(path+"/"+resource, "POST", {"rows":rows}, 201)
        add("customers", [{"external_id":"C1", "name":"Demo customer", "is_demo":True}])
        add("products", [{"sku":"P1", "name":"Demo product", "unit_price":"10", "unit_cost":"4", "initial_stock":"20", "is_demo":True}])
        add("orders", [{"external_id":"O1", "ordered_on":end.isoformat(), "customer_external_id":"C1", "product_sku":"P1", "quantity":"3", "unit_price":"10", "unit_cost":"4", "discount_amount":"2", "is_demo":True}])
        add("expenses", [{"external_id":"E1", "incurred_on":end.isoformat(), "category":"rent", "amount":"5.50", "is_demo":True}])
        call(path+"/expense-coverage", "PUT", {"start_date":period["start"], "end_date":period["end"], "complete":True})
        baseline = call(path+"/twin/snapshots", "POST", period|{"name":"Baseline"}, 201)
        route = path+"/twin/snapshots/"+baseline["id"]
        saved = call(route)
        assert saved["integrity"] == "verified_and_reproduced"
        assert saved["state"]["metrics"]["operating_profit"] == "10.50"
        assert saved["state"]["inventory_value"] == "80.00"
        assert len(call(path+"/twin/snapshots")) == 1
        assert call(route+"/sources?resource=orders")["items"][0]["status"] == "paid"
        call(other+"/twin/snapshots/"+baseline["id"], expected=404)
        call(other+f"/twin/compare?left={baseline['id']}&right={baseline['id']}", expected=404)
        params = {"name":"Price +10% assumption", "baseline_snapshot_id":baseline["id"], "price_change_pct":"10", "price_elasticity":"-1", "sensitivity_elasticities":["-0.5","-1","-2"]}
        preview = call(path+"/simulations/preview", "POST", params)
        assert preview["persisted"] is False and call(path+"/simulations/runs") == []
        call(path+"/simulations/runs", "POST", params|{"customer_loss_pct":"10", "preview_hash":preview["preview_hash"], "assumptions_confirmed":True}, expected=409)
        run = call(path+"/simulations/runs", "POST", params|{"preview_hash":preview["preview_hash"], "assumptions_confirmed":True}, expected=201)
        run_route = path+"/simulations/runs/"+run["id"]
        assert run["integrity"] == "verified_and_reproduced"
        assert run["result"]["metrics"]["revenue"] == "28.00"
        assert run["result"]["metrics"]["operating_profit"] == "11.59"
        assert len(run["result"]["sensitivity"]) == 3
        zero = {"name":"Unchanged assumption", "baseline_snapshot_id":baseline["id"]}
        zero_preview = call(path+"/simulations/preview", "POST", zero)
        zero_run = call(path+"/simulations/runs", "POST", zero|{"preview_hash":zero_preview["preview_hash"], "assumptions_confirmed":True}, expected=201)
        assert zero_run["result"]["metrics"] == zero_run["result"]["baseline_metrics"]
        compared = call(path+f"/simulations/compare?left={zero_run['id']}&right={run['id']}")
        assert compared["changes"]["operating_profit"]["absolute_change"] == "1.09"
        supply = {"name":"Incoming stock assumption", "baseline_snapshot_id":baseline["id"], "product_sku":"P1", "replenishment_units":"5", "stock_constrained":True}
        supply_preview = call(path+"/simulations/preview", "POST", supply)
        assert supply_preview["result"]["replenishment_cash_outlay"] == "20.00"
        assert supply_preview["result"]["metrics"]["operating_profit"] == "10.50"
        call(other+"/simulations/runs/"+run["id"], expected=404)
        call(other+"/simulations/preview", "POST", params, expected=404)
        call(path+"/simulations/preview", "POST", {"name":"Missing elasticity", "baseline_snapshot_id":baseline["id"], "price_change_pct":"10"}, expected=422)
        with client.open(Request(BASE+"/api/backend/"+run_route+"/export", headers={"Origin":BASE}), timeout=30) as exported:
            assert "attachment" in exported.headers["Content-Disposition"]
            csv_data = exported.read().decode()
            assert "HYPOTHETICAL SIMULATION" in csv_data and run["baseline_hash"] in csv_data
        no_mutation = call(path+f"/twin/current?start={period['start']}&end={period['end']}")["state"]["source_versions"]
        assert no_mutation == baseline["state"]["source_versions"]
        order = call(path+"/orders")["items"][0]
        call(path+"/orders/"+order["id"], "PATCH", {"status":"refunded", "reason":"Twin HTTP regression"})
        add("inventory", [{"external_id":"M1", "product_sku":"P1", "occurred_on":end.isoformat(), "quantity_delta":"-3", "reason":"sale"}])
        after = call(path+"/twin/snapshots", "POST", period|{"name":"After correction"}, 201)
        assert call(route) == saved
        assert call(run_route) == run
        current = call(path+f"/twin/current?start={period['start']}&end={period['end']}")
        assert current["state"]["metrics"]["revenue"] == "0.00"
        assert current["state"]["inventory_value"] == "68.00"
        result = call(path+f"/twin/compare?left={baseline['id']}&right={after['id']}")
        assert Decimal(result["metrics"]["revenue"]["absolute_change"]) == Decimal("-28")
        assert result["metrics"]["revenue"]["percentage_change"] == "-100.00"
        assert set(result["source_changes"]) >= {"orders","inventory","balances"}
        call(path+"/twin/snapshots", "POST", {"name":"Bad dates", "start":period["end"], "end":period["start"]}, 422)
        call("auth/logout", "POST", expected=204)
        report = {"status":"passed", "checks":["real frontend proxy", "explicit preview confirmation", "stale preview rejection", "elasticity arithmetic", "sensitivity cases", "zero-change baseline", "replenishment cash separation", "unchanged operational source versions", "CSV export", "tenant isolation", "saved simulation replay after refund", "scenario comparison"], "comparison":result}
        folder = Path(__file__).resolve().parents[1]/".local"
        folder.mkdir(exist_ok=True)
        (folder/"phase7-http-report.json").write_text(json.dumps(report, indent=2))
        print("Simulation HTTP acceptance passed: reviewed assumptions, elasticity, sensitivity, unchanged records, cash separation, CSV, tenant isolation, comparisons and replay.")
    finally:
        with Session(get_engine()) as db:
            owned = db.scalars(select(User).where(User.id.in_(users))).all()
            assert all(user.email == prefix+"@example.com" for user in owned)
            memberships = db.scalars(select(Membership.business_id).where(Membership.business_id.in_(businesses), Membership.user_id.in_(users), Membership.role=="owner")).all()
            assert set(memberships) == set(businesses), "Could not verify cleanup ownership"
            db.execute(delete(AuditLog).where(AuditLog.user_id.in_(users)))
            db.execute(delete(Business).where(Business.id.in_(businesses)))
            db.execute(delete(User).where(User.id.in_(users)))
            db.commit()
        print("Removed only this acceptance check's temporary account and businesses.")


if __name__ == "__main__":
    main()
