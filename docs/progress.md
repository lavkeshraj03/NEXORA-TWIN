# Development progress

Latest start-to-finish acceptance: **nine live HTTP workflows, 14 authenticated browser stages, seven CSV downloads and seven strictly parsed PDFs passed**. See [end-to-end verification](end-to-end-verification.md) for coverage, the snapshot-test correction, data preservation and limits.

**Phases 1–10 are complete for the documented local MVP.** Final hardening and delivery acceptance is recorded in [Phase 10 verification](phase10-verification.md). Public production deployment and the explicit limitations below remain outside this verified release.

| Phase | Delivered capability |
| --- | --- |
| 1 | Next.js/FastAPI/PostgreSQL/Redis foundation, migration and readiness |
| 2 | Accounts, sessions, businesses, membership roles, switching and audit |
| 3 | Operational records, mapped imports and source-calculated financial dashboards |
| 4 | Versioned documents, local embeddings/chat, evidence citations and English macOS OCR |
| 5 | Evaluated sales/demand models, customer-inactivity proxy and stock diagnostics |
| 6 | Reproducible saved business snapshots and historical comparison |
| 7 | Reviewed deterministic scenarios, sensitivity, stock/cash calculations and exports |
| 8 | Bounded analyst investigations, calculated/document evidence and private history |
| 9 | Source-backed knowledge graph, seven report families and CSV/PDF exports |
| 10 | Direct API body protection, query batching, keyboard improvements, isolated startup/demo acceptance and delivery documentation |

Final results: **167 backend tests**, **37 frontend tests**, strict TypeScript, production image builds and Alembic schema comparison passed. A separate installation migrated empty volumes, reached five healthy services, passed the complete backend suite and real graph/report/PDF HTTP checks, then loaded/reloaded synthetic demo data with actual local indexing and cited answers. Browser checks passed for public/login keyboard navigation and mobile layouts. Nexa's existing operational data, financial totals and seven reports remain intact.

Start at **http://localhost:3000/login**, select Nexa, and follow [the demo guide](nexa-demo-guide.md). [README](../README.md) explains startup and usage; [deployment](deployment.md) covers fresh seeding, upgrades, isolated acceptance and recovery. After a reboot, restart the native AI/OCR helpers before document/analyst use.

Remaining work is explicitly recorded in [Phase 10 limitations](phase10-verification.md), [security](security.md) and [deployment](deployment.md): public production infrastructure/TLS, backups with verified restore, least-privilege roles, content isolation/antivirus, retention/account recovery, broader accessibility/load/security evaluation and independent model-quality review. Configurable business profiles do not imply complete industry ERP modules. There is no fabricated next numbered development phase; the next practical step is a reviewed pilot with real records in a separate empty business.

Previous verification and implementation detail is preserved in [Phase 9 progress history](progress-phase9-history.md), [Phase 9 verification](phase9-verification.md), [Phase 8 verification](phase8-verification.md), [Phase 4 verification](phase4-verification.md), and the earlier progress-phase1/2/4-history files.
