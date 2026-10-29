"""Run only via verify_fresh_install.py --all-flows against its disposable stack."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from urllib.request import urlopen

from redis import Redis
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.security import token_digest
from app.db.session import get_engine
from app.models import User, Business


def main():
    root = Path(__file__).resolve().parents[1]
    project = os.environ.get("NEXORA_ISOLATED_PROJECT", "")
    assert re.fullmatch(r"nexora-acceptance-[0-9a-f]{12}", project), "An owned disposable project is required"
    assert os.environ["REDIS_URL"] == "redis://127.0.0.1:56380/0"
    assert os.environ["DATABASE_URL"].endswith("@127.0.0.1:55433/acceptance")
    base = os.environ["NEXORA_BASE_URL"]
    assert base == "http://localhost:3001"
    compose = json.loads(os.environ["NEXORA_COMPOSE_COMMAND"])
    ip = subprocess.check_output(["docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", project + "-frontend-1"], text=True).strip()
    assert re.fullmatch(r"[0-9.]+", ip)
    registration_key = "nexora:auth:" + token_digest("register:" + ip)
    output = root / ".local/e2e"
    output.mkdir(parents=True, exist_ok=True)
    browser_only = os.getenv("NEXORA_E2E_BROWSER_ONLY") == "1"
    result = {"status": "failed", "project": project, "mode": "browser_only" if browser_only else "all_flows", "workflows": [],
              "rate_limit_handling": "Only the exact frontend registration counter in this disposable Redis is cleared between independent workflows; production Redis is untouched."}
    fault_name = project + "-fault"
    failures = []
    try:
        subprocess.run(compose + ["run", "--no-deps", "-d", "--name", fault_name,
                                 "-e", "AI_BASE_URL=http://127.0.0.1:9", "-p", "127.0.0.1:8002:8000", "backend"], check=True)
        for attempt in range(60):
            try:
                with urlopen("http://localhost:8002/api/v1/health/ready", timeout=2) as response:
                    assert response.status == 200
                break
            except Exception:
                if attempt == 59:
                    raise
                time.sleep(0.5)
        os.environ["NEXORA_ANALYST_FAULT_BASE"] = "http://localhost:8002"
        receipts = {"rag": "phase4-live-report.json", "local_ocr": "phase4-ocr-report.json",
                    "twin": "phase6-http-report.json", "simulation": "phase7-http-report.json",
                    "analyst": "phase8-http-report.json", "insights": "phase9-http-report.json"}
        workflows = [] if browser_only else ["identity", "operations", "rag", "local_ocr", "ml", "twin", "simulation", "analyst", "insights"]
        for name in workflows:
            with Redis.from_url(os.environ["REDIS_URL"]) as redis:
                redis.delete(registration_key)
            begun = time.monotonic()
            row = {"name": name, "status": "failed"}
            print("START workflow:", name, flush=True)
            try:
                source = root / "scripts" / ("verify_" + name + "_http.py")
                spec = importlib.util.spec_from_file_location("e2e_" + name, source)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.BASE = base
                previous = sys.argv
                sys.argv = [str(source)]
                try:
                    module.main()
                finally:
                    sys.argv = previous
                with Session(get_engine()) as db:
                    assert db.scalar(select(func.count()).select_from(User)) == 0, "Workflow leaked an account"
                    assert db.scalar(select(func.count()).select_from(Business)) == 0, "Workflow leaked a business"
                row["status"] = "passed"
                if name in receipts:
                    receipt = root / ".local" / receipts[name]
                    (output / (name + ".json")).write_bytes(receipt.read_bytes())
            except Exception as error:
                row["error"] = str(error)[:1500]
                failures.append(name)
                print("FAIL workflow:", name, type(error).__name__, str(error)[:500], flush=True)
            row["seconds"] = round(time.monotonic() - begun, 2)
            result["workflows"].append(row)
            (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
            print("END workflow:", name, row["status"], row["seconds"], "seconds", flush=True)

        with Redis.from_url(os.environ["REDIS_URL"]) as redis:
            redis.delete(registration_key)
        with tempfile.TemporaryDirectory(prefix="nexora-e2e-data-") as folder:
            subprocess.run([sys.executable, str(root / "scripts/seed_nexa_demo.py"), "--generate-only", "--data-dir", folder,
                            "--end", (date.today() - timedelta(days=1)).isoformat()], check=True, stdout=subprocess.DEVNULL)
            env = os.environ.copy()
            env["NEXORA_BROWSER_DATA_DIR"] = folder
            browser = subprocess.run(["node", str(root / "scripts/verify_journey_browser.cjs")], env=env)
            if browser.returncode:
                failures.append("browser_journey")
            else:
                from pypdf import PdfReader
                receipt = json.loads((output / "browser-journey.json").read_text())
                directory = Path(receipt["downloadDirectory"])
                pdfs = list(directory.glob("*.pdf"))
                csvs = list(directory.glob("*.csv"))
                assert len(pdfs) == 7 and len(csvs) == 7, "Missing report downloads"
                for pdf in pdfs:
                    reader = PdfReader(pdf, strict=True)
                    assert reader.pages and "NEXORA TWIN" in "\n".join(page.extract_text() for page in reader.pages)
                result["report_downloads"] = {"strictly_parsed_pdfs": len(pdfs), "csv_files": len(csvs)}
        result["status"] = "passed" if not failures else "failed"
        result["failures"] = failures
    finally:
        subprocess.run(["docker", "rm", "--force", fault_name], stdout=subprocess.DEVNULL)
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    if failures:
        raise RuntimeError("End-to-end failures: " + ", ".join(failures))
    print("Browser journey and report downloads passed." if browser_only else "All live workflows and the browser journey passed.", flush=True)


if __name__ == "__main__":
    main()
