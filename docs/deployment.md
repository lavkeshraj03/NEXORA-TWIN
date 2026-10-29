# Deployment, demo setup and recovery

## Local installation

Install Docker Desktop/Engine with Compose v2. Preserve an existing .env and its volumes during upgrades. For a fresh checkout, copy `.env.example` to `.env`, choose a unique PostgreSQL password, then run from the repository root:

```sh
docker compose config --quiet
docker compose up --build -d
docker compose ps
python3 scripts/validate_environment.py
```

Configuration validation deliberately prints no resolved credentials. The five long-running services are PostgreSQL, Redis, API, RQ worker and frontend. The migration service exits successfully after applying **0009_insights**, the current schema head. API readiness checks PostgreSQL, pgvector, migration head and Redis; it does not certify local AI readiness. Open Documents & answers to inspect provider status.

Default host bindings are loopback 3000/8000/55432/56379. Optional FRONTEND_PORT/BACKEND_PORT/POSTGRES_PORT/REDIS_PORT change host ports. Set ALLOWED_ORIGINS to the actual browser origin as a JSON list, such as `["http://localhost:3000"]`. Internal service addresses remain backend:8000, postgres:5432 and redis:6379. Native tools instead use the corresponding loopback host ports. Do not expose database, Redis or unauthenticated local model/OCR ports publicly.

The verified AI configuration is in local-ai.md. Start the native Ollama and OCR helpers after reboot; keep API and worker model/provider variables identical, then recreate them after configuration changes. Changing an embedding model or provider URL requires explicit re-indexing. Models are not bundled into Linux images. No AI API key is needed for the selected local Ollama profile.

## Migrations and upgrades

```sh
docker compose run --rm migrate
docker compose up -d --build backend worker frontend
```

Migrations are an explicit deployment task; the API never creates tables on startup. The initial revision enables pgvector and does not remove a potentially shared extension during downgrade. Every schema change must update the health revision contract and migration tests. Back up before upgrades. Do not downgrade a database containing later-phase records without a reviewed migration/recovery plan.

## Fresh labelled demonstration

Register an account and create a **new empty retail business in INR with inventory enabled**. Copy its business ID from the business API/URL and the owner user ID from `/api/backend/auth/me` while signed in. The loader verifies ownership and refuses to mix into nonempty operational/document/model data. It generates only synthetic data and never provisions a privileged account.

With the backend test Python environment installed as in README:

```sh
backend/.venv/bin/python scripts/seed_nexa_demo.py --generate-only --data-dir /tmp/nexora-demo --end 2026-10-28
docker compose cp scripts/seed_nexa_demo.py backend:/tmp/nexora-seed.py
docker compose cp /tmp/nexora-demo backend:/tmp/nexora-demo
docker compose exec -T -e PYTHONPATH=/app backend python /tmp/nexora-seed.py --data-dir /tmp/nexora-demo --business-id YOUR_BUSINESS_UUID --owner-id YOUR_OWNER_UUID
```

Replace the two UUID placeholders with the actual IDs; never use somebody else's account. Run this only for an explicitly requested demo. It imports six resources atomically, reconciles finances/stock, trains evaluated sales/demand/inactivity runs, indexes two generated text sources through RQ and checks real cited answers. AI and worker must be available. Repeat with the same generated package to verify idempotency; operational data/models/documents are reused, while new verification/evaluation history may be recorded. The existing Nexa package includes additional document formats and saved outputs from subsequent phases; this fresh seed does not fabricate those later saved outputs.

Run the loader inside the API container as shown. A native loader must use the exact same provider identity as the worker; replacing host.docker.internal with 127.0.0.1 changes that identity and causes current-index retrieval to exclude those embeddings. Provider identities intentionally include the URL and model. See nexa-demo-guide.md for the existing workspace walkthrough.

## Repeatable isolated release acceptance

Build the app images with `docker compose build`, install backend test dependencies, configure local AI, and keep ports 3001/8001/55433/56380 free. Run:

```sh
backend/.venv/bin/python scripts/verify_fresh_install.py
```

The verifier names its project `nexora-acceptance-` followed by a random suffix. It creates independent PostgreSQL/Redis volumes, migrates from empty, waits for all five services, checks model/schema drift, runs all backend tests and a real Next.js graph/report/PDF workflow, then imports synthetic demo data twice with actual local indexing and cited answers. It uses existing locally built app images; fresh image builds are verified separately. It removes only its own generated project's containers, network and volumes, and records `.local/phase10-fresh-install.json`. The main nexora-twin database/volumes are not reset. If interrupted by a machine crash, inspect that exact project name and remove only those acceptance resources. Do not run a global prune or remove volumes from the main project.

NEXORA_TEST_BACKEND can point to a matching local backend copy to work around macOS Desktop file offloading. Keep project files downloaded; stalled cloud-backed file reads are an operating-system issue, not a reason to reset PostgreSQL.

## Backup and restore procedure

This local release stores tenant data, raw documents, vectors, model artifacts and saved outputs in PostgreSQL. Redis retains queue/rate-limit infrastructure. Native downloaded model files and `.env` are separate operational assets. Keep backup access restricted and choose encryption/retention appropriate for the data.

```sh
mkdir -p backups
chmod 700 backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/nexora.dump
chmod 600 backups/nexora.dump
```

Restore to a **separate empty PostgreSQL database** with pgvector support and compatible roles, using `pg_restore --no-owner --no-privileges --exit-on-error`; never overwrite the working database to test recovery. Validate readiness, record counts, document retrieval and source hashes before a reviewed cutover. Automated backup scheduling and disaster-recovery/restore acceptance are not implemented or claimed as tested by Phase 10. A fresh migration test is not a backup restore test. Do not commit dumps or `.env` files.

## Troubleshooting

- Docker socket unavailable: start Docker Desktop and wait for the engine. Do not kill unrelated processes or remove volumes.
- Occupied ports: change host port variables or stop only a known conflicting service; update browser origins/native URLs.
- Password changed after initial setup: changing POSTGRES_PASSWORD does not update the role in an existing volume. Restore the configured password or deliberately change the role through a controlled admin operation.
- API not ready: inspect `docker compose logs --tail=100 backend migrate worker`, migration head and PostgreSQL/Redis health. Do not share environment dumps or sensitive log content.
- AI errors: start native helpers, check the configured models and provider status, ensure API/worker variables agree, then explicitly re-index waiting documents. No hidden paid or dummy fallback exists.
- Queued documents: check the worker and version status. Extraction/indexing has a 180-second job deadline; stale processing can be explicitly retried after five minutes.
- Missing profit/forecast: inspect coverage and history requirements. Unknown input stays unknown. Do not replace unavailable facts with zero.

## Production target and limits

Compose is a loopback-only local MVP with a single database role. Synchronous bounded training and graph reads are suitable only for the documented local workload. A production target may use HTTPS ingress with separate frontend/API/worker tasks, private PostgreSQL supporting pgvector and private Redis. Use separate restricted migration/runtime roles, managed secrets, tested backups, object retention policies, content isolation/antivirus, monitoring and bounded queues. AWS/ECS/RDS/ElastiCache infrastructure, TLS, production scaling and restore acceptance have not been deployed or verified here. Security.md and phase10-verification.md distinguish measured local checks from remaining work.
