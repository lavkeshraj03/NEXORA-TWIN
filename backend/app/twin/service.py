from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select

from app.data.calculations import ZERO, financial_summary, line_amounts, money
from app.data.models import ExpenseCoverage, InventoryBalance, OrderItem
from app.data.service import MODELS, json_ready
from app.ml.datasets import fingerprint
from app.ml.models import ModelRun

VERSION = "1"
MAX_SOURCES = 20000
DEFINITIONS = {
    "revenue": "Paid sale lines: quantity × historical unit price, rounded per line, less discounts; tax excluded.",
    "cogs": "Paid sale-line quantities × explicit historical unit costs; incomplete when any cost is unknown.",
    "gross_profit": "Revenue less complete historical COGS.",
    "gross_margin_pct": "Gross profit / revenue × 100; undefined at zero revenue.",
    "recorded_expenses": "Paid expenses incurred within the reporting period; voided expenses excluded.",
    "operating_profit": "Gross profit less expenses; requires known line costs and confirmed expense coverage for this exact period.",
    "average_order_value": "Revenue / distinct paid orders in the reporting period.",
    "paid_orders": "Distinct paid orders in the reporting period; pending, cancelled and refunded orders excluded.",
}


def scalar_row(row):
    # Do not copy customer/supplier email addresses into retained snapshots.
    return json_ready({column.name: getattr(row, column.name) for column in row.__table__.columns if column.name != "email"})


def capture(db, business, start, end):
    sources, remaining = {}, MAX_SOURCES
    models = dict(MODELS) | {"order_items": OrderItem, "balances": InventoryBalance, "expense_coverage": ExpenseCoverage}
    for key, model in models.items():
        rows = db.scalars(select(model).where(model.business_id == business.id).order_by(*model.__table__.primary_key.columns).limit(remaining+1)).all()
        if len(rows) > remaining:
            raise HTTPException(422, f"Snapshots support at most {MAX_SOURCES} operational source records per business")
        remaining -= len(rows)
        sources[key] = [scalar_row(row) for row in rows]
    active = db.scalars(select(ModelRun).where(ModelRun.business_id == business.id, ModelRun.active.is_(True)).order_by(ModelRun.id).limit(21)).all()
    if len(active) > 20:
        raise HTTPException(422, "Snapshots support at most 20 active models")
    forecasts = []
    for run in active:
        if run.implementation_version != "1" or fingerprint(run.dataset) != run.dataset_hash:
            raise HTTPException(409, "An active model failed its integrity/version check")
        forecasts.append(json_ready({"run_id": run.id, "task": run.task, "data_scope": run.data_scope, "algorithm": run.algorithm, "implementation_version": run.implementation_version, "dataset_hash": run.dataset_hash, "created_at": run.created_at, "config": run.config, "result": run.result}))
    inputs = json_ready({"implementation_version": VERSION, "captured_at": datetime.now(timezone.utc), "start": start, "end": end,
        "business": {"id": business.id, "name": business.name, "business_type": business.business_type, "currency": business.currency, "timezone": business.timezone, "modules": business.modules},
        "sources": sources, "forecasts": forecasts})
    return {"inputs": inputs, "state": reconstruct(inputs)}


def reconstruct(inputs):
    """Pure transformation: only stored inputs, Decimal arithmetic, no DB or clock."""
    sources, business = inputs["sources"], inputs["business"]
    start, end, currency = inputs["start"], inputs["end"], business["currency"]
    orders = [row for row in sources["orders"] if start <= row["ordered_on"] <= end and row["status"] == "paid"]
    ids = {row["id"] for row in orders}
    items = [row for row in sources["order_items"] if row["order_id"] in ids]
    expenses = [row for row in sources["expenses"] if start <= row["incurred_on"] <= end and row["status"] == "paid"]
    complete = any(row["start_date"] == start and row["end_date"] == end and row["complete"] for row in sources["expense_coverage"])
    lines = [line_amounts(Decimal(row["quantity"]), Decimal(row["unit_price"]), Decimal(row["unit_cost"]) if row["unit_cost"] is not None else None, Decimal(row["discount_amount"]), Decimal(row["tax_amount"]), currency) for row in items]
    metrics = financial_summary([(row[0], row[1]) for row in lines], [Decimal(row["amount"]) for row in expenses], len(orders), currency, complete)
    missing = sum(row["unit_cost"] is None for row in items)
    period_days = (date.fromisoformat(end)-date.fromisoformat(start)).days+1
    products, inventory = {row["id"]: row for row in sources["products"]}, []
    balances = {row["product_id"]: row for row in sources["balances"]}
    units = {}
    for row in items:
        units[row["product_id"]] = units.get(row["product_id"], ZERO)+Decimal(row["quantity"])
    inventory_enabled = "inventory" in business["modules"]
    if inventory_enabled:
        for product_id, product in products.items():
            balance = balances.get(product_id)
            quantity = Decimal(balance["quantity"]) if balance else ZERO
            cost = Decimal(product["unit_cost"]) if product["unit_cost"] is not None else None
            daily = units.get(product_id, ZERO)/period_days
            inventory.append({"product_id": product_id, "sku": product["sku"], "name": product["name"], "quantity": quantity, "unit_cost": cost,
                "value": money(quantity*cost, currency) if cost is not None else (money(ZERO, currency) if not quantity else None),
                "period_daily_units": daily.quantize(Decimal("0.001")), "days_cover": (quantity/daily).quantize(Decimal("0.01")) if daily else None,
                "below_seven_days_cover": bool(daily and quantity < daily*7), "is_demo": product["is_demo"], "balance_updated_at": balance["updated_at"] if balance else None})
    active_customers = {row["customer_id"] for row in orders}
    eligible = {row["customer_id"] for row in sources["orders"] if row["ordered_on"] < start and row["status"] == "paid"}
    retained = len(eligible & active_customers)
    updates = [row["updated_at"] for values in sources.values() for row in values if row.get("updated_at")]
    freshest = max(updates, default=None)
    fresh_days = (datetime.fromisoformat(inputs["captured_at"])-datetime.fromisoformat(freshest)).total_seconds()/86400 if freshest else None
    demo_count = sum(bool(row.get("is_demo")) for key, values in sources.items() if key not in {"order_items", "balances", "expense_coverage"} for row in values)
    zero = sum(row["quantity"] == 0 for row in inventory)
    low = sum(row["below_seven_days_cover"] for row in inventory)
    health = [
        {"key": "cost_coverage", "status": "warning" if missing else ("ok" if items else "unknown"), "detail": f"{missing} paid sale lines have unknown cost; {len(items)} lines observed."},
        {"key": "expense_coverage", "status": "ok" if complete else "unknown", "detail": "Expense coverage confirmed for this exact period." if complete else "Complete operating profit cannot be established without exact-period expense coverage."},
        {"key": "source_freshness", "status": "unknown" if freshest is None else ("warning" if fresh_days > 7 else "ok"), "detail": "No source updates recorded." if freshest is None else f"Latest recorded source update: {freshest}. Warning threshold: seven days at capture; not proof of complete imports."},
        {"key": "inventory_cover", "status": ("warning" if low else "ok") if inventory_enabled and products else "unknown", "detail": f"{low} products below seven days of reporting-period demand; {zero} products at zero stock." if inventory_enabled else "Inventory module disabled."},
    ]
    provenance = {}
    sale_ids, expense_ids = [row["id"] for row in items], [row["id"] for row in expenses]
    for key in metrics:
        provenance[key] = {"kind": "calculated_historical", "recorded_at": inputs["captured_at"], "period": {"start": start, "end": end}, "definition": DEFINITIONS.get(key, key),
            "sources": {"orders": sorted(ids) if key != "recorded_expenses" else [], "order_items": sale_ids if key != "recorded_expenses" else [], "expenses": expense_ids if key in {"recorded_expenses", "operating_profit"} else [], "expense_coverage": complete if key == "operating_profit" else None}}
    provenance["inventory_value"] = {"kind": "calculated_current_at_capture", "recorded_at": inputs["captured_at"], "definition": "Current recorded balances × current product unit cost, rounded per product; unknown nonzero-stock costs make value incomplete. Independent of reporting-period end.", "sources": {"products": list(products) if inventory_enabled else [], "balances": list(balances) if inventory_enabled else []}}
    provenance["customer_retention_pct"] = {"kind": "calculated_historical", "recorded_at": inputs["captured_at"], "definition": "Customers with a paid purchase before the reporting period who also purchased in the period / eligible prior purchasers × 100. Unknown earlier imports limit the cohort.", "sources": {"orders": [row["id"] for row in sources["orders"] if row["status"] == "paid" and row["ordered_on"] <= end]}}
    return json_ready({"kind": "business_state", "business": business, "captured_at": inputs["captured_at"], "period": {"start": start, "end": end, "days": period_days},
        "metrics": metrics, "metric_provenance": provenance, "expenses_complete": complete, "missing_cost_lines": missing,
        "counts": {key: len(sources[key]) for key in MODELS}, "demo_records": demo_count,
        "customers": {"total": len(sources["customers"]), "active_in_period": len(active_customers), "eligible_retention": len(eligible), "retained": retained, "retention_pct": (Decimal(retained)/len(eligible)*100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if eligible else None},
        "orders": {status: sum(row["status"] == status and start <= row["ordered_on"] <= end for row in sources["orders"]) for status in ["paid", "pending", "cancelled", "refunded"]},
        "inventory": inventory if inventory_enabled else None, "inventory_value": sum((row["value"] for row in inventory), money(ZERO, currency)) if inventory_enabled and all(row["value"] is not None for row in inventory) else None,
        "suppliers": {"total": len(sources["suppliers"]), "linked_products": sum(bool(row.get("supplier_id")) for row in products.values()), "purchasing_state": "Unavailable: purchase orders are not implemented in the operational foundation."},
        "data_updated_at": freshest, "source_versions": {key: {"records": len(rows), "sha256": fingerprint(rows)} for key, rows in sources.items()},
        "forecasts": inputs["forecasts"], "health": health,
        "assumptions": ["All real and labelled demonstration records are included; demo_records reports their presence. Keep real and demo data in separate businesses.", "Reporting-period paid sales and expenses use business-local calendar dates. Full refunds restate the original period; partial refunds are unsupported.", "Inventory and master records are current at capture, not reconstructed as of the reporting-period end. Valuation uses current unit cost, not FIFO.", "Seven-day stock-cover warnings use mean recorded units per reporting-period calendar day; missing imports can understate demand. They are deterministic rules, not ML probabilities.", "Active model results are copied as forecasts at their original cutoff, not retrained or treated as actuals. No active model means no forecast summary.", "No simulation values or real-world actions are produced. Health indicators describe recorded data; they are not a comprehensive business rating."],
        "transformation_version": VERSION})


def verified(snapshot):
    if snapshot.implementation_version != VERSION or snapshot.payload["inputs"]["implementation_version"] != VERSION or snapshot.payload["inputs"]["business"]["id"] != str(snapshot.business_id) or fingerprint(snapshot.payload) != snapshot.content_hash:
        raise HTTPException(409, "Snapshot integrity/version check failed")
    if reconstruct(snapshot.payload["inputs"]) != snapshot.payload["state"]:
        raise HTTPException(409, "Stored state does not reproduce from its source inputs")
    return snapshot.payload["state"]


def summary(snapshot):
    state = snapshot.payload["state"]
    return {"id": str(snapshot.id), "name": snapshot.name, "created_at": snapshot.created_at.isoformat(), "content_hash": snapshot.content_hash, "implementation_version": snapshot.implementation_version,
        "period": state["period"], "currency": state["business"]["currency"], "demo_records": state["demo_records"]}


def compare(left, right):
    if any(left["business"][key] != right["business"][key] for key in ["id", "currency", "timezone"]):
        raise HTTPException(422, "Compare snapshots from the same business, currency and timezone")
    changes = {}
    for key, before in left["metrics"].items():
        after = right["metrics"][key]
        a, b = Decimal(str(before)) if before is not None else None, Decimal(str(after)) if after is not None else None
        delta = b-a if a is not None and b is not None else None
        changes[key] = {"before": before, "after": after, "absolute_change": delta,
            "percentage_change": (delta/abs(a)*100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if delta is not None and a and key != "gross_margin_pct" else None,
            "unit": "percentage_points" if key == "gross_margin_pct" else ("orders" if key == "paid_orders" else left["business"]["currency"])}
    return json_ready({"metrics": changes, "same_period": left["period"] == right["period"], "equal_period_length": left["period"]["days"] == right["period"]["days"],
        "left_period": left["period"], "right_period": right["period"], "source_changes": [key for key in left["source_versions"] if left["source_versions"][key]["sha256"] != right["source_versions"][key]["sha256"]],
        "definition": "Right snapshot minus left snapshot. Raw totals are not normalized for unequal periods; source changes can restate the same historical period. Undefined/missing values have no computed change; zero baselines have no percentage change."})
