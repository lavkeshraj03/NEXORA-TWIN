"""Live scanned-PDF OCR and optional owned Ollama outage/recovery acceptance."""
import argparse
import io
import json
import os
import secrets
import signal
import subprocess
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID, uuid4

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import AuditLog, Business, Membership, User

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:3000"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-owned-provider-outage", action="store_true", help="Briefly stop/restart only the Ollama PID created by scripts/start_local_ai.sh")
    options = parser.parse_args()
    fixture = ROOT/".local/scanned-policy.pdf"
    if not fixture.exists():
        subprocess.run([str(ROOT/".local/nexora-ocr"), "--fixture", str(fixture)], check=True)
    raw = fixture.read_bytes()
    assert not PdfReader(io.BytesIO(raw)).pages[0].extract_text().strip(), "Fixture must require OCR"
    prefix = "nexora-ocr-"+uuid4().hex
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    users, businesses, csrf, stopped = [], [], None, False
    report = {"completed": False, "image_only_fixture": True, "checks": [], "registration_count": 0}

    def call(path, method="GET", body=None, data=None, expected=200):
        headers = {"Origin": BASE}
        if csrf: headers["X-CSRF-Token"] = csrf
        if body is not None: data = json.dumps(body).encode()
        if data is not None: headers["Content-Type"] = "application/json" if body is not None else "application/pdf"
        try:
            response = client.open(Request(BASE+"/api/backend/"+path, method=method, headers=headers, data=data), timeout=300)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            assert response.code == expected, f"{path}: {response.code}: {content[:300]!r}"
            return json.loads(content) if content else None

    try:
        account = call("auth/register", "POST", {"name": "Local OCR check", "email": prefix+"@example.com", "password": secrets.token_urlsafe(32)}, expected=201)
        users.append(UUID(account["user"]["id"]))
        report["registration_count"] = 1
        csrf = account["csrf_token"]
        business = call("businesses", "POST", {"name": "Temporary scanned PDF verification", "business_type": "retail", "country": "IN", "currency": "INR", "timezone": "Asia/Kolkata"}, expected=201)
        businesses.append(UUID(business["id"]))
        path = "businesses/"+business["id"]
        version = call(path+"/documents?"+urlencode({"filename": "scanned-policy.pdf", "title": "Scanned warranty fixture"}), "POST", data=raw, expected=202)
        deadline = time.monotonic()+200
        while time.monotonic() < deadline:
            document = call(path+"/documents")[0]
            current = document["versions"][0]
            if current["status"] == "ready": break
            assert current["status"] not in {"failed", "awaiting_configuration"}, current
            time.sleep(0.5)
        assert current["status"] == "ready", current
        chunks = call(path+f"/documents/{version['document_id']}/versions/{version['id']}/chunks")
        assert chunks[0]["page"] == 1 and "twelve months" in chunks[0]["content"].lower()
        report["actual_ocr_text"] = chunks[0]["content"]
        report["checks"].append("Image-only PDF -> macOS OCR -> worker embedding -> pgvector ready")
        question = {"question": "How long does the warranty last?", "document_ids": [version["document_id"]]}

        def verify_answer():
            answer = call(path+"/rag/ask", "POST", question)
            assert any(term in answer["answer"].lower() for term in ["twelve months", "12 months"]), answer
            assert answer["citations"] and answer["citations"][0]["page"] == 1
            assert answer["citations"][0]["excerpt"] in chunks[0]["content"]
            return answer

        report["answer"] = verify_answer()
        report["checks"].append("Local grounded answer cites actual OCR text and page 1")
        if options.test_owned_provider_outage:
            pid = int((ROOT/".local/ollama.pid").read_text())
            command = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True).strip()
            assert command == "ollama serve" or command.endswith("/ollama serve"), "Refusing to signal a PID not identified as the owned Ollama service"
            os.kill(pid, signal.SIGTERM)
            stopped = True
            time.sleep(1)
            failure = call(path+"/rag/ask", "POST", question, expected=503)
            assert "error" in failure and "answer" not in failure
            report["outage_response"] = failure
            report["checks"].append("Provider outage returns 503 with no fabricated answer")
            subprocess.run(["sh", str(ROOT/"scripts/start_local_ai.sh")], check=True)
            stopped = False
            report["recovery_answer"] = verify_answer()
            report["checks"].append("Owned local provider restarted and grounded answers recovered")
        report["completed"] = True
        print("Local OCR/outage checks passed:", report["checks"], flush=True)
    except Exception as error:
        report["error"] = str(error)[:1000]
        raise
    finally:
        if stopped:
            subprocess.run(["sh", str(ROOT/"scripts/start_local_ai.sh")], check=True)
        with Session(get_engine()) as db:
            owned = db.scalars(select(User).where(User.id.in_(users))).all()
            assert all(user.email == prefix+"@example.com" for user in owned)
            memberships = db.scalars(select(Membership.business_id).where(Membership.business_id.in_(businesses), Membership.user_id.in_(users), Membership.role == "owner")).all()
            assert set(memberships) == set(businesses)
            db.execute(delete(AuditLog).where(AuditLog.user_id.in_(users)))
            db.execute(delete(Business).where(Business.id.in_(businesses)))
            db.execute(delete(User).where(User.id.in_(users)))
            db.commit()
        report["temporary_records_removed"] = True
        (ROOT/".local/phase4-ocr-report.json").write_text(json.dumps(report, indent=2))
        print("Removed only this run's temporary records. Report: .local/phase4-ocr-report.json", flush=True)


if __name__ == "__main__":
    main()
