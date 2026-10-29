# End-to-end verification — 29 October 2026

**Result: all tested flows passed.** Nine live HTTP workflows and a continuous authenticated Chrome journey were exercised against the current production app images. The browser journey passed all 14 stages, downloaded all seven report types as CSV and PDF, and produced no uncaught browser runtime exceptions. Seven downloaded PDFs were independently parsed with pypdf in strict mode.

These were actual Next.js → FastAPI → PostgreSQL/pgvector/Redis/RQ requests, with real qwen3:1.7b answers, qwen3-embedding:0.6b embeddings and native macOS Vision OCR. No provider doubles or fabricated responses were used in live acceptance. The separate automated backend suite uses explicit fixtures/doubles where appropriate.

## Coverage and results

| Workflow | Exercised behaviour | Result |
| --- | --- | --- |
| Identity and teams | Anonymous workspace protection; registration; session/cookie proxy; two businesses; membership; viewer write denial; CSRF; audit; logout | Passed |
| Operational data | CSV/XLSX preview and validation; explicit/idempotent confirmation; rejected import atomicity; exports; stock and financial totals; expense completeness; cross-business denial | Passed |
| Documents and answers | TXT, PDF, DOCX, CSV and XLSX extraction/indexing; real embeddings; exact citations; PDF page references; follow-up questions; unsupported questions; tenant/document/conversation isolation; instruction fixture; replacement versions; curated evaluation | Passed |
| Scanned PDF | Image-only source verified to have no extractable text; OCR through worker; embeddings; cited answer with page 1 | Passed |
| Numerical models | Imported 140-day history; chronological sales/demand evaluation; prediction replay; explicit activation; stock risk; source-drift detection after refund; saved-history immutability; inactivity evaluation; tenant denial | Passed |
| Digital twin | Save/current/read/reproduce; source inspection; comparison; date validation; cross-business denial; old evidence after correction | Passed |
| Simulations | Explicit preview confirmation; stale-preview rejection; elasticity/sensitivity; baseline; replenishment cash separation; unchanged operations; exports; comparison; replay after correction | Passed |
| Analyst | Actual-model financial and policy investigations; captured sources; citations; CSV; unsupported future competitor question; attempted destructive instruction; unchanged source versions; separate unavailable-provider API returns 503 and saves a failed investigation without an answer | Passed |
| Graph and reports | Recorded relationships and provenance; idempotent refresh; relationship filters; frozen financial/monthly/inventory reports; CSV; PDF bytes through the proxy; strict PDF parsing; tenant/source denial; immutable reports after refund | Passed |

The browser used the visible forms/navigation to register an owner, create an empty INR retail business and import all six generated CSV resources. It checked that previews wrote no records and explicitly confirmed each import. It reconciled revenue and expense-dependent operating profit, inspected data, uploaded/indexed a policy and asked a cited question, trained sales/demand/inactivity models, explicitly activated the sales model, saved/reopened/compared snapshots, reviewed and saved two sensitivity scenarios, asked the analyst a financial question, and searched/explored a SKU's graph relationships with keyboard activation.

It then generated **monthly, revenue/expenses, inventory-risk, sales-forecast, customer-inactivity, scenario-comparison and investigation reports**, clicking each real CSV/PDF download link. It saved settings, created an empty restaurant business, switched back without leaking its records, added a registered viewer through the team form, verified viewer read/write limits and creator-private reports, checked audit history, captured the mobile workspace, signed out, verified 401, signed back in and signed out again.

The complete backend suite passed **167 tests** against fresh PostgreSQL/Redis in **41.73 seconds**. Frontend passed **37 tests across nine files**, and strict TypeScript passed. The existing Starlette TestClient/httpx deprecation warning remains. All tests ran against unchanged application code from the final Phase 10 images; this task added reusable acceptance scripts and documentation, not product behaviour changes.

## Test correction and rerun

All nine HTTP workflows passed in the first isolated installation. The first browser attempt stopped at a test assumption: creating a snapshot displays captured evidence, while integrity reproduction is checked on a subsequent read. The test now explicitly reopens each saved snapshot before asserting reproduced integrity. The complete browser journey then passed in a second fresh isolated installation. This was a harness correction; no application bug or weakened assertion was introduced. The original failure and successful rerun receipts/logs are retained.

The consolidated `.local/e2e/final-summary.json` identifies both projects and preserves the distinction between the nine HTTP results and the browser rerun. It does not relabel the initial interrupted browser run as successful.

## Data preservation and cleanup

Testing used randomly named `nexora-acceptance-*` projects with independent database/Redis volumes and ports 3001/8001/8002/55433/56380. Only the exact registration counter in that disposable Redis was cleared between independent workflows to avoid aggregating their temporary registrations. The main application's authentication counters were not changed. Unavailable-provider checks used a separate API container configured with an unreachable provider address; the working native Ollama service was not stopped.

Both disposable projects and their dedicated volumes/network were removed. Individual HTTP workflows also verified removal of their temporary users/businesses. Browser-generated synthetic reports remain only as local test artifacts. Nexa's existing records were checked separately in a read-only transaction: 84 customers, three suppliers, six products, 342 orders, 538 stock movements, 68 expenses, seven documents, four model runs, three snapshots, two scenarios, three investigations, seven reports, 1,055 graph nodes and 2,468 graph edges. Its 29 September–28 October totals remain revenue INR 150,562.00 and operating profit INR 42,712.00.

## Repeat and inspect

```sh
backend/.venv/bin/python scripts/verify_fresh_install.py --all-flows
```

Requirements: built app images, backend test dependencies, Docker access, installed Chrome/Chromium and Node 22+, real local AI/OCR configuration, and free acceptance ports. CHROME_BIN can override the browser path; NEXORA_TEST_BACKEND can use a matching downloaded source copy if macOS Desktop offloading stalls reads. A browser-only rerun is available with `--browser-only`. See README for setup.

Receipts are under `.local/e2e/`: `final-summary.json`, `http-first-run.json`, `browser-first-run.json`, `browser-journey.json`, `nexa-preservation.json`, individual workflow JSON, `all-flows.log`, `browser-final.log` and `frontend-tests.log`. Screenshots include `dashboard-desktop.png`, `analyst-desktop.png`, `reports-desktop.png` and `workspace-mobile.png`; the successful download folder is recorded in browser-journey.json. These artifacts contain synthetic test data and should not be committed as customer data.

## Limits

This checks the recorded normal journeys and selected failure/security boundaries; it is not exhaustive coverage of every input or concurrency condition. Browser checks do not certify WCAG conformance or every browser/device. Citation integrity/curated retrieval tests do not establish broad semantic accuracy or human faithfulness. Production TLS/cloud deployment, least-privilege infrastructure, content isolation/antivirus, load testing and backup-restore acceptance remain outside this local release. See security.md and deployment.md.
