# AI business analyst — version 1

The analyst investigates a question through a bounded plan: one mandatory financial tool plus up to three additional predefined tools. The configured chat model chooses tools and selects evidence IDs. Financial arithmetic and fact text come from tested backend calculations, while policy findings quote actual retrieved document text. Financial summaries retain the calculated period-comparison bridge even when the model selects only the totals, so the changes remain explicit. The model cannot issue SQL, supply tenant IDs/tool arguments, invent narrative figures, train/activate models, create scenario assumptions or change operational records.

This deliberately limits what the analyst can say. Valid references do not prove that the selected evidence fully answers a question. Observed accounting changes and statistical associations do not establish business causes. Human review remains necessary.

## Use with Nexa

1. Refresh http://localhost:3000/workspace, select **Nexa → AI analyst**.
2. Set **2026-09-29 through 2026-10-28**. Ask **“How did recorded revenue, costs and gross profit change from the previous period?”** The comparison uses 30 August–28 September. October revenue is ₹150,562; operating profit is ₹42,712. The prior period lacks confirmed expense coverage, so operating-profit change must remain unavailable rather than fabricated.
3. For inventory, ask **“Which products have low stock based on recorded demand?”** and optionally enter SKU **NX-PEN-01**. Stock is current at capture; cover is a rule using selected-period recorded demand, not a guaranteed stockout date.
4. For documents, select the demo returns-policy document under optional scope and ask **“What does the returns policy say?”** Review the exact excerpt, document/version, page and chunk reference.
5. For forecasts or inactivity estimates, choose **Labelled demonstration records only**, select the saved sales/inactivity model, and ask about that model. No activation or retraining occurs. Its original cutoff, evaluation, limitations and source-change check are retained.
6. Select the two already reviewed demo scenarios and ask to compare their hypothetical operating profits. Both must share the same saved baseline. The analyst does not invent new assumptions or save a new scenario.
7. Inspect the tool execution trail and captured source values. Download the investigation CSV if needed. History is private to your own account in that business.

Local Qwen performs two bounded structured generation calls. A document search additionally uses the configured embedding model. Requests can take a few minutes on the laptop. An unavailable/malformed provider returns an explicit error and saves a failed investigation without an answer; there is no alternate model or synthetic fallback. Existing local AI starter scripts/configuration are reused, with no new environment variables or paid provider requirement.

## API

All routes are below `/api/v1/businesses/{business_id}/analyst`:

| Method | Route | Behavior |
| --- | --- | --- |
| POST | `/investigations` | Validate scope, capture operational inputs, plan, execute and select findings. Returns 201 on completed/partial analysis; explicit 4xx/503 on failure with `investigation_id` when already saved. |
| GET | `/investigations` | Project up to 30 summaries belonging to the requesting user in this business. |
| GET | `/investigations/{id}` | Return saved findings, parameters, captured time, hashes and execution metadata after access/integrity checks. |
| GET | `/investigations/{id}/sources?resource=orders&limit=25&offset=0` | Inspect frozen operational values. |
| GET | `/investigations/{id}/export` | Download completed findings, assumptions, sources, timings and limits as CSV. |

Input fields: `question` (5–1500 characters), `start`, `end`; optional `product_sku`, `model_data_scope` (`real` or `demo`), `forecast_run_id`, `churn_run_id`, `scenario_run_ids` (up to two), `document_ids` (up to five). Unknown fields, model-generated arguments and client business-ID overrides are rejected. Dates contain 1–366 business-local days, cannot end in the future, and must allow a preceding equal-length period. Natural-language date words never override these explicit dates.

Owners, administrators and analysts may start investigations. Members may read only their own saved investigations; being business owner does not grant access to another user's analyst history. Every tool rechecks its underlying business permission. Selected model, scenario and document IDs are checked in the authenticated business before planning. Document visibility is filtered before retrieval and rechecked before synthesis, publication, saved reads, source inspection and exports. Administrator-captured investigations are blocked after a downgrade to a non-administrator role. Losing analyst execution permission during generation prevents publication.

## Tools

| Tool | Evidence / constraints |
| --- | --- |
| `get_business_metrics` | Always included. Current/prior equal-length Decimal financial totals, completeness and accounting change bridge. |
| `query_sales` | Up to ten products ranked by recorded current paid revenue, with units, costs, changes and captured item IDs. |
| `query_inventory` | Up to twenty captured products, quantities/current costs and reporting-period stock-cover rules. |
| `query_customers` | Recorded activity/retention cohort and up to ten purchasers by recorded revenue. |
| `query_expenses` | Paid expense-category totals, source IDs, changes and exact-period coverage. |
| `search_business_documents` | Hybrid retrieval, role/document scope, up to three exact source excerpts; text is untrusted evidence. |
| `run_sales_forecast` | Seven-period saved-artifact inference from an explicitly selected or active sales model of the chosen scope; evaluation and source-change monitoring. |
| `predict_customer_churn` | Up to ten saved customer-inactivity estimates at their original cutoff. Uncalibrated proxy, not confirmed loss. |
| `detect_anomalies` | Selected-window rolling revenue diagnostics, with 28 prior days for warm-up; needs earlier paid history and does not prove import completeness or a cause. |
| `run_what_if_simulation` | Reproduce the first explicitly selected reviewed scenario from its original snapshot/assumptions; no new run is saved. |
| `compare_scenarios` | Compare two explicitly selected saved scenarios using the same baseline. |
| `generate_business_report` | Read-only captured financial report with definitions, freshness and assumptions; the investigation CSV exports its evidence. Broader reports belong to Phase 9. |

Financial/operational tools match Overview and include real plus labelled demo records, with demonstration flags retained. Model scope is separate and explicit. Pending/cancelled/refunded orders and voided expenses are excluded as in Phase 3. Unknown historical costs/expense coverage remain incomplete. Current stock is not time-travelled to the reporting-period end. The private captured inputs omit customer/supplier email addresses.

## Execution and evidence

Source capture coordinates briefly with the existing business write lock. The lock is released before model calls. Every subsequent tool checks membership/permission, then persists its ID, name, validated arguments, permission, timestamps, duration, status, structured output and fact IDs. A tool failure is explicit in the trail; a partial answer can use only the remaining evidence. No unrestricted execution loop or tool retry generated by the model exists.

Model planning and selection use constrained JSON schemas and independent backend validation. Findings cite only generated fact IDs; unsupported IDs, injected fields and arbitrary prose are rejected. Review recommendations come from a small server-defined set, with no consequential actions. Document findings are exact retrieved excerpts; this checks quote integrity without certifying semantic relevance or policy truth. Actual token counts are retained when supplied by the provider; estimated cost remains unknown.

`analyst_investigations` stores business/user, captured role, question, request correlation ID, model/version, parameters, source snapshot/hash, plan, execution trail, response/error, status and timestamps. A database trigger protects inputs and finalized evidence. Saved reads validate source/evidence hashes. Operational copies persist independently of later refunds or edits. Document visibility remains live even for historical evidence, so later restriction/deletion can block a saved investigation. There is no shared conversation memory: each question has explicit scope and an independent private investigation.

Limits: 5,000 operational source records per business for this initial analyst; 30 retained investigations per business; ten attempts per operator/business/hour; one concurrent investigation per operator/business through a token-checked 300-second Redis lease. Planning chooses at most three optional tools; total is four. The generation budget is 240 seconds with bounded context/output. The same-origin proxy allows 300 seconds. Stale running records older than five minutes become failed when their owner refreshes history. Process/connection failures may interrupt work; nothing is silently retried or deployed.

Unit/integration provider doubles are test-only. Actual local-model acceptance must be recorded separately in the progress log; these boundaries do not certify production security, broad answer quality, causal inference or financial decision suitability.
