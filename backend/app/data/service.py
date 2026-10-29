from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.data.calculations import ZERO, financial_summary, line_amounts, money
from app.data.models import Customer, Expense, ExpenseCoverage, InventoryBalance, InventoryMovement, Order, OrderItem, Product, Supplier
from app.data.schemas import SCHEMAS
from app.models import AuditLog, Business

MODELS = {"customers": Customer, "suppliers": Supplier, "products": Product, "orders": Order, "inventory": InventoryMovement, "expenses": Expense}
LABELS = {
    "retail": {"customers":"Customers", "products":"Products", "orders":"Sales orders"},
    "restaurant": {"customers":"Guests", "products":"Menu items", "orders":"Restaurant orders"},
    "manufacturing": {"customers":"Customers", "products":"Finished goods", "orders":"Sales orders"},
    "services": {"customers":"Clients", "products":"Service offerings", "orders":"Sales invoices"},
    "wholesale": {"customers":"Trade customers", "products":"Catalog products", "orders":"Wholesale orders"},
}


def json_ready(value):
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def require_resource(resource: str):
    if resource not in MODELS:
        raise HTTPException(404, "Data resource not found")


def reference_context(db: Session, business_id: UUID) -> dict:
    result = {}
    for name, model, field in [("customers",Customer,"external_id"),("suppliers",Supplier,"external_id"),("products",Product,"sku")]:
        result[name] = {getattr(item, field): item for item in db.scalars(select(model).where(model.business_id == business_id))}
    result["balances"] = {item.product_id:item.quantity for item in db.scalars(select(InventoryBalance).where(InventoryBalance.business_id == business_id))}
    return result


def validate_rows(db: Session, business: Business, resource: str, rows: list[dict]) -> tuple[list, list[dict], dict]:
    require_resource(resource)
    if not 1 <= len(rows) <= 1000:
        raise HTTPException(422, "Submit 1–1000 rows per operation")
    try:
        money(ZERO,business.currency)
    except ValueError as failure:
        raise HTTPException(422,str(failure))
    context = reference_context(db, business.id)
    model = MODELS[resource]
    key = "sku" if resource == "products" else "external_id"
    existing = set(db.scalars(select(getattr(model,key)).where(model.business_id == business.id)))
    seen = set()
    groups = {}
    order_products = set()
    virtual_stock = context["balances"].copy()
    parsed, errors = [], []
    for number, row in enumerate(rows, start=2):
        try:
            clean = {field:value for field,value in row.items() if value is not None and value != ""}
            item = SCHEMAS[resource].model_validate(clean)
            external = getattr(item, key)
            if external in existing or (resource != "orders" and external in seen):
                raise ValueError("External identifier already exists in this business or occurs twice in the file")
            if resource == "inventory" and "inventory" not in business.modules:
                raise ValueError("Enable an inventory-supported business profile/module first")
            if hasattr(item, "currency") and item.currency not in (None, business.currency):
                raise ValueError("Currency must match the business; conversion is not performed")
            if resource == "products":
                if item.supplier_external_id and item.supplier_external_id not in context["suppliers"]:
                    raise ValueError("Supplier reference does not exist in this business")
                if item.initial_stock and "inventory" not in business.modules:
                    raise ValueError("Initial stock requires an enabled inventory module")
            if resource in {"orders", "inventory"}:
                if item.product_sku not in context["products"]:
                    raise ValueError("Product SKU does not exist in this business")
            if resource == "orders":
                if item.customer_external_id not in context["customers"]:
                    raise ValueError("Customer reference does not exist in this business")
                line_amounts(item.quantity, item.unit_price, item.unit_cost, item.discount_amount, item.tax_amount, business.currency)
                signature = (item.customer_external_id,item.ordered_on,item.status,item.currency,item.is_demo)
                if external in groups and groups[external] != signature:
                    raise ValueError("All lines of an order must share customer, date, status, currency, and demo label")
                if (external,item.product_sku) in order_products:
                    raise ValueError("Use one line per SKU per order; combine repeated SKU quantities")
                groups[external] = signature
                order_products.add((external,item.product_sku))
            if resource == "expenses" and money(item.amount, business.currency) != item.amount:
                raise ValueError("Expense amount must use the currency's minor-unit precision")
            if resource == "inventory":
                product_id = context["products"][item.product_sku].id
                quantity = virtual_stock.get(product_id, ZERO) + item.quantity_delta
                if quantity < 0 or quantity > Decimal("1000000000"):
                    raise ValueError("Inventory movement would produce negative or unsupported stock")
                virtual_stock[product_id] = quantity
            seen.add(external)
            parsed.append(item)
        except ValidationError as failure:
            for error in failure.errors(include_input=False, include_url=False):
                errors.append({"row":number,"field":".".join(map(str,error["loc"])),"message":error["msg"]})
        except ValueError as failure:
            errors.append({"row":number,"field":"record","message":str(failure)})
    return parsed, errors, context


def add_movement(db: Session, business_id: UUID, product_id: UUID, external: str, occurred_on: date, delta: Decimal, reason: str, is_demo: bool):
    balance = db.get(InventoryBalance, (business_id,product_id))
    if balance is None:
        balance = InventoryBalance(business_id=business_id, product_id=product_id, quantity=ZERO)
        db.add(balance)
    balance.quantity += delta
    movement = InventoryMovement(business_id=business_id, product_id=product_id, external_id=external, occurred_on=occurred_on, quantity_delta=delta, reason=reason, is_demo=is_demo)
    db.add(movement)
    return movement


def invalidate_expense_coverage(db: Session, business_id: UUID, dates: list[date]):
    if dates:
        db.execute(update(ExpenseCoverage).where(
            ExpenseCoverage.business_id == business_id,
            ExpenseCoverage.start_date <= max(dates),
            ExpenseCoverage.end_date >= min(dates),
        ).values(complete=False))


def persist_rows(db: Session, business: Business, resource: str, parsed: list, context: dict) -> int:
    orders = {}
    for item in parsed:
        values = item.model_dump()
        if resource in {"customers","suppliers"}:
            db.add(MODELS[resource](business_id=business.id, **values))
        elif resource == "products":
            stock = values.pop("initial_stock")
            supplier = values.pop("supplier_external_id")
            product = Product(business_id=business.id, supplier_id=context["suppliers"][supplier].id if supplier else None, **values)
            db.add(product)
            db.flush()
            if stock:
                add_movement(db, business.id, product.id, "opening-" + item.sku, datetime.now(ZoneInfo(business.timezone)).date(), stock, "opening", item.is_demo)
        elif resource == "orders":
            order = orders.get(item.external_id)
            if order is None:
                order = Order(business_id=business.id, external_id=item.external_id, customer_id=context["customers"][item.customer_external_id].id, ordered_on=item.ordered_on, status=item.status, currency=business.currency, is_demo=item.is_demo)
                db.add(order)
                db.flush()
                orders[item.external_id] = order
            db.add(OrderItem(business_id=business.id, order_id=order.id, product_id=context["products"][item.product_sku].id, quantity=item.quantity, unit_price=item.unit_price, unit_cost=item.unit_cost, discount_amount=item.discount_amount, tax_amount=item.tax_amount, is_demo=item.is_demo))
        elif resource == "inventory":
            add_movement(db, business.id, context["products"][item.product_sku].id, item.external_id, item.occurred_on, item.quantity_delta, item.reason, item.is_demo)
        elif resource == "expenses":
            values["currency"] = business.currency
            db.add(Expense(business_id=business.id, **values))
    if resource == "expenses":
        invalidate_expense_coverage(db, business.id, [item.incurred_on for item in parsed])
    business.data_status = "has_data"
    return len(parsed)


def record_dict(db: Session, resource: str, record, context: dict | None = None) -> dict:
    result = {column.name:getattr(record,column.name) for column in record.__table__.columns}
    context = context or reference_context(db, record.business_id)
    products = {item.id:item.sku for item in context["products"].values()}
    customers = {item.id:item.external_id for item in context["customers"].values()}
    suppliers = {item.id:item.external_id for item in context["suppliers"].values()}
    if resource == "products":
        result["supplier_external_id"] = suppliers.get(record.supplier_id)
        result["stock_quantity"] = context["balances"].get(record.id, ZERO)
    if resource == "orders":
        result["customer_external_id"] = customers.get(record.customer_id)
        items = db.scalars(select(OrderItem).where(OrderItem.business_id == record.business_id, OrderItem.order_id == record.id)).all()
        lines = [line_amounts(item.quantity,item.unit_price,item.unit_cost,item.discount_amount,item.tax_amount,record.currency) for item in items]
        result["net_sales"] = sum((line[0] for line in lines), ZERO)
        result["tax_amount"] = sum((item.tax_amount for item in items), ZERO)
        result["items"] = [{"product_sku":products.get(item.product_id),"quantity":item.quantity,"unit_price":item.unit_price,"unit_cost":item.unit_cost,"discount_amount":item.discount_amount,"tax_amount":item.tax_amount} for item in items]
    if resource == "inventory":
        result["product_sku"] = products.get(record.product_id)
        result["current_stock"] = context["balances"].get(record.product_id,ZERO)
    return json_ready(result)


def period(business: Business, start: date | None, end: date | None) -> tuple[date,date]:
    end = end or datetime.now(ZoneInfo(business.timezone)).date()
    start = start or end - timedelta(days=29)
    if end < start or (end-start).days > 365:
        raise HTTPException(422, "Choose a reporting range of 1–366 days")
    return start,end


def dashboard(db: Session, business: Business, start: date, end: date) -> dict:
    orders = db.scalars(select(Order).where(Order.business_id == business.id, Order.ordered_on.between(start,end), Order.status == "paid")).all()
    items = db.scalars(select(OrderItem).where(OrderItem.business_id == business.id, OrderItem.order_id.in_([order.id for order in orders]))).all()
    expenses = db.scalars(select(Expense).where(Expense.business_id == business.id, Expense.incurred_on.between(start,end), Expense.status == "paid")).all()
    coverage = db.get(ExpenseCoverage, (business.id,start,end))
    complete = bool(coverage and coverage.complete)
    lines = {item.id:line_amounts(item.quantity,item.unit_price,item.unit_cost,item.discount_amount,item.tax_amount,business.currency) for item in items}
    metrics = financial_summary([(line[0],line[1]) for line in lines.values()], [item.amount for item in expenses], len(orders), business.currency, complete)
    order_dates = {order.id:order.ordered_on for order in orders}
    days = {start+timedelta(days=offset): {"revenue":money(ZERO,business.currency),"expenses":money(ZERO,business.currency)} for offset in range((end-start).days+1)}
    for item in items:
        days[order_dates[item.order_id]]["revenue"] += lines[item.id][0]
    for expense in expenses:
        days[expense.incurred_on]["expenses"] += expense.amount
    current_customers = {order.customer_id for order in orders}
    eligible = set(db.scalars(select(Order.customer_id).where(Order.business_id == business.id, Order.ordered_on < start, Order.status == "paid").distinct()))
    retained = len(current_customers & eligible)
    retention = (Decimal(retained)/len(eligible)*100).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP) if eligible else None
    inventory = None
    if "inventory" in business.modules:
        holdings = db.execute(select(InventoryBalance,Product).join(Product, (Product.business_id == InventoryBalance.business_id) & (Product.id == InventoryBalance.product_id)).where(InventoryBalance.business_id == business.id)).all()
        known = all(product.unit_cost is not None for balance,product in holdings if balance.quantity)
        inventory = {"valuation":"current unit cost, not FIFO", "as_of":"current", "value":sum((money(balance.quantity*product.unit_cost,business.currency) for balance,product in holdings if balance.quantity and product.unit_cost is not None), money(ZERO,business.currency)) if known else None,"stocked_products":sum(1 for balance,product in holdings if balance.quantity),"zero_stock_products":db.scalar(select(func.count()).select_from(Product).where(Product.business_id == business.id))-sum(1 for balance,product in holdings if balance.quantity)}
    counts, demo, freshness = {},0,[]
    for name,model in MODELS.items():
        counts[name] = db.scalar(select(func.count()).select_from(model).where(model.business_id == business.id))
        demo += db.scalar(select(func.count()).select_from(model).where(model.business_id == business.id,model.is_demo.is_(True)))
        updated = db.scalar(select(func.max(model.updated_at)).where(model.business_id == business.id))
        if updated:
            freshness.append(updated)
    return json_ready({"business_id":business.id,"currency":business.currency,"timezone":business.timezone,"start_date":start,"end_date":end,"calculation_type":"calculated_historical","metrics":metrics,"expenses_complete":complete,"missing_cost_lines":sum(1 for item in items if item.unit_cost is None),"active_customers":len(current_customers),"retention":{"eligible":len(eligible),"retained":retained,"percentage":retention},"inventory":inventory,"counts":counts,"demo_records":demo,"labels":LABELS[business.business_type],"trend":[{"date":day,**values} for day,values in days.items()],"data_updated_at":max(freshness) if freshness else None,"calculated_at":datetime.now(timezone.utc),"methodology":["Paid orders only; pending, cancelled and fully refunded orders are excluded. Refunds restate the original sale period; partial refunds are unsupported.","Revenue is quantity × sale price, rounded per line, minus line discounts; tax is excluded. Costs are explicit historical per-line costs, never inferred from current product cost.","Operating profit remains incomplete until all line costs are known and this exact period's expense coverage is confirmed.","All dates are business-local calendar dates. Inventory is current stock at current unit cost, independent of the sales reporting period.","Retention is repeat purchasing among customers with a known paid purchase before this period. Missing earlier history limits the eligible cohort.","Sales entry does not automatically change inventory; record stock movements separately to avoid double counting historical imports."]})
