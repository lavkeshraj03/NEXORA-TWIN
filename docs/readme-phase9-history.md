# NEXORA TWIN

**Understand Your Business. Simulate Your Future.**

A phased implementation of a multi-business decision intelligence platform. The source brief is preserved in [docs/product-requirements.txt](docs/product-requirements.txt).

## Current release

Phases 1–9 provide a working Next.js/FastAPI/PostgreSQL workspace with registration, login/logout, server-side sessions, business creation and switching, configurable business profiles, team roles, audit history, mapped CSV/XLSX/JSON imports, operational records, actual financial dashboards, evaluated sales/demand/customer-inactivity models, inventory-risk diagnostics, health checks, migrations, and Docker services.

Open **http://localhost:3000/login**, create an account, and create a business. To add a teammate, have them register first, then add their email from the business's Team screen. No emails are sent. Each business starts empty. Open Import data to preview, map, validate, and explicitly confirm your records; Overview then shows calculated results. See [operational data](docs/operations-api.md) and [labelled demonstration datasets](datasets/README.md). The document library and cited answers are verified with local Ollama models and English macOS OCR. Open Forecasts & risk to train and inspect evaluated numerical models without an AI provider. [Forecasting API and limitations](docs/forecasting-api.md) explains history requirements, baseline comparison and explicit demonstration mode. Open Digital twin to capture reproducible business states, inspect saved source values and compare historical snapshots. See [Digital twin API and walkthrough](docs/digital-twin-api.md). Open What-If Lab for deterministic scenarios, reviewed assumptions, elasticity sensitivity, stock/cash calculations, scenario comparison and CSV reports. [Simulation methodology and walkthrough](docs/simulation-methodology.md) documents the formulas and limits. Open AI analyst for bounded investigations, cited calculated/document evidence, private history and review steps. See [analyst tools and usage](docs/analyst-api.md). Knowledge graph provides source-backed entity exploration; Reports & exports freezes financial, model, scenario and investigation reports with CSV/PDF downloads. [Graph/report API and walkthrough](docs/graph-reports-api.md) explains source selection and limits.

See [development progress](docs/progress.md) for verification and remaining limitations. The previous disk-space interruption has been resolved and dependencies restored.

## Quick start with Docker

Requirements: Docker Desktop/Engine with Compose v2, approximately 4 GB available RAM, and free local ports 3000, 8000, 55432, and 56379. Downloads require network access. Project database and Redis ports deliberately differ from common host installations.

```sh
cp .env.example .env
# Edit .env; change POSTGRES_PASSWORD before a non-local deployment.
docker compose up --build -d
docker compose ps
python3 scripts/validate_environment.py
```

Open http://localhost:3000. API documentation is at http://localhost:8000/api/docs. The frontend calls a same-origin Next.js route, which contacts FastAPI server-side. API_INTERNAL_URL is never sent to the browser.

Compose runs `alembic upgrade head` as a separate migration service before starting the API. Neither FastAPI nor the worker creates tables on startup. The worker processes versioned document extraction/indexing jobs. Registration and login require Redis because rate limiting fails closed when Redis is unavailable.

Stop without removing persisted data:

```sh
docker compose down
```

PostgreSQL and Redis use named volumes. Deleting these volumes deletes persisted data; do not use volume removal as routine troubleshooting.

## Development without application containers

Use Node.js 22 LTS or newer and Python 3.12 or newer. The Python and JavaScript dependencies are installed independently. PostgreSQL still requires the pgvector extension; ordinary PostgreSQL without this extension is insufficient.

```sh
cp .env.example .env
docker compose up -d postgres redis
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -c backend/requirements.lock -e './backend[test]'
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

In a third terminal, if testing the worker:

```sh
cd backend
.venv/bin/python -m app.worker
```

RQ's default process worker targets Linux containers. Use the Docker worker on macOS; the API and frontend can run natively.

## Verification

```sh
cd backend
.venv/bin/pytest -m 'not integration'
# Requires the configured real PostgreSQL, pgvector, migrations, and Redis:
RUN_INTEGRATION=1 .venv/bin/pytest -m integration
```

```sh
cd frontend
npm run typecheck
npm test
npm run build
```

Unit tests deliberately inject failures to validate readiness behavior. Only the integration test asserts real infrastructure connectivity. Skipped tests are not successful integration verification. [API contract](docs/api-reference.md), [architecture](docs/architecture.md), [deployment](docs/deployment.md), and [security](docs/security.md) describe the current release.

## Configuration

Copy `.env.example` to `.env`; the latter is ignored. `DATABASE_URL`, `REDIS_URL`, `ALLOWED_ORIGINS`, and `ENVIRONMENT` configure FastAPI. Compose overrides database and Redis hostnames with internal service names. `API_INTERNAL_URL` configures the Next.js server. POSTGRES_PASSWORD must be URL-safe because Compose constructs a connection URL from it; use a long random hexadecimal value.

Phase 4 document ingestion and retrieval code is available through Documents & answers. [Document setup and API](docs/documents-api.md) explains server-side embedding/chat and optional OCR configuration. No AI credentials are needed for Phase 3 or basic document extraction; this laptop now uses verified local Qwen models without an API key. Other deployments must configure and verify their own provider. Never put API keys in `NEXT_PUBLIC_*` variables. Demonstration CSV files are available under datasets/ for explicit import; nothing is seeded automatically. To provision a platform account, run from the repository root:

```sh
backend/.venv/bin/python scripts/create_admin.py --email admin@example.com --name Administrator
```

The command prompts for and confirms a password; no password goes in shell arguments. The platform flag grants no tenant access automatically. Use business creation or explicit team membership to access tenant records. Platform management screens are not implemented.

## Identity checks

[Identity API](docs/identity-api.md), [security scope](docs/security.md), and [schema](docs/database-schema.md) describe the implemented boundaries. The integration tests use PostgreSQL transactions/savepoints and roll back their data, with isolated expiring Redis counters.

With the complete Docker stack running, verify the browser-facing HTTP/session contract:

```sh
backend/.venv/bin/python scripts/verify_identity_http.py
```

This creates temporary accounts and empty businesses, exercises access controls through Next.js, and removes only its own records. No test credentials are printed.

## Operational HTTP check

With the stack running, from backend run `PYTHONPATH=. .venv/bin/python ../scripts/verify_operations_http.py`. It uploads CSV and XLSX through Next.js, confirms previews, checks actual totals and tenant isolation, then removes its temporary records.

## Model lifecycle HTTP check

With the stack running, from backend run `PYTHONPATH=. .venv/bin/python ../scripts/verify_ml_http.py`. It imports synthetic history, evaluates and replays sales/demand/churn models, checks activation, source drift and tenant isolation, then removes only its own records.

## Local AI on this Mac

The selected local profile uses qwen3:1.7b for answers and qwen3-embedding:0.6b for retrieval, with a macOS Vision bridge for English scanned PDFs. No fine-tuning or paid API is used. After a reboot, start the native services before the app:

```sh
sh scripts/start_local_ai.sh
sh scripts/start_local_ocr.sh
docker compose up -d
```

Open Documents & answers. Re-index older uploads that awaited configuration. See [local setup](docs/local-ai.md) and [actual Phase 4 verification](docs/phase4-verification.md). Initial model downloads are already installed on this Mac; do not pull them on every startup.
