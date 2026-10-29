import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.data.calculations import ZERO, line_amounts, money
from app.data.models import Order, OrderItem, Product
from app.data.service import json_ready


def closed_today(business):
    return datetime.now(ZoneInfo(business.timezone)).date()


def scope_predicate(scope):
    synthetic = or_(Order.is_demo.is_(True), OrderItem.is_demo.is_(True))
    return synthetic if scope == "demo" else ~synthetic


def paid_lines(db, business_id, start, end, scope, product_id=None):
    query = select(Order, OrderItem).join(OrderItem, (OrderItem.business_id == Order.business_id) & (OrderItem.order_id == Order.id)).where(Order.business_id == business_id, OrderItem.business_id == business_id, Order.status == "paid", Order.ordered_on.between(start, end), scope_predicate(scope))
    if product_id:
        query = query.where(OrderItem.product_id == product_id)
    rows = db.execute(query.order_by(Order.ordered_on, Order.id, OrderItem.id).limit(30001)).all()
    if len(rows) > 30000:
        raise HTTPException(422, "Split the training window: this release supports at most 30000 sale lines")
    return rows


def product_for(db, business_id, sku):
    product = db.scalar(select(Product).where(Product.business_id == business_id, Product.sku == sku))
    if product is None:
        raise HTTPException(404, "Product not found in this business")
    return product


def series(db, business, start, end, aggregation, task, scope, product_id=None):
    if end < start or (end - start).days > 729:
        raise HTTPException(422, "Choose 1–730 days of history")
    if end >= closed_today(business):
        raise HTTPException(422, "Training must end before the current business-local day")
    if aggregation == "weekly" and (start.weekday() != 0 or end.weekday() != 6):
        raise HTTPException(422, "Weekly history must start Monday and end Sunday; partial weeks are excluded")
    rows = paid_lines(db, business.id, start, end, scope, product_id)
    step = 1 if aggregation == "daily" else 7
    totals = {start + timedelta(days=offset): ZERO for offset in range(0, (end-start).days+1, step)}
    sources = []
    for order, item in rows:
        bucket = order.ordered_on if aggregation == "daily" else order.ordered_on - timedelta(days=order.ordered_on.weekday())
        value = line_amounts(item.quantity, item.unit_price, item.unit_cost, item.discount_amount, item.tax_amount, business.currency)[0] if task == "sales" else item.quantity
        totals[bucket] += value
        sources.append({"order_id": str(order.id), "item_id": str(item.id), "customer_id": str(order.customer_id), "product_id": str(item.product_id), "date": order.ordered_on.isoformat(), "quantity": str(item.quantity), "net_sales": str(line_amounts(item.quantity, item.unit_price, None, item.discount_amount, item.tax_amount, business.currency)[0]), "is_demo": bool(order.is_demo or item.is_demo)})
    points = [{"date": day.isoformat(), "value": str(money(value, business.currency) if task == "sales" else value.quantize(Decimal("0.001")))} for day, value in totals.items()]
    dataset = {"points": points, "sources": sources, "paid_orders": len({source["order_id"] for source in sources}), "sale_lines": len(sources), "zero_buckets": sum(value == 0 for value in totals.values()), "currency": business.currency, "timezone": business.timezone, "start": start.isoformat(), "end": end.isoformat(), "aggregation": aggregation, "task": task, "data_scope": scope, "product_id": str(product_id) if product_id else None}
    return dataset


def fingerprint(dataset):
    return hashlib.sha256(json.dumps(json_ready(dataset), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
