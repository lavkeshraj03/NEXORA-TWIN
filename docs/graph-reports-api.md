# Knowledge graph and reports — Phase 9

## Explore Nexa

Refresh http://localhost:3000/workspace, select **Nexa → Knowledge graph**. Search for **NX-PEN-01** with entity type **product**. Select a linked entity to move through its neighborhood. Use **supplies**, **contains**, **has balance** or **has movement** to focus the connections. The source panels show captured values, resource IDs, hashes and timestamps.

Each diagram shows at most twelve connections at once. Page through connections or search for a different customer, order, supplier or product. The list and SVG support keyboard navigation. **Refresh graph from records** creates a new snapshot only when its source values change; historical snapshots remain available. Only owners and administrators can build a graph. Read access follows current business membership and document visibility.

Open **Reports & exports**, select a saved report or generate one from a saved source. Review the result type, period, data freshness, definitions and limitations, then download **CSV** or **PDF**. Report history is private to your account within this business; being the business owner does not expose another member's reports.

Nexa's demonstration package includes financial, monthly, inventory-risk, sales-forecast, customer-inactivity, scenario-comparison and analyst-investigation examples. They remain labelled synthetic. Financial reports use recorded historical results; forecasts/inactivity reports use model estimates; scenario reports show hypothetical outcomes. None changes operational records, trains a model or activates one.

## Knowledge graph contract

Routes are under `/api/v1/businesses/{business_id}/knowledge-graph`:

| Method | Route | Behavior |
| --- | --- | --- |
| POST | `/refresh` | Capture structured source relationships atomically; return `unchanged=true` when the latest source hash matches. |
| GET | base route, optional `build_id` | Visible node/edge counts and kinds, capture time, methodology and visible-view hash. |
| GET | `/builds` | Up to five retained snapshot IDs/timestamps. |
| GET | `/nodes?build_id=…&kind=product&search=NX-PEN-01&limit=25&offset=0` | Search/filter/paginate visible entities. |
| GET | `/nodes/{id}?build_id=…&relationship=supplies&limit=12&offset=0` | A bounded neighborhood and original source evidence. |
| GET | `/export?build_id=…` | Export only currently visible nodes/relationships as CSV. |

PostgreSQL stores graph_builds, knowledge_nodes and knowledge_edges. Composite tenant/build/node foreign keys prevent cross-business or cross-snapshot endpoints. Nodes retain type, label, source reference, captured values/hash and timestamp. Edges retain their relationship and supporting row values/reference/hash. Saved evidence cannot be updated through the API or database update paths. Business deletion may cascade its graph.

Relationships come only from existing business ownership and foreign keys: customer → places → order; order → contains → product; supplier → supplies → product; product → stock movement/balance; business → its stored entities/documents. Cancelled/refunded/pending orders remain known relationships, with their captured statuses visible; graph existence does not imply paid revenue. No campaign influence, warehouse location, purchasing transaction or LLM-derived policy relation is invented. Unsupported extraction is not presented as verified knowledge.

Document nodes contain metadata, not raw document text. Administrator-only nodes and incident edges are filtered before counts, pagination, neighborhoods and exports. Captured administrator visibility remains restricted, and later restriction/deletion is checked against the live document. Archived operational values remain frozen after corrections; graph capture time is explicit. Refresh after source changes to see a new state.

Limits: 10,000 operational source records, 100 document metadata records, five snapshots per business, ten refresh attempts per operator/business/hour. Oversized builds fail atomically. Node pages contain at most 100 entries; neighborhood pages at most 50 (UI uses twelve). There is no separate graph database or external AI call.

## Report contract

Routes are under `/api/v1/businesses/{business_id}/reports`:

| Method | Route | Behavior |
| --- | --- | --- |
| POST | base route | Generate and freeze a named report from an authorized saved source. |
| GET | base route | Up to forty projected summaries belonging to the current user. |
| GET | `/{id}` | Verify hash/version and current access, then return frozen report sections. |
| GET | `/{id}/export/csv` | Download UTF-8 CSV with source/assumption metadata. |
| GET | `/{id}/export/pdf` | Download a deterministic, paginated PDF summary. |

Request fields: `name`, `kind`, and exactly the matching reference:

| Kind | Required source | Interpretation |
| --- | --- | --- |
| `monthly` | `snapshot_id` | One complete, closed calendar-month snapshot. |
| `revenue_expenses` | `snapshot_id` | Paid historical financial metrics for its reporting dates. |
| `inventory_risk` | `snapshot_id` | Captured stock and mean recorded reporting-period demand. |
| `sales_forecast` | `model_run_id` for sales | Saved-artifact forecast with original cutoff, evaluation and limits. |
| `customer_inactivity` | `model_run_id` for churn | Saved uncalibrated inactivity estimates; not confirmed losses. |
| `scenario_comparison` | Two `scenario_run_ids` | Reviewed scenarios sharing one saved baseline; hypothetical differences. |
| `investigation` | `investigation_id` owned by requester | Saved analyst findings, tool evidence and review steps. |

Sales reports accept `horizon` (1–30 periods; weekly at most twelve). Inventory-risk reports accept `lead_days` (1–180), `incoming_units` and `safety_units` (nonnegative, up to three decimal places). Incoming/safety assumptions apply independently to each SKU. Required quantity is the exact recorded mean daily units × lead time + safety; shortfall is max(0, required − captured stock − incoming). Displayed quantities round to 0.001. The reporting-window demand mean can differ from Forecasts & risk's current trailing-28-day calculation; the source dates and method are explicit.

Reports retain business identity, currency/timezone, period, source capture/freshness, result kind, demo flag, metrics/definitions, model information when relevant, source IDs/hashes/versions, assumptions and limitations. Inventory is current at capture, independently of the historical sales period. Unknown historical costs or exact-period expense coverage keep operating profit incomplete. No net-profit, exchange-rate, partial-refund or causal conclusion is fabricated.

Reports are frozen, not live dashboards. Their payload/hash and version are checked on read. Report generation/export is audited with actor and report ID, without copying sensitive content into audit logs. Owners, administrators and analysts can generate reports; members can read only their own authorized history. Administrator-captured reports are blocked after a downgrade. Investigation reports additionally recheck the original private investigation and current document access, including on exports. There is no public report sharing endpoint.

The browser proxy preserves binary PDF bytes. PDFs use standard portable Courier/WinAnsi fonts, support pagination and escape literal control syntax. Characters outside that repertoire appear as visible Unicode escapes; CSV and JSON preserve full Unicode text. CSV cells are protected against spreadsheet formula prefixes. Outputs reproduce stored report values; downloads never silently refresh a model or scenario. Limits: forty reports per business, twenty generation attempts per operator/business/hour, up to 1,000 inactivity estimates and a 100-page PDF cap. Use CSV or a smaller source if the PDF limit is exceeded. No new dependency, AI provider or environment variable is required.
