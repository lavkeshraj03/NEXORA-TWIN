"""Verify locally built images in an isolated Compose project; never reset the main app.

Run with the backend test environment's Python after building the four app images.
Requires Docker, python-dotenv, backend test dependencies and configured local AI.
Temporary containers/volumes belong only to a randomly named acceptance project.
"""
import json
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from http.cookiejar import CookieJar
from urllib.request import Request, HTTPCookieProcessor, build_opener

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-flows", action="store_true", help="Also run every live workflow and the authenticated browser journey")
    parser.add_argument("--browser-only", action="store_true", help="Run only the authenticated browser journey in a fresh disposable stack")
    options = parser.parse_args()
    if options.browser_only:
        options.all_flows = True
    root = Path(__file__).resolve().parents[1]
    project = "nexora-acceptance-" + secrets.token_hex(6)
    configuration = dotenv_values(root / ".env")
    result = {"project": project, "status": "failed", "checks": []}
    output = root / ".local" / ("e2e-install.json" if options.all_flows else "phase10-fresh-install.json")
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=project + "-") as temporary:
        folder = Path(temporary)
        settings = {key: str(value) for key, value in configuration.items()
                    if value is not None and (key.startswith("AI_") or key.startswith("OCR_") or key.startswith("DOCUMENT_CHUNK_"))}
        settings.update(ENVIRONMENT="test", POSTGRES_USER="nexora",
                        POSTGRES_PASSWORD=secrets.token_hex(24), POSTGRES_DB="acceptance",
                        POSTGRES_PORT="55433", REDIS_PORT="56380", BACKEND_PORT="8001",
                        FRONTEND_PORT="3001", ALLOWED_ORIGINS='["http://localhost:3001"]')
        env = os.environ.copy()
        env.update(settings)
        env_file = folder / ".env"
        env_file.touch(mode=0o600)
        env_file.write_text("\n".join(key + "=" + value for key, value in settings.items()) + "\n")
        override = folder / "images.yml"
        override.write_text("services:\n" + "".join(
            f"  {service}:\n    image: nexora-twin-{service}\n"
            for service in ["backend", "worker", "migrate", "frontend"]))
        compose = ["docker", "compose", "--project-name", project, "--env-file", str(env_file),
                   "-f", str(root / "docker-compose.yml"), "-f", str(override)]

        def run(command, **kwargs):
            subprocess.run(command, cwd=root, env=env, check=True, **kwargs)

        try:
            run(compose + ["config", "--quiet"])
            run(compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "180"])
            result["checks"].append("five healthy services and migration from an empty volume")
            run(compose + ["exec", "-T", "backend", "alembic", "check"])
            result["checks"].append("fresh schema has no model drift")
            env.update(DATABASE_URL="postgresql+psycopg://nexora:" + settings["POSTGRES_PASSWORD"] + "@127.0.0.1:55433/acceptance",
                       REDIS_URL="redis://127.0.0.1:56380/0", RUN_INTEGRATION="1",
                       NEXORA_BASE_URL="http://localhost:3001")
            # An optional local copy avoids macOS Desktop offloading delays.
            backend = Path(os.environ.get("NEXORA_TEST_BACKEND", str(root / "backend")))
            env["PYTHONPATH"] = str(backend)
            env["ALLOWED_ORIGINS"] = '["http://localhost:3000"]'
            if not options.browser_only:
                run([sys.executable, "-m", "pytest", "-q", "--tb=short", str(backend / "tests")])
            env["ALLOWED_ORIGINS"] = settings["ALLOWED_ORIGINS"]
            if not options.browser_only:
                result["checks"].append("complete backend suite on fresh PostgreSQL and Redis")
            if options.all_flows:
                env["NEXORA_ISOLATED_PROJECT"] = project
                env["NEXORA_COMPOSE_COMMAND"] = json.dumps(compose)
                if options.browser_only:
                    env["NEXORA_E2E_BROWSER_ONLY"] = "1"
                run([sys.executable, str(root / "scripts/verify_all_flows.py")])
                result["checks"].append("authenticated browser journey" if options.browser_only else "all live HTTP workflows and authenticated browser journey")
                result["status"] = "passed"
                return
            run([sys.executable, str(root / "scripts/verify_insights_http.py")])
            result["checks"].append("real frontend graph/report/PDF workflow and cross-business denial")

            client = build_opener(HTTPCookieProcessor(CookieJar()))
            def call(path, body, csrf=None):
                headers = {"Origin": env["NEXORA_BASE_URL"], "Content-Type": "application/json"}
                if csrf:
                    headers["X-CSRF-Token"] = csrf
                with client.open(Request(env["NEXORA_BASE_URL"] + "/api/backend/" + path,
                                         data=json.dumps(body).encode(), headers=headers), timeout=30) as response:
                    return json.load(response)
            identity = call("auth/register", {"email": project + "@example.com", "name": "Fresh demo owner",
                                             "password": secrets.token_urlsafe(32)})
            business = call("businesses", {"name": "Fresh Nexa demo", "business_type": "retail",
                                          "country": "IN", "currency": "INR", "timezone": "Asia/Kolkata"}, identity["csrf_token"])
            data = folder / "demo"
            seed = [sys.executable, str(root / "scripts/seed_nexa_demo.py"), "--data-dir", str(data)]
            run(seed + ["--generate-only", "--end", (date.today() - timedelta(days=1)).isoformat()])
            run(compose + ["cp", str(root / "scripts/seed_nexa_demo.py"), "backend:/tmp/nexora-seed.py"])
            run(compose + ["cp", str(data), "backend:/tmp/nexora-demo"])
            # Run inside the API container so its provider identity exactly matches
            # the worker's identity, including the configured provider URL.
            load = compose + ["exec", "-T", "-e", "PYTHONPATH=/app", "backend", "python", "/tmp/nexora-seed.py",
                              "--data-dir", "/tmp/nexora-demo", "--business-id", business["id"],
                              "--owner-id", identity["user"]["id"]]
            # Indexing uses the isolated RQ worker and real configured local models.
            run(load)
            run(load)
            result["checks"].append("synthetic demo import, repeat-safe reload, saved ML models, worker indexing and live cited answers")
            result["status"] = "passed"
        except Exception as error:
            result["status"] = "failed"
            result["failure_type"] = type(error).__name__
            raise
        finally:
            # Only this newly generated project's resources are eligible for cleanup.
            cleanup = subprocess.run(compose + ["down", "--volumes", "--remove-orphans"], cwd=root, env=env)
            result["cleanup"] = "passed" if cleanup.returncode == 0 else "failed"
            if cleanup.returncode:
                result["status"] = "cleanup_failed"
            output.write_text(json.dumps(result, indent=2) + "\n")
            if cleanup.returncode:
                raise RuntimeError("Acceptance project cleanup failed; see receipt for its exact name")
    print("Fresh-install verification passed; receipt: " + str(output))


if __name__ == "__main__":
    main()
