from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, localcontext

from app.data.calculations import ZERO, financial_summary, line_amounts, money
from app.data.service import json_ready

VERSION = "1"
FIELDS = ["revenue", "cogs", "gross_profit", "gross_margin_pct", "recorded_expenses", "operating_profit"]
LIMIT = Decimal("99999999999999.9999")


def difference(before, after):
    changes = {}
    for key in FIELDS:
        a, b = before[key], after[key]
        delta = b-a if a is not None and b is not None else None
        changes[key] = {"baseline": a, "scenario": b, "absolute_change": delta,
            "percentage_change": (delta/abs(a)*100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if delta is not None and a and key != "gross_margin_pct" else None,
            "unit": "percentage_points" if key == "gross_margin_pct" else "currency"}
    return changes


def calculate(inputs, parameters):
    """No database, clock, randomness, LLM or operational writes."""
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_UP
        try:
            central = _case(inputs, parameters)
            cases = []
            if Decimal(str(parameters["price_change_pct"])):
                for elasticity in dict.fromkeys(parameters.get("sensitivity_elasticities", [])):
                    case = _case(inputs, parameters | {"price_elasticity": elasticity})
                    cases.append({"elasticity": str(elasticity), "metrics": case["metrics"], "demand_units": case["demand_units"]})
            # Extremes describe only these assumptions; they are not probabilistic bounds.
            ranked = [row for row in cases if row["metrics"]["operating_profit"] is not None]
            central["sensitivity"] = cases
            central["sensitivity_extremes"] = {"best_operating_profit": max((row["metrics"]["operating_profit"] for row in ranked), default=None), "worst_operating_profit": min((row["metrics"]["operating_profit"] for row in ranked), default=None), "definition":"Best/worst only among the supplied elasticity assumptions; no probability or guarantee."}
            return json_ready(central)
        except (InvalidOperation, OverflowError) as error:
            raise ValueError("Scenario exceeds supported numeric precision or range") from error


def _case(inputs, p):
    sources, business = inputs["sources"], inputs["business"]
    currency, start, end = business["currency"], inputs["start"], inputs["end"]
    d = lambda key: Decimal(str(p[key]))
    products = {row["id"]: row for row in sources["products"]}
    target = next((row for row in products.values() if row["sku"] == p.get("product_sku")), None)
    if p.get("product_sku") and target is None: raise ValueError("Product SKU does not exist in the saved baseline")
    supplier = next((row for row in sources["suppliers"] if row["external_id"] == p.get("supplier_external_id")), None)
    if p.get("supplier_external_id") and supplier is None: raise ValueError("Supplier reference does not exist in the saved baseline")
    inventory_enabled = "inventory" in business["modules"]
    if (p["stock_constrained"] or d("replenishment_units")) and not inventory_enabled:
        raise ValueError("Stock constraints and replenishment require an inventory-enabled baseline")
    paid = {row["id"] for row in sources["orders"] if row["status"] == "paid" and start <= row["ordered_on"] <= end}
    items = [row for row in sources["order_items"] if row["order_id"] in paid]
    if not items: raise ValueError("Select a baseline with paid sale lines in its reporting period")
    price_factor = 1+d("price_change_pct")/100
    demand_factor = 1+d("demand_change_pct")/100
    loss_factor = 1-d("customer_loss_pct")/100
    elasticity = Decimal(str(p["price_elasticity"])) if p.get("price_elasticity") is not None else ZERO
    response_factor = price_factor**elasticity
    planned, grouped, selected = {}, {}, set()
    for row in items:
        affected = target is None or row["product_id"] == target["id"]
        if affected and d("price_change_pct") and not Decimal(row["unit_price"]):
            raise ValueError("Price elasticity requires positive baseline prices; choose another SKU or use a demand-change assumption")
        if affected: selected.add(row["id"])
        factor = response_factor*demand_factor*loss_factor if affected else Decimal(1)
        quantity = (Decimal(row["quantity"])*factor).quantize(Decimal("0.001"))
        if quantity > Decimal("1000000000"): raise ValueError("Hypothetical line quantity exceeds one billion units")
        planned[row["id"]] = quantity
        grouped.setdefault(row["product_id"], []).append(row)
    balances = {row["product_id"]: Decimal(row["quantity"]) for row in sources["balances"]}
    inventory, amounts, purchased = [], [], money(ZERO, currency)
    for product_id, product in products.items():
        incoming = d("replenishment_units") if target and product_id == target["id"] else ZERO
        purchase_cost = Decimal(str(p["replenishment_unit_cost"])) if p.get("replenishment_unit_cost") is not None else (Decimal(product["unit_cost"]) if product["unit_cost"] is not None else None)
        if incoming and purchase_cost is None: raise ValueError("Provide a replenishment unit-cost assumption for a product with unknown current cost")
        purchased += money(incoming*purchase_cost, currency) if incoming else ZERO
        current = balances.get(product_id, ZERO)
        available = current+incoming
        rows = grouped.get(product_id, [])
        demand = sum((planned[row["id"]] for row in rows), ZERO)
        capped = p["stock_constrained"] and demand > available
        remaining, served = available, ZERO
        for row in rows:
            quantity = planned[row["id"]]
            if capped:
                quantity = min(remaining, (quantity*available/demand).quantize(Decimal("0.001"), rounding=ROUND_DOWN))
                remaining -= quantity
            served += quantity
            price = Decimal(row["unit_price"])*(price_factor if row["id"] in selected else 1)
            cost_affected = product.get("supplier_id") == supplier["id"] if supplier else row["id"] in selected
            cost = Decimal(row["unit_cost"])*(1+d("unit_cost_change_pct")/100 if cost_affected else 1) if row["unit_cost"] is not None else None
            discount = min(money(quantity*price, currency), money(Decimal(row["discount_amount"])*quantity/Decimal(row["quantity"])*(price_factor if row["id"] in selected else 1), currency))
            if quantity:
                revenue, cogs, _ = line_amounts(quantity, price, cost, discount, ZERO, currency)
            else:
                revenue, cogs = money(ZERO, currency), money(ZERO, currency)
            amounts.append((revenue, cogs))
        if inventory_enabled:
            inventory.append({"sku":product["sku"], "current_stock":current, "incoming_units":incoming, "planned_demand":demand, "fulfilled_units":served,
                "unfulfilled_units":demand-served, "projected_closing_units":max(ZERO, available-served), "additional_units_needed":max(ZERO, served-available),
                "stock_constrained":p["stock_constrained"], "replenishment_unit_cost":purchase_cost if incoming else None})
    expense_rows = [row for row in sources["expenses"] if row["status"] == "paid" and start <= row["incurred_on"] <= end]
    expenses = []
    for row in expense_rows:
        factor = 1+d("marketing_change_pct")/100 if row["category"] == "marketing" else (1+d("employee_cost_change_pct")/100 if row["category"] == "payroll" else 1)
        expenses.append(money(Decimal(row["amount"])*factor, currency))
    complete = any(row["start_date"] == start and row["end_date"] == end and row["complete"] for row in sources["expense_coverage"])
    metrics = {key:value for key,value in financial_summary(amounts, expenses, 0, currency, complete).items() if key in FIELDS}
    original = [line_amounts(Decimal(row["quantity"]), Decimal(row["unit_price"]), Decimal(row["unit_cost"]) if row["unit_cost"] is not None else None, Decimal(row["discount_amount"]), Decimal(row["tax_amount"]), currency) for row in items]
    before = {key:value for key,value in financial_summary([(row[0],row[1]) for row in original], [Decimal(row["amount"]) for row in expense_rows], len(paid), currency, complete).items() if key in FIELDS}
    if any(abs(value) > LIMIT for value in [*metrics.values(), purchased] if value is not None): raise ValueError("Scenario totals exceed the supported monetary range")
    categories = {row["category"] for row in expense_rows}
    warnings = []
    if d("marketing_change_pct") and "marketing" not in categories: warnings.append("No paid marketing expenses in this baseline; a percentage change adds no new budget.")
    if d("employee_cost_change_pct") and "payroll" not in categories: warnings.append("No paid payroll expenses in this baseline; a percentage change adds no new payroll cost.")
    if not selected: warnings.append("The chosen product has no paid sale lines in this reporting period.")
    if metrics["operating_profit"] is None: warnings.append("Operating profit remains incomplete because baseline cost or expense coverage is incomplete.")
    return {"kind":"hypothetical_simulation", "implementation_version":VERSION, "currency":currency, "timezone":business["timezone"], "baseline_period":{"start":start,"end":end}, "baseline_captured_at":inputs["captured_at"],
        "demo_records_present":any(row.get("is_demo") for values in sources.values() for row in values), "baseline_metrics":before, "metrics":metrics, "changes":difference(before,metrics), "inventory":inventory if inventory_enabled else None,
        "demand_units":sum(planned.values(), ZERO), "replenishment_cash_outlay":purchased, "warnings":warnings,
        "methodology":["Replay the saved reporting-period sale mix as a hypothetical period of the same length. This is not a sales forecast.", "For selected products, units = baseline line units × (1 + price %/100)^elasticity × (1 + demand %/100) × (1 − additional customer-loss %/100). Elasticity is an operator assumption, not a fitted estimate.", "Units round to 0.001. Optional stock constraints proportionally allocate each product's available stock, rounding allocations down so stock is never exceeded.", "Revenue = rounded hypothetical line quantity × historical unit price × price factor, less proportionally scaled discounts. Tax is excluded. COGS uses historical line costs × the cost factor; unknown nonzero-line costs remain unknown.", "Supplier selection changes the cost-factor scope only; otherwise costs follow the product scope. Marketing/payroll percentages change only matching recorded paid expense categories, with no automatic demand or productivity benefit.", "Replenishment uses an explicit cost assumption or saved current unit cost. Its cash outlay is separate from operating expenses and COGS; inventory purchases are not immediately expensed again.", "Without stock constraints, calculated revenue assumes supply is available; additional units needed are disclosed. Current stock is taken at capture, not at the historical reporting end.", "Operating profit requires the baseline's exact-period expense coverage and complete applicable historical line costs. Additional customer loss is a uniform demand assumption, not a calibrated churn prediction.", "Rounding and all monetary arithmetic use Decimal with fixed precision 34. Sensitivity cases vary only the supplied price-elasticity assumption; outcomes are neither guaranteed nor probabilistic bounds."]}
