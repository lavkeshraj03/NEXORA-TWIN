# Operational data — Phase 3

All paths start `/api/v1/businesses/{business_id}`. Every request checks membership. All roles can read; owners and administrators can write. Mutations require the session cookie, allowed Origin and CSRF token.

| Route | Behavior |
|---|---|
| GET /data-schema | Profile labels, manual/import fields and limits |
| GET /dashboard?start=YYYY-MM-DD&end=YYYY-MM-DD | Calculated tenant metrics and daily trend, maximum 366 days |
| PUT /expense-coverage | Explicit completeness confirmation for the exact reporting period |
| GET /{resource} | Search, status, sort, limit and offset |
| POST /{resource} | Manual entry: `{ "rows": [...] }`, up to 100 |
| GET /{resource}/{id} | Traceable source record |
| PATCH /orders/{id}, /expenses/{id} | Allowed status transition with a reason |
| GET /{resource}/export | CSV download, up to 10,000 records |
| GET /transactions | Projection of current paid sales/expenses, never an additional ledger |
| POST /imports?resource=...&filename=... | Raw CSV/XLSX/JSON body; creates a preview |
| GET /imports, /imports/{id} | History and saved preview |
| POST /imports/{id}/validate | `{ "mapping": { "business_field": "source_column" } }` |
| POST /imports/{id}/commit | `{ "confirmed": true, "preview_updated_at": "..." }` |
| GET /imports/{id}/errors | Download row-level CSV errors |

Resources: customers, suppliers, products, orders, inventory, expenses. Services omit inventory. Upload customers/suppliers before products; upload products before orders or inventory. Orders contain one row per SKU; repeated external order IDs group lines only when headers agree. References must already exist in the same business.

Imports support UTF-8 CSV, one-sheet XLSX and flat JSON object arrays. Limits: 2 MiB, 1000 rows, 50 distinct columns and 1000 characters per cell. Correct all errors before confirming; a failed validation imports no records. Confirmation revalidates against current data under a business lock. Identical file content is deduplicated per business/resource; committed confirmations are idempotent. Mapping changes require validation and a fresh acknowledgement. Stale preview timestamps return 409. Downloads neutralize spreadsheet commands.

Financial calculations use Decimal, explicit minor units and ROUND_HALF_UP. Paid orders qualify; pending, cancelled and fully refunded orders are excluded. Refunds restate the original sale period; partial refunds are unsupported. Revenue is quantity × unit price minus line discount, excluding tax. COGS uses explicit historical line costs. Unknown cost remains incomplete. Average order value divides net sales by qualifying order count. Operating profit requires known line costs and confirmed expense completeness for the exact period; new/voided expenses retract overlapping confirmations. Inventory value is a current snapshot at current cost, independent of sales-report dates. Sales do not automatically alter stock; record explicit movements. Restocks are positive; sales/waste are negative; adjustments may have either sign.

Money is returned as exact decimal strings. Dates are business-local calendar dates. Labelled demo records are counted visibly; there is no silent seed. See datasets/README.md for synthetic CSV examples. This milestone does not implement FIFO, multiple inventory locations, partial refunds, manufacturing BOM/production, service utilization or an accounting general ledger.
