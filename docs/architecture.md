# Architecture and implementation plan

The repository was empty at inspection. The chosen stack follows the source brief: Next.js App Router and strict TypeScript, FastAPI/Pydantic, SQLAlchemy 2, PostgreSQL with pgvector, Alembic, Redis/RQ, and Docker Compose. Dependency snapshots are committed separately from environment credentials.

## Current boundaries

- Browser → Next.js: rendering and same-origin `/api/health` proxy.
- Next.js → FastAPI: server-side HTTP, finite timeout, no cached health data.
- FastAPI → PostgreSQL: SQLAlchemy connection pool with pre-ping and connection timeout.
- FastAPI → Redis: bounded connectivity probe.
- Alembic → PostgreSQL: explicit versioned migrations, independently executed.
- RQ worker → Redis/PostgreSQL: versioned document extraction/indexing jobs, durable per-version status.

Readiness verifies SELECT 1, pgvector extension presence, the expected Alembic revision, and Redis PING. Readiness does not claim worker, AI-provider, or future business-feature health. Liveness is independent of infrastructure. Every API response has a generated request ID; request logs exclude request bodies and secrets.

## Incremental phases

1. Foundation: startup, migrations, design system, health, containers, tests.
2. Identity: password hashing, server-side sessions, CSRF, membership-based authorization, business switching, isolation tests.
3. Business data: normalized operational schema, mapped imports, Decimal calculations, real dashboard queries.
4. Documents: extraction, versioned chunks, provider embeddings, tenant-filtered pgvector and lexical retrieval, citations.
5. ML: chronological validation, naive baseline, per-business models, evaluated predictions and artifacts.
6. Twin: immutable snapshots of traceable state.
7. Scenarios: validated deterministic calculations with persisted assumptions and comparisons.
8. Analyst: authorized read tools, evidence, explicit provider failures, bounded execution.
9. Graph and reports: source-linked relationships and exports.
10. Hardening: full integration, accessibility, isolation review, production deployment and limitations.

Advance only after verifying the preceding phase. Future phases must replace planned labels with working backend-driven features; decorative charts and fabricated data are prohibited.

## Risks and decisions

- Tenant leakage is the highest business risk: introduce identity before records, check memberships in centralized backend dependencies, and use composite tenant foreign keys for related entities. PostgreSQL RLS is optional defense in depth only after safe connection-pool session tests.
- Document extraction and model calls are untrusted, long-running operations. Use worker jobs with explicit tenant/user context and renewed authorization; never deserialize arbitrary user-supplied model artifacts.
- Numerical truth belongs to Decimal calculation services and evaluated models. LLMs explain evidence; they do not provide financial arithmetic.
- No synthetic data is silently introduced. Demonstration operational records carry explicit provenance labels.
- The entire source brief is larger than the foundation and identity releases. Security-sensitive endpoints are introduced with tests in later phases rather than exposed early.
- The current migration installs pgvector and requires an extension-capable database administrator. A production runtime user should not own migrations or have DDL privileges.

## Phase 2 boundaries

PostgreSQL now holds accounts, expiring server-side sessions, business configuration, composite memberships, and audit records. A centralized permission registry is checked by every business router. The browser uses a bounded same-origin proxy; the protected workspace validates the session server-side. See identity-design.md and database-schema.md for the implemented scope and remaining limits.

## Phase 3–4 boundaries

Operational data uses composite tenant references, bounded preview/confirm imports and exact Decimal reporting. Document processing uses a bounded RQ pipeline and versioned chunks in pgvector. Hybrid retrieval filters business, document visibility, active version and embedding identity before context assembly. A configurable compatible provider performs embeddings/chat; optional OCR has an explicit operator-hosted contract. No model is silently selected or substituted. Provider doubles are isolated to unit/integration tests; actual local Qwen/OCR acceptance passed and is recorded in phase4-verification.md. See operations-api.md and documents-api.md.

## Phase 5 numerical boundary

Tenant-filtered paid sale lines are aggregated with Decimal before model conversion to NumPy. Fixed chronological evaluation compares seasonal-naive and ridge models; customer inactivity uses leakage-aware cutoff snapshots and deterministic logistic fitting. Immutable snapshots, feature definitions and safe JSON artifacts live in PostgreSQL model_runs. Explicit activation and prediction replay are distinct from training. Source monitoring never silently retrains. Inventory risk is deterministic, and rolling anomalies expose their source dates. These numerical services are independent of Phase 4's chat/embedding provider. See forecasting-api.md for precise assumptions, limits and verification.


## Phase 6 state boundary

Digital twin capture locks the business row shared by operational mutations, serializes tenant-filtered operational inputs and active forecast results, then applies a pure versioned Decimal transformation. PostgreSQL retains both inputs and state; reads verify a canonical content hash and replay before returning saved details or comparisons. Current previews never persist automatically. Historical reporting dates and current-at-capture stock are explicit, and comparisons preserve missing values and unequal-period warnings. No AI or simulation changes actual business records. See digital-twin-api.md.


## Phase 7 hypothetical boundary

The pure simulation engine consumes only saved twin inputs and validated scenario assumptions. Decimal calculations apply explicit price elasticity, demand/customer-loss assumptions, supplier/product cost changes, category-specific marketing/payroll changes and optional stock constraints/replenishment cash. Preview hashes bind confirmation to unchanged parameters/baseline. Saved runs and reports retain provenance and reproduce before reads; no operational record is updated. Docker dependency installation now precedes source copying so subsequent source edits reuse the locked runtime dependency layer. See simulation-methodology.md.


## Phase 8 analyst boundary

A structured model chooses up to three predefined read tools in addition to mandatory financial comparison. Server-validated request fields supply all arguments; no model-generated SQL, business identifiers or operational actions exist. The model then selects IDs of backend-calculated facts or exact retrieved excerpts, rather than authoring unchecked figures. Business permissions and document visibility are revalidated between stages. Private source copies, tool timings/results, hashes and finalized findings are retained in PostgreSQL. Redis bounds concurrency; model calls occur outside the business write lock. Saved scenario/model replay never trains, activates, invents assumptions or mutates operations. See analyst-api.md.


## Phase 9 relationship/report boundary

A bounded graph builder copies tenant-filtered source records under the business write lock, creating only ownership and foreign-key relationships. Reads filter document visibility before counts and neighborhoods. Reports consume authorized saved twins, models, scenarios or private investigations and retain dated results, assumptions and hashes without operational changes. The native CSV/PDF exporters escape data; the same-origin proxy forwards binary buffers so PDF cross-reference offsets remain intact. No graph database or extra AI call is introduced. See graph-reports-api.md.
