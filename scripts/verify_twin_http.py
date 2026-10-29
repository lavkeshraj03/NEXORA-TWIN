"""Live Next.js → API → PostgreSQL twin acceptance with owned-record cleanup."""
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
    prefix = "nexora-twin-http-"+uuid4().hex
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
        order = call(path+"/orders")["items"][0]
        call(path+"/orders/"+order["id"], "PATCH", {"status":"refunded", "reason":"Twin HTTP regression"})
        add("inventory", [{"external_id":"M1", "product_sku":"P1", "occurred_on":end.isoformat(), "quantity_delta":"-3", "reason":"sale"}])
        after = call(path+"/twin/snapshots", "POST", period|{"name":"After correction"}, 201)
        assert call(route) == saved
        current = call(path+f"/twin/current?start={period['start']}&end={period['end']}")
        assert current["state"]["metrics"]["revenue"] == "0.00"
        assert current["state"]["inventory_value"] == "68.00"
        result = call(path+f"/twin/compare?left={baseline['id']}&right={after['id']}")
        assert Decimal(result["metrics"]["revenue"]["absolute_change"]) == Decimal("-28")
        assert result["metrics"]["revenue"]["percentage_change"] == "-100.00"
        assert set(result["source_changes"]) >= {"orders","inventory","balances"}
        call(path+"/twin/snapshots", "POST", {"name":"Bad dates", "start":period["end"], "end":period["start"]}, 422)
        call("auth/logout", "POST", expected=204)
        report = {"status":"passed", "checks":["real frontend proxy", "authenticated capture", "Decimal totals", "source inspection", "tenant isolation", "immutable replay after correction", "current state", "comparison", "invalid date rejection"], "comparison":result}
        folder = Path(__file__).resolve().parents[1]/".local"
        folder.mkdir(exist_ok=True)
        (folder/"phase6-http-report.json").write_text(json.dumps(report, indent=2))
        print("Twin HTTP acceptance passed: saved states, reproducible old evidence, current calculations, comparison, tenant denial and date validation.")
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
