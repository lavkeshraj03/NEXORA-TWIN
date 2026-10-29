# Development progress — 29 October 2026

## Current status

**Phase 3 is complete and running locally. Phase 4 implementation is running; live-provider acceptance remains pending.** Open http://localhost:3000/login. No production deployment is claimed. Phases 5–10 are not implemented and remain planned.

The original Phase 3 interruption was caused by offloaded Desktop source/dependency files. Requesting macOS downloads and verifying against a fresh dependency directory under /private/tmp restored progress. Project source remains in this workspace. The temporary directory is only a verification workaround, not a runtime dependency.

## Phase 3 completed

Implemented tenant-scoped customers, suppliers, products, orders/items, stock movements/balances, expenses/coverage, and import previews. Composite tenant foreign keys enforce relationships. Manual entry, search/filter/sort/pagination, record inspection, status corrections, exports and source transactions are connected to the UI. CSV/XLSX/JSON imports support preview, mapping, validation, explicit timestamped confirmation, atomic rejection, error downloads and idempotency.

Actual dashboard APIs calculate Decimal revenue, historical COGS, gross profit/margin, recorded expenses, operating profit completeness, average order value, daily trends, activity retention and current inventory valuation. Unknown costs remain incomplete. New or voided expenses retract overlapping expense-completeness confirmations. Inventory direction and nonnegative-stock checks apply. Profile labels/modules and 29 explicitly labelled demonstration CSV files are included; no automatic seed exists. See operations-api.md and datasets/README.md.

## Phase 4 implemented; acceptance pending

Added a document library and question interface, bounded PDF/DOCX/TXT/CSV/XLSX uploads, version history, document-level visibility, source previews, durable ingestion states, RQ processing and explicit retries. Extraction preserves PDF pages, headings and table rows. Provider embeddings are stored with model identity/dimensions in pgvector. Hybrid retrieval combines exact cosine ranking and PostgreSQL English full-text rankings, with tenant/visibility/active-version filters applied before model context assembly. Citations require retrieved IDs and exact supporting excerpts. Conversations are business- and user-scoped. Provider failures are explicit; no model or answer fallback is fabricated.

Configured compatible hosted/local HTTP adapters support embeddings and JSON chat answers. Optional operator-hosted OCR has a documented bounded contract. Evaluation records actual retrieval/ranking, citation integrity, reference-substring matching and latency. Human faithfulness/relevance review remains explicitly Not evaluated. No real model or OCR service was configured or successfully exercised in this environment; provider doubles exist only in tests. See documents-api.md and .env.example for configuration and remaining acceptance.

## Verification

- **71 backend tests passed**, including real PostgreSQL/Redis and pgvector retrieval integration. New cases cover operational financial truth, atomic import confirmation, tenant composite FKs, document visibility, active versions, citation forgery rejection, explicit provider failures, OCR response validation and measured evaluation persistence. One upstream Starlette/httpx deprecation warning remains.
- **17 frontend tests passed** across four files; strict TypeScript passed. Document UI cases cover absent-provider states, source citations, follow-up conversation IDs and viewer controls. Vite emits a config-loader compatibility notice.
- Docker production frontend build passed, including final document styles. Backend, worker, migrate and frontend images built successfully with locked runtime dependencies under Python 3.12 / Node 22. Native backend tests used Python 3.14; timezone data was aligned to the committed constraint.
- Alembic upgrade through **0004_documents** succeeded; schema comparison reported **No new upgrade operations detected**. Revisions 0003_operations and 0004_documents were reviewed and pgvector type imports corrected.
- All five long-running services reached healthy status. Readiness verified PostgreSQL, pgvector 0.8.7, current migration and Redis. Compose interpolation validated without printing credentials.
- Actual HTTP workflow through Next.js passed: CSV and XLSX uploads, previews without auto-commit, explicit/idempotent confirmation, dashboard totals, inventory, expense completeness, tenant isolation, CSV exports/error downloads, rejected import atomicity and logout. Expected sample totals were revenue 28.00, gross profit 16.00 and confirmed operating profit 10.50 INR.
- Actual HTTP/RQ document workflow passed: saved upload, background extraction, exact source preview, cross-business denial and explicit 503 for unconfigured AI. Worker completed the temporary extraction job. Test accounts/businesses and their records were removed by owned-ID cleanup.
- Final full-stack identity regression passed: server-side protection, registration/cookie proxy, two businesses, tenant isolation, CSRF, viewer restrictions, audit history and logout. Temporary users/businesses were removed. Three confirmed registration-counter increments from the final document/identity HTTP checks were removed, preserving other attempts and expiry.

## Remaining work

Configure actual AI_BASE_URL, AI_EMBEDDING_MODEL, AI_CHAT_MODEL and credentials where required, restart backend/worker, re-index, then verify a real upload/question/citation workflow and run/review curated evaluation. OCR accuracy and live endpoint behavior remain unverified. Do not mark Phase 4 accepted until this succeeds. The UI deliberately labels missing configuration and evaluation state.

Phases 5–10 add evaluated forecasting, reproducible twin snapshots, deterministic scenarios, bounded analyst tools, graph/report exports and hardening. Production still needs robust content sandboxing/antivirus, raw-file retention controls, restricted database roles, TLS, backups/restore, accessibility/browser QA, load testing and an independent tenant/security review. No timeline or completed phase is fabricated. Earlier milestones are archived in progress-phase1-history.md and progress-phase2-history.md.
