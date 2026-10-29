"""Real Next.js -> API -> PostgreSQL model lifecycle check, with owned-record cleanup."""
import csv
import io
import json
import secrets
from datetime import date, timedelta
from decimal import Decimal
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import AuditLog, Business, Membership, User

BASE = "http://localhost:3000"


def main():
    prefix = "nexora-ml-http-"+uuid4().hex
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    users, businesses = [], []
    csrf = None

    def call(path, method="GET", body=None, expected=200, raw=None):
        headers = {"Origin": BASE}
        if csrf: headers["X-CSRF-Token"] = csrf
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        if data is not None: headers["Content-Type"] = "application/octet-stream" if raw is not None else "application/json"
        try:
            response = client.open(Request(BASE+"/api/backend/"+path, method=method, headers=headers, data=data), timeout=65)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            assert response.code == expected, f"{method} {path}: {response.code}: {content[:350]!r}"
            return json.loads(content) if content else None

    def add(path, resource, rows):
        return call(path+"/"+resource, "POST", {"rows": rows}, expected=201)

    def import_orders(path, raw):
        batch = call(path+"/imports?"+urlencode({"resource":"orders", "filename":"model-history.csv"}), "POST", raw=raw)
        assert batch["error_count"] == 0, batch["errors"]
        return call(path+f"/imports/{batch['id']}/commit", "POST", {"confirmed":True, "preview_updated_at":batch["updated_at"]})

    try:
        identity = call("auth/register", "POST", {"name":"ML HTTP check", "email":prefix+"@example.com", "password":secrets.token_urlsafe(32)}, expected=201)
        users.append(UUID(identity["user"]["id"]))
        csrf = identity["csrf_token"]
        for name in ["Forecast HTTP check", "Churn HTTP check"]:
            business = call("businesses", "POST", {"name":name, "business_type":"retail", "country":"IN", "currency":"INR", "timezone":"Asia/Kolkata"}, expected=201)
            businesses.append(UUID(business["id"]))
        path, other = ["businesses/"+str(value) for value in businesses]
        add(path, "customers", [{"external_id":f"C{index}", "name":"Demonstration customer", "is_demo":True} for index in (1,2)])
        add(path, "products", [{"sku":"P1", "name":"Demonstration notebook", "unit_price":"120", "unit_cost":"65", "initial_stock":"100", "is_demo":True}])
        raw = (Path(__file__).resolve().parents[1]/"datasets/forecasting/orders.csv").read_bytes()
        assert import_orders(path, raw)["imported_count"] == 140
        training = {"task":"sales", "start":"2026-06-11", "end":"2026-10-28", "aggregation":"daily", "horizon":7, "data_scope":"demo", "coverage_confirmed":True}
        run = call(path+"/ml/forecasts", "POST", training, expected=201)
        assert len(run["history"]) == 140 and run["history"][0]["value"] == "600.00"
        assert run["source_count"] == 140 and len(run["result"]["candidates"]) == 2
        model_path = path+"/ml/runs/"+run["id"]
        assert call(model_path+"/predict", "POST", {"horizon":7})["forecast"] == run["result"]["forecast"]
        assert call(model_path+"/monitor")["source_changed"] is False
        call(other+"/ml/runs/"+run["id"], expected=404)
        assert call(model_path+"/activate", "POST")["active"] is True
        demand = call(path+"/ml/forecasts", "POST", training|{"task":"demand", "product_sku":"P1"}, expected=201)
        assert demand["history"][0]["value"] == "5.000"
        risk = call(path+"/ml/inventory-risk?product_sku=P1&lead_days=30&data_scope=demo")
        assert risk["calculation_type"] == "deterministic_inventory_risk" and risk["current_stock"] == "100.000"
        record = call(path+"/orders?search=FC0001")["items"][0]
        call(path+"/orders/"+record["id"], "PATCH", {"status":"refunded", "reason":"HTTP model source correction"})
        assert call(model_path+"/monitor")["source_changed"] is True
        assert call(model_path)["history"][0]["value"] == "600.00"
        assert call(model_path+"/sources?limit=1")["items"][0]["net_sales"] == "600.0000"
        # A separate tenant gets a small labelled customer/outcome history.
        add(other, "customers", [{"external_id":f"CH{index}", "name":"Demonstration customer", "is_demo":True} for index in range(80)])
        add(other, "products", [{"sku":"P1", "name":"Demonstration service", "unit_price":"10", "is_demo":True}])
        rows = []
        end = date(2026,10,28)
        for index in range(80):
            days = [end-timedelta(days=61+index%10)]
            if index < 40: days.append(end-timedelta(days=53))
            if index%2 == 0: days.append(end-timedelta(days=23))
            for number, day in enumerate(days):
                rows.append({"external_id":f"CH{index}-{number}", "ordered_on":day.isoformat(), "customer_external_id":f"CH{index}", "product_sku":"P1", "quantity":"1", "unit_price":"10", "is_demo":"true"})
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        import_orders(other, stream.getvalue().encode())
        churn = call(other+"/ml/churn", "POST", {"end":end.isoformat(), "inactivity_days":30, "data_scope":"demo", "coverage_confirmed":True}, expected=201)
        assert churn["result"]["evaluation"]["observations"] == 80 and len(churn["result"]["predictions"]) == 80
        call(path+"/ml/runs/"+churn["id"], expected=404)
        call("auth/logout", "POST", expected=204)
        print("ML HTTP passed: imported history, chronological sales/demand evaluation, JSON artifact replay, explicit activation, inventory calculation, source drift, churn metrics/estimates and tenant isolation.")
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
        print("Removed only this ML check's temporary account and businesses.")


if __name__ == "__main__":
    main()
