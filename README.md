# NEXORA TWIN

**Understand Your Business. Simulate Your Future.**

A local multi-business decision intelligence MVP built with Next.js, FastAPI, PostgreSQL/pgvector, Redis/RQ and small local Ollama models. The original brief is in [product requirements](docs/product-requirements.txt). See [progress and measured verification](docs/progress.md).

## Start the application

For a fresh checkout, create .env as below. Preserve an existing .env and its database volumes during upgrades.

Install Docker Desktop with Compose v2. Use Node 22 and Python 3.12+ for native development. Leave several GB of disk space and RAM available; the application and local models share this laptop.

```sh
cp .env.example .env
# Edit .env and set a unique POSTGRES_PASSWORD before initializing PostgreSQL.
docker compose up --build -d
docker compose ps
python3 scripts/validate_environment.py
```

Open **http://localhost:3000/login**. Register, create an empty business and select its currency/timezone. A teammate registers their own account before an owner adds them in Team. No invitation email is sent. API documentation: http://localhost:8000/api/docs in development.

Ports 3000, 8000, 55432 and 56379 bind only to loopback. FRONTEND_PORT, BACKEND_PORT, POSTGRES_PORT and REDIS_PORT can change host ports; update ALLOWED_ORIGINS when changing the browser origin. Compose applies migrations before starting the API. Stop using `docker compose down`; persisted volumes remain. Do not remove volumes to troubleshoot.

## Local AI on this Mac

The verified profile uses **qwen3:1.7b** for answers and **qwen3-embedding:0.6b** for indexing/retrieval. It requires no paid API or fine-tuning. Install these models in native Ollama and set the AI variables described in [local AI setup](docs/local-ai.md), then:

```sh
sh scripts/start_local_ai.sh
sh scripts/start_local_ocr.sh
docker compose up -d backend worker frontend
```

The OCR helper uses macOS Vision; it is not a Linux-container service. Native helpers must be started again after reboot. The API and worker must use the same provider URL/model settings. Changing provider identity requires explicit document re-indexing. If AI is unavailable, document answers and analyst investigations report the failure; dashboards, numerical models, snapshots, scenarios and existing ordinary reports continue to work.

## Use Nexa demonstration data

Your existing **Nexa** business already contains explicitly labelled synthetic operational data, documents, models, snapshots, scenarios, investigations and seven reports. Sign in with your existing account and select Nexa. See the [Nexa walkthrough](docs/nexa-demo-guide.md). Choose **29 September–28 October 2026** to reproduce the loaded financial example: revenue INR 150,562; gross profit INR 69,012; recorded expenses INR 26,300; operating profit INR 42,712.

Try these screens in order:

1. **Overview / Data explorer:** inspect totals and the records behind them.
2. **Documents & answers:** select the returns policy and ask how long a customer has to return an item; inspect its citation.
3. **Forecasts & risk:** inspect saved demo models and their evaluation; use the labelled demonstration scope.
4. **Digital twin / What-If Lab:** open the October baseline, inspect sources and compare the saved price-change assumptions.
5. **AI analyst:** review an existing investigation and its calculated/document evidence.
6. **Knowledge graph:** search a SKU and inspect stored relationships and source records.
7. **Reports & exports:** open one of the seven saved reports and download its CSV or PDF.

Other accounts and businesses start empty. Use Import data to upload, map, validate and explicitly confirm records. For a fresh demo, use a separate empty INR retail business; the guarded loader refuses to mix records into a nonempty business. Instructions are in [deployment and demo setup](docs/deployment.md).

## Verify or develop

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -c backend/requirements.lock -e './backend[test]'
cd backend
.venv/bin/alembic upgrade head
RUN_INTEGRATION=1 .venv/bin/python -m pytest -q
.venv/bin/alembic check
```

From `frontend/`, run `npm ci`, `npm test`, `npm run typecheck` and `npm run build`. Native API development uses `uvicorn app.main:app --host 127.0.0.1 --port 8000`; frontend development uses `npm run dev`. Keep the RQ worker in Docker on macOS. Native database/Redis URLs must use host ports; Compose services use internal hostnames.

After building the Compose images, run the isolated release acceptance from the repository root:

```sh
backend/.venv/bin/python scripts/verify_fresh_install.py
```

This requires Docker access, free ports 3001/8001/55433/56380, backend test dependencies and configured local AI. It creates a randomly named separate project, migrates empty volumes, runs the backend suite and real HTTP graph/report/PDF checks, loads synthetic data twice, trains saved numerical models, indexes documents and checks live cited answers. It removes only its own temporary project and writes a receipt under `.local/`. It does not reset Nexa. Optional NEXORA_TEST_BACKEND points to a local source copy if macOS Desktop offloading stalls reads.

With Chrome installed, `node scripts/verify_browser.cjs` checks login/home keyboard navigation, accessibility-tree landmarks and mobile overflow. Set CHROME_BIN for a different Chrome/Chromium binary, or NEXORA_BASE_URL for another local frontend. Screenshots and a receipt are written to .local/. This is limited browser coverage, not a WCAG audit.

## Documentation and limits

[Architecture](docs/architecture.md), [API reference](docs/api-reference.md), [database schema](docs/database-schema.md), [security](docs/security.md), [deployment/recovery](docs/deployment.md), [forecasting](docs/forecasting-api.md), [snapshots](docs/digital-twin-api.md), [simulation methodology](docs/simulation-methodology.md), [analyst](docs/analyst-api.md), [graph/reports](docs/graph-reports-api.md).

This release is a local MVP. It does not claim enterprise production readiness, independently validated model accuracy, universal document understanding or complete industry ERP modules. Review evidence and model limitations before decisions. Production requires TLS, least-privilege database roles, operational backups/restore, retention, content isolation/antivirus, broader accessibility and load/security evaluation. PDF text uses standard fonts with escaped fallback for unsupported Unicode; CSV preserves Unicode.

## Complete start-to-finish acceptance

After building the app images and configuring local AI/OCR, run from the repository root:

```sh
backend/.venv/bin/python scripts/verify_fresh_install.py --all-flows
```

This starts a disposable installation, runs the complete backend suite, then verifies identity/team access, imports and financial totals, all five document formats, scanned-PDF OCR, local cited answers, sales/demand/inactivity models, snapshots, scenarios, analyst evidence/failures, graph relationships and report exports through the real frontend proxy. Chrome then exercises a continuous authenticated browser journey, including six CSV confirmations, training, snapshot/scenario comparisons, all seven CSV/PDF report downloads, settings, tenant switching, team permissions, mobile layout and logout/relogin.

Requires an installed Chrome/Chromium binary (CHROME_BIN can override its path), native Node 22+, configured real local AI/OCR and free acceptance ports 3001/8001/8002/55433/56380. Tests use synthetic data and remove only their own isolated project. The exact registration counter in that disposable Redis is cleared between independent workflows; the main application's Redis is untouched. Receipts/screenshots/downloads are written under .local/e2e/. A browser-only rerun is available with --browser-only.
