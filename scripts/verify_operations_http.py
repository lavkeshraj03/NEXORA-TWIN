"""Verify imports through Next.js and remove only this run's temporary records.

Run from backend with PYTHONPATH=. python ../scripts/verify_operations_http.py.
Requires the local Compose stack and the backend test dependencies.
"""
import io
import json
import secrets
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID, uuid4

from openpyxl import Workbook
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import AuditLog, Business, Membership, User

BASE = "http://localhost:3000"


def main():
    prefix = "nexora-operations-" + uuid4().hex
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    users, businesses = [], []
    csrf = None

    def call(path, method="GET", body=None, expected=200, raw=None):
        headers = {"Origin": BASE}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if raw is not None:
            data = raw
            headers["Content-Type"] = "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        else:
            data = None
        request = Request(BASE + "/api/backend/" + path, method=method, headers=headers, data=data)
        try:
            response = client.open(request, timeout=65)
        except HTTPError as failure:
            response = failure
        with response:
            content = response.read()
            assert response.code == expected, f"{method} {path}: {response.code}: {content[:300]!r}"
            if "text/csv" in response.headers.get("Content-Type", ""):
                assert "attachment" in response.headers.get("Content-Disposition", "")
                return content.decode()
            return json.loads(content) if content else None

    def upload(path, resource, filename, raw):
        batch = call(path + "/imports?" + urlencode({"resource": resource, "filename": filename}), "POST", raw=raw)
        assert batch["error_count"] == 0, batch["errors"]
        assert batch["status"] == "validated"
        assert call(path + "/" + resource)["total"] == 0, "Upload committed without confirmation"
        confirm = {"confirmed": True, "preview_updated_at": batch["updated_at"]}
        result = call(path + f"/imports/{batch['id']}/commit", "POST", confirm)
        assert result["status"] == "committed"
        assert call(path + f"/imports/{batch['id']}/commit", "POST", confirm)["imported_count"] == result["imported_count"]
        return result

    try:
        account = call("auth/register", "POST", {"name": "Operations HTTP check", "email": prefix + "@example.com", "password": secrets.token_urlsafe(32)}, expected=201)
        users.append(UUID(account["user"]["id"]))
        csrf = account["csrf_token"]
        for name in ["Import verification", "Isolated verification"]:
            business = call("businesses", "POST", {"name": name, "business_type": "retail", "country": "IN", "currency": "INR", "timezone": "Asia/Kolkata"}, expected=201)
            businesses.append(UUID(business["id"]))
        path, isolated = ["businesses/" + str(value) for value in businesses]
        upload(path, "customers", "customers.csv", b"external_id,name,is_demo\nC1,Example,true\n")
        book = Workbook()
        book.active.append(["sku", "name", "unit_price", "unit_cost", "initial_stock", "is_demo"])
        book.active.append(["P1", "Example", "10.00", "4.00", "20", "true"])
        buffer = io.BytesIO()
        book.save(buffer)
        upload(path, "products", "products.xlsx", buffer.getvalue())
        upload(path, "orders", "orders.csv", b"external_id,ordered_on,customer_external_id,product_sku,quantity,unit_price,unit_cost,discount_amount,tax_amount,is_demo\nO1,2026-10-10,C1,P1,3,10,4,2,3,true\n")
        upload(path, "expenses", "expenses.csv", b"external_id,incurred_on,category,amount,is_demo\nE1,2026-10-10,rent,5.50,true\n")
        dates = "?start=2026-10-01&end=2026-10-31"
        report = call(path + "/dashboard" + dates)
        assert report["metrics"]["revenue"] == "28.00"
        assert report["metrics"]["gross_profit"] == "16.00"
        assert report["inventory"]["value"] == "80.00"
        assert report["metrics"]["operating_profit"] is None
        call(path + "/expense-coverage", "PUT", {"start_date": "2026-10-01", "end_date": "2026-10-31", "complete": True})
        assert call(path + "/dashboard" + dates)["metrics"]["operating_profit"] == "10.50"
        assert call(isolated + "/dashboard" + dates)["metrics"]["revenue"] == "0.00"
        batch = call(path + "/imports")[0]
        call(isolated + f"/imports/{batch['id']}", expected=404)
        assert "C1" in call(path + "/customers/export")
        assert len(call(path + "/transactions")["items"]) == 2
        bad = call(path + "/imports?resource=customers&filename=invalid.csv", "POST", raw=b"external_id,name,email\nC2,Bad,invalid\n")
        assert bad["error_count"] == 1
        call(path + f"/imports/{bad['id']}/commit", "POST", {"confirmed": True, "preview_updated_at": bad["updated_at"]}, expected=409)
        assert "email" in call(path + f"/imports/{bad['id']}/errors")
        assert call(path + "/customers")["total"] == 1
        status = call(path + "/rag/status")
        version = call(path + "/documents?" + urlencode({"filename": "policy.txt", "title": "HTTP returns policy"}), "POST", raw=b"Returns are accepted within thirty days.", expected=202)
        for _ in range(60):
            document = next(item for item in call(path + "/documents") if item["id"] == version["document_id"])
            processed = document["versions"][0]
            if processed["status"] not in {"queued", "extracting", "indexing"}:
                break
            time.sleep(0.25)
        assert processed["status"] in {"ready", "awaiting_configuration"}, processed
        chunks = call(path + f"/documents/{version['document_id']}/versions/{version['id']}/chunks")
        assert chunks[0]["content"] == "Returns are accepted within thirty days."
        call(isolated + f"/documents/{version['document_id']}/versions/{version['id']}/chunks", expected=404)
        if status["embeddings_configured"] and status["chat_configured"]:
            answer = call(path + "/rag/ask", "POST", {"question": "What is the return policy?"})
            assert answer["citations"] and answer["citations"][0]["document_id"] == version["document_id"]
        else:
            call(path + "/rag/ask", "POST", {"question": "What is the return policy?"}, expected=503)
        print("Document HTTP passed: saved upload, background extraction, actual source preview, tenant isolation, explicit provider readiness.")
        call("auth/logout", "POST", expected=204)
        print("Operations HTTP passed: CSV/XLSX preview, explicit confirmation, idempotency, actual dashboard totals, stock, expense completeness, tenant isolation, CSV exports, atomic rejection, logout.")
    finally:
        with Session(get_engine()) as db:
            owned = db.scalars(select(User).where(User.id.in_(users))).all()
            assert all(user.email == prefix + "@example.com" for user in owned)
            memberships = db.scalars(select(Membership.business_id).where(Membership.business_id.in_(businesses), Membership.user_id.in_(users), Membership.role == "owner")).all()
            assert set(memberships) == set(businesses), "Cleanup ownership could not be verified"
            db.execute(delete(AuditLog).where(AuditLog.user_id.in_(users)))
            db.execute(delete(Business).where(Business.id.in_(businesses)))
            db.execute(delete(User).where(User.id.in_(users)))
            db.commit()
        print("Removed only this check's temporary account and businesses.")


if __name__ == "__main__":
    main()
