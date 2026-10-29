# Phase 9 local verification — 29 October 2026

Implemented tenant-scoped relational graph snapshots, source-backed neighborhoods, live document visibility, entity search and visible CSV export. Frozen private reports cover closed calendar months, revenue/expenses, inventory risk, saved sales forecasts, saved customer-inactivity estimates, same-baseline scenarios and private analyst investigations. CSV and paginated PDF exports retain source/model/assumption metadata. No graph database, extra AI call or dependency was introduced.

The complete PostgreSQL/Redis backend suite passed **153 tests** in **35.56 seconds**, including graph composite FKs, role/document filtering, immutable evidence, report source boundaries, numeric rules, retention caps, Unicode CSV handling and PDF parsing. All **37 frontend tests** and strict TypeScript passed. Revision **0009_insights** applied and Alembic found no schema drift. Production backend/worker/migration/frontend images built and all five services reached healthy state.

Actual HTTP acceptance passed through Next.js, FastAPI and PostgreSQL: real relationships, idempotent refresh, bounded relationship filters, graph CSV, financial report totals, PDF binary preservation and strict PDF parsing, source-hash CSV, stock-risk arithmetic, closed-month reporting, cross-business denial, unchanged operational source versions and frozen report values after a refund. Its temporary account and businesses were removed. The binary proxy fix forwards ArrayBuffer instead of text, preserving PDF byte offsets.

Nexa has **1,055 graph nodes and 2,468 edges** from existing structured records. Seven labelled demo reports were saved using genuine snapshots, evaluated models, reviewed scenarios and the owner's saved investigation. Their generated PDFs parsed successfully (two or three pages each). One September calendar-month snapshot was added for monthly reporting; no orders, customers, expenses, stock or models were changed. Original October revenue/operating profit remain INR 150,562 / INR 42,712.

PDFs use portable Courier/WinAnsi fonts. Unsupported characters remain visible as Unicode escapes; CSV/JSON preserve full Unicode. This is a documented export limitation, not full multilingual typesetting. Broader production security, performance, accessibility and fresh-install acceptance remain Phase 10 work. See graph-reports-api.md for permissions, source semantics, limits and walkthrough.

Measured HTTP report:

```json
{
  "status": "passed",
  "checks": [
    "real frontend proxy",
    "source-backed graph",
    "idempotent graph refresh",
    "bounded relationship filter",
    "graph CSV",
    "financial report totals",
    "binary PDF preserved through proxy",
    "strict PDF parsing",
    "report CSV source hashes",
    "inventory risk arithmetic",
    "closed-month report",
    "cross-business denial",
    "no operational changes",
    "frozen report after refund"
  ],
  "graph_nodes": 9,
  "graph_edges": 14,
  "pdf_pages": 2,
  "pdf_bytes": 6063
}
```
