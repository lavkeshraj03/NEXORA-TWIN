# Digital twin — transformation version 1

All routes are under `/api/v1/businesses/{business_id}/twin`. Authentication and centralized business membership checks apply to every route. All members may read; owners, administrators and analysts may capture snapshots. Mutating HTTP requests require Origin and CSRF protection.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/current?start=YYYY-MM-DD&end=YYYY-MM-DD` | Calculate a current preview without saving it. |
| POST | `/snapshots` | Save `{name, start, end}` and return the captured state. |
| GET | `/snapshots` | List up to 50 saved snapshot summaries, newest first. |
| GET | `/snapshots/{id}` | Verify the content hash, reproduce state from saved inputs and return it. |
| GET | `/snapshots/{id}/sources?resource=orders&limit=25&offset=0` | Inspect saved source values, with pagination. |
| GET | `/compare?left={id}&right={id}` | Compare two verified snapshots belonging to this business. |

Reporting windows contain 1–366 business-local calendar days and cannot end after the current local day. Capturing is limited to 20 requests per user/business/hour, 50 retained snapshots per business, 20,000 operational source records and 20 active models per capture. Oversized requests fail explicitly and do not save partial snapshots. No external AI call or new dependency is required.

## Stored evidence and consistency

`twin_snapshots` stores tenant ID, optional creator, name, implementation version, SHA-256, timestamp and a JSONB payload. The payload contains business configuration, reporting dates, a capture timestamp, operational source values and copied active-model summaries/results. Customer/supplier email addresses are excluded. A business-row lock coordinates capture with the application's operational writes, model activation and settings changes. Out-of-band database writers must honor the same lock protocol.

The operational inputs contain customers, suppliers, products, orders, order items, inventory movements, balances, expenses and expense coverage. All are tenant-filtered and deterministically ordered. Each source collection has its own canonical SHA-256 version. The complete payload is hashed using sorted JSON keys and compact separators. Reads reject unsupported versions, a mismatched payload hash or a state that differs from pure reconstruction. A database update trigger protects captured evidence; creator nulling for account deletion remains supported. There is no update/delete snapshot API. Business deletion may cascade its snapshots.

The pure `app.twin.service.reconstruct` transformation has no database, wall clock, model call or random input. Historical financial formulas reuse the Decimal calculation authority from Phase 3. A transformation-version change must preserve the previous replay implementation or reject unsupported snapshots explicitly. Hashes detect corruption/inconsistency; they are not cryptographic signatures against a privileged database administrator.

## Interpretation

- **Observed at capture:** business settings, master records and current stock balances. Choosing an earlier reporting end does not time-travel inventory or recover an unrecorded earlier business state.
- **Calculated historical:** reporting-period paid sales, explicit historical costs, paid expenses, paid/pending/refunded/cancelled counts and activity retention. Pending/cancelled/refunded sales and voided expenses are excluded from financial totals. Tax is excluded; discounts and currency rounding follow Phase 3. Missing sale-line costs make COGS/gross profit incomplete. Operating profit additionally requires expense completeness confirmed for the exact reporting window.
- **Forecast:** only models explicitly active at capture are copied, including their original cutoffs/configurations, algorithms, dataset hashes, limitations and results. They are not refreshed or treated as actual performance. No active model means no forecast summary.
- **Hypothetical:** none in Phase 6; simulation belongs to Phase 7.

All real and labelled demo operational records are included, matching Overview. Demo counts and original row labels are retained. Keep demo and real records in separate businesses. Product valuation uses current unit cost, not FIFO. Product/supplier links are captured; purchasing state is explicitly unavailable because purchase orders are not yet implemented.

Financial metric provenance records the definition, capture timestamp, reporting period and qualifying source-line/expense IDs. Inventory rows retain product IDs, quantities, current costs and balance-update times. Source collections contain the underlying customer/supplier/product/order identifiers and timestamps needed for inspection and replay. Unknown values remain null rather than zero.

Health indicators use explicit rules, without a fabricated aggregate score: sale-cost completeness, exact-period expense coverage, latest recorded source update (seven-day warning threshold at capture) and inventory below seven days of average recorded reporting-period unit demand. Zero stock is counted separately. Missing imports can distort demand and freshness; a recent update does not establish data completeness. No-demand stock cover is undefined.

Comparisons return right minus left, source-version changes, absolute and percentage differences. Zero/missing baselines have no percentage change. Gross-margin differences use percentage points. Different period lengths are disclosed and totals are not normalized. Business/currency/timezone mismatches are rejected. Comparisons do not establish causation.

## Use with Nexa

Refresh the browser, select Nexa and open **Digital twin**. Set **2026-09-29–2026-10-28**, refresh current state, name it **Nexa October baseline** and save. It should reproduce revenue ₹150,562 and operating profit ₹42,712. Inspect the stock table, health rules, assumptions and source versions. The supplied numerical models remain unactivated until explicitly selected in Forecasts & risk; this correctly leaves the forecast section empty initially.

For a period comparison, save another snapshot for **2026-08-30–2026-09-28**, then select it on the left and October on the right. Both are 30-day periods; September's operating profit may be incomplete because only the October demonstration window has confirmed expense coverage. Neither action changes orders, expenses or inventory. To test corrections, use a separate disposable demo business rather than changing the prepared Nexa records.
