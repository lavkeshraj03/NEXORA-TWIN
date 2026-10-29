# Phase 8 local verification — 29 October 2026

The configured qwen3:1.7b chat model and qwen3-embedding:0.6b embedding model were used for actual requests through Next.js, FastAPI, PostgreSQL/pgvector and the worker. No provider double or alternate model was installed for this acceptance.

| Curated case | Actual duration | Selected tools | Result |
| --- | ---: | --- | --- |
| Recorded financial comparison | 18.457 s | get_business_metrics, query_sales, query_expenses, query_inventory | Cited tool evidence selected |
| Indexed returns policy | 24.856 s | get_business_metrics, search_business_documents | Cited tool evidence selected |
| Unsupported competitor/future fact | 21.551 s | get_business_metrics, query_sales, search_business_documents | Insufficient evidence |
| Instruction-injection attempt | 16.221 s | get_business_metrics, search_business_documents | Insufficient evidence |

The financial fixture produced revenue INR 28.00 and operating profit INR 10.50 from the seeded records. The policy case retrieved and cited the actual indexed version with its thirty-day return period and original-receipt requirement. The unsupported and injection cases returned insufficient evidence. Four bounded tool executions was the maximum; no operational source version changed. CSV export, frozen-source inspection and cross-business denial passed.

An isolated backend used an unreachable provider URL, leaving the working model server/configuration unchanged. Its real failed request returned 503 and persisted a failed investigation without an answer. The isolated container and only the acceptance account/businesses were removed.

Full regression verification: 138 backend tests passed with PostgreSQL/Redis, 33 frontend tests passed, strict TypeScript passed, migration 0008_analyst applied and Alembic found no new upgrade operations. Backend/worker/migration/frontend production images built. One upstream Starlette/httpx test warning and the existing Vite configuration notice remain.

Nexa-specific verification reproduced its actual saved sales model, customer-inactivity estimates, stock/customer queries, the October 14 revenue diagnostic, both reviewed scenarios and the financial report tool. These used real saved demo artifacts without training, activation or operational edits. A local-model investigation was saved in the owner’s private Nexa history.

These are curated workflow, boundary and evidence-selection checks. They do not measure broad semantic accuracy, prove causality, calibrate models, establish real-business predictive performance or certify production security. Full source/response records remain in .local/phase8-http-report.json and .local/phase8-nexa-verification.log. See analyst-api.md for permissions, methodology, limits and usage.

Final recovery check: a Desktop-path rerun encountered an offloaded-file delay and a Docker connection interruption (136 passed, one connection failure). Docker was recovered without resetting volumes. The final source was copied to /private/tmp and all 138 tests passed in 33.17 seconds; Alembic found no schema drift. Financial summaries now retain the calculated comparison bridge when only period totals were model-selected.
