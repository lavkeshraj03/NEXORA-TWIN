# Implemented schema — Phases 3–4

The PostgreSQL schema is managed by Alembic revisions `0001_foundation`, `0002_identity`, `0003_operations`, and `0004_documents`. SQLAlchemy metadata lives in `backend/app/models.py`; `alembic check` detects migration drift. Operational metadata lives in app/data/models.py. Document metadata lives in app/documents/models.py. ML and simulations follow in later phases.

| Table | Purpose | Important constraints |
|---|---|---|
| users | Normalized email, display name, scrypt password hash, platform flag | UUID primary key, unique normalized email |
| auth_sessions | Hashed session identifiers, CSRF token, UTC expiry | User FK with cascade; indexes on user and expiry |
| businesses | Profile, country, currency, IANA timezone, reporting month, configured modules | UUID PK; supported profile and reporting month checks |
| business_memberships | Tenant access and per-business role | Composite business/user PK; both FKs; closed role constraint |
| audit_logs | Authentication and tenant change events without request bodies | Nullable business/user FKs; business/time index |

Roles and permissions are currently a centralized, version-controlled registry in `app/core/permissions.py`; they are not user-editable database tables. A platform administrator flag does not imply tenant membership. There are no unrestricted platform tenant-data endpoints.

Tenant isolation is enforced through backend membership checks and tenant-scoped queries. PostgreSQL RLS is not enabled; no pooled-connection tenant context is used. Membership writes lock the business row, refresh the actor's role, and preserve a final owner. RLS, invitation delivery, and retention automation are later work.

Dates are timezone-aware. Sessions expire after eight hours and become unusable immediately on logout. Expired session rows are currently retained until operational cleanup; no automatic user/business deletion endpoint is exposed. The rollback migration for identity deletes identity tables and is destructive; never run it against retained accounts without an explicit backup and maintenance plan.

## Operational records

Customers, suppliers, products, orders/order_items, inventory_movements/inventory_balances, expenses, expense_coverage, and import_batches are tenant-scoped. Composite foreign keys prevent cross-business customer/product/supplier links. External identifiers are unique per tenant/resource; order items allow one SKU per order. Amounts use Numeric(18,4), quantities Numeric(18,3). Business data_status changes to has_data on a successful write and prevents currency changes after data is recorded. Confirmed import previews persist source rows, mapping, errors, hashes and results. No automatic data seeding or hard-delete API exists.

## Document intelligence

Revision 0004_documents adds documents, document_versions, document_chunks, rag_conversations and rag_evaluations. Version/chunk references use composite tenant foreign keys. Documents select an active version only after successful indexing. Each version retains the original bounded bytea, hash, pipeline status, model identity/dimensions and usage. Chunks retain text, page/section/kind and pgvector vectors. Variable vector dimensions are allowed in storage; retrieval filters model identity/dimensions before similarity ranking. Conversations are business- and user-scoped; evaluation metrics exist only after a run. Raw files, chunks, conversations and evaluations require a production retention policy; no deletion API exists yet.

## Evaluated models — Phase 5

Revision 0005_models adds model_runs: tenant/task/product/scope, creator, algorithm/implementation version, immutable dataset snapshot/hash, safe JSON artifact, evaluation/prediction results and explicit active state. The product reference is a composite tenant FK. A partial NULLS NOT DISTINCT unique index enforces one active run per business/task/scope/product, including all-product/churn runs with null product. No pickled artifact or user-supplied executable is stored. Dataset/source retention is bounded to 20 runs/business in this MVP; deletion/retention UI remains later work.


## Digital twin — Phase 6

Revision 0006_twin adds twin_snapshots with business/creator references, bounded name, transformation version, SHA-256, JSONB inputs/state and timestamp. Business/creation indexes support tenant history. Captured evidence is protected against UPDATE by a database trigger; creator SET NULL remains supported. Tenant ownership is verified on every read, capture, source and comparison route. Saved source copies preserve replay after operational corrections. See digital-twin-api.md for hash, reconstruction and retention details.


## What-If Lab — Phase 7

Revision 0007_simulations adds a tenant/id unique key to twin_snapshots and simulation_runs with a composite tenant-snapshot FK, creator, immutable name/parameters/results, engine version, baseline/content hashes and creation timestamp. A database trigger protects evidence updates; tenant history indexes and projected queries bound listing cost. Runs reproduce against their original immutable snapshot, independently of current operational edits. See simulation-methodology.md.


## Bounded analyst — Phase 8

Revision 0008_analyst adds analyst_investigations: private tenant/user ownership, captured role, question/correlation ID, configured model and implementation version, parameters, operational inputs/hash, selected plan, execution evidence, response/error and lifecycle timestamps/status. Business/user indexes support projected history. A PostgreSQL trigger protects source inputs and finalized evidence. History, detail, source and export queries enforce both business membership and user ownership; current document visibility and captured administrator privilege are rechecked. See analyst-api.md.


## Graph and reports — Phase 9

Revision 0009_insights adds graph_builds, knowledge_nodes, knowledge_edges and generated_reports. Composite tenant/build/node FKs constrain graph endpoints. Nodes and edges retain structured source references/values/hashes; graph build manifests preserve versioned capture. Reports retain private tenant/user ownership, captured role, kind, frozen sections/provenance, version/hash and timestamp. Database triggers protect captured evidence from updates. Live document visibility is applied to graph reads and investigation-report exports. See graph-reports-api.md.
