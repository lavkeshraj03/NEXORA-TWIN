from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.data.calculations import CURRENCY_DIGITS, ZERO, line_amounts
from app.data.models import Customer, InventoryBalance, InventoryMovement
from app.data.service import json_ready
from app.ml.classification import classification_metrics, fit_classifier, predict_classifier
from app.ml.datasets import closed_today, fingerprint, paid_lines, series
from app.ml.forecasting import anomalies, decimal_value, predict, train_forecast
from app.ml.models import ModelRun


def forecast_rows(dataset, result, artifact, horizon):
    places = CURRENCY_DIGITS[dataset["currency"]] if dataset["task"] == "sales" else 3
    values = predict(artifact, horizon)
    step = 1 if dataset["aggregation"] == "daily" else 7
    origin = date.fromisoformat(dataset["points"][-1]["date"])
    band = Decimal(result["residual_band"]) if result["residual_band"] is not None else None
    output = []
    for index, value in enumerate(values, 1):
        point = decimal_value(value, places)
        width = band if index <= result["band_max_horizon"] else None
        output.append({"date": (origin + timedelta(days=step*index)).isoformat(), "prediction": str(point), "lower": str(max(ZERO, point-width)) if width is not None else None, "upper": str(point+width) if width is not None else None})
    return output


def train_series(db, business, user, data, product):
    dataset = series(db, business, data.start, data.end, data.aggregation, data.task, data.data_scope, product.id if product else None)
    places = CURRENCY_DIGITS[business.currency] if data.task == "sales" else 3
    artifact, result = train_forecast(dataset["points"], data.aggregation, data.horizon, places)
    result.pop("forecast_values")
    result["forecast"] = forecast_rows(dataset, result, artifact, data.horizon)
    result["anomalies"] = anomalies(dataset["points"])
    result["limitations"] = [
        "No-record buckets are treated as zero only because you confirmed this window is fully imported.",
        "Current-status paid sales only; refunds restate history. Taxes are excluded from sales.",
        "Statistical estimates, not accounting totals. No price, promotion, stock availability or external causal features are included.",
        "One chronological validation/test split does not establish future reliability; longer horizons can perform differently.",
        "Demo runs use only explicitly labelled demonstration sale lines." if data.data_scope == "demo" else "Real-data mode excludes labelled demonstration sale lines.",
    ]
    if result["baseline_only"]:
        result["limitations"].append("History is sufficient only for an evaluated seasonal-naive baseline; no regression was fitted.")
    config = json_ready(data.model_dump()) | {"product_sku": product.sku if product else None, "timezone": business.timezone, "currency": business.currency}
    run = ModelRun(business_id=business.id, created_by=user.id, task=data.task, product_id=product.id if product else None, data_scope=data.data_scope, algorithm=artifact["algorithm"], config=config, dataset=dataset, dataset_hash=fingerprint(dataset), artifact=artifact, result=json_ready(result))
    db.add(run)
    return run


def churn_snapshot(orders, cutoff, days, labelled):
    groups = defaultdict(list)
    for item in orders:
        if cutoff-timedelta(days=89) <= item["date"] <= cutoff:
            groups[item["customer_id"]].append(item)
    future = {item["customer_id"] for item in orders if cutoff < item["date"] <= cutoff+timedelta(days=days)} if labelled else set()
    rows = []
    for customer_id in sorted(groups):
        purchases = groups[customer_id]
        amount = sum((item["amount"] for item in purchases), ZERO)
        first, last = min(item["date"] for item in purchases), max(item["date"] for item in purchases)
        rows.append({"customer_id": customer_id, "features": [(cutoff-last).days, len(purchases), float(amount/len(purchases)), (cutoff-first).days], "label": int(customer_id not in future) if labelled else None})
    return rows


def churn_dataset(db, business, data):
    if data.end >= closed_today(business):
        raise HTTPException(422, "The observed outcome window must end before today in the business timezone")
    if (data.end-date.min).days < 2*data.inactivity_days+89:
        raise HTTPException(422, "The requested cutoff cannot contain the required historical window")
    start = data.end-timedelta(days=2*data.inactivity_days+89)
    lines = paid_lines(db, business.id, start, data.end, data.data_scope)
    orders = {}
    sources = []
    for order, item in lines:
        value = line_amounts(item.quantity, item.unit_price, None, item.discount_amount, item.tax_amount, business.currency)[0]
        group = orders.setdefault(order.id, {"order_id": str(order.id), "customer_id": str(order.customer_id), "date": order.ordered_on, "amount": ZERO})
        group["amount"] += value
        sources.append({"order_id": str(order.id), "item_id": str(item.id), "customer_id": str(order.customer_id), "date": order.ordered_on.isoformat(), "net_sales": str(value), "is_demo": bool(order.is_demo or item.is_demo)})
    if len({item["customer_id"] for item in orders.values()}) > 1000:
        raise HTTPException(422, "Churn training supports at most 1000 purchasing customers per run")
    training_cutoff, test_cutoff = data.end-timedelta(days=2*data.inactivity_days), data.end-timedelta(days=data.inactivity_days)
    train = churn_snapshot(orders.values(), training_cutoff, data.inactivity_days, True)
    test = churn_snapshot(orders.values(), test_cutoff, data.inactivity_days, True)
    current = churn_snapshot(orders.values(), data.end, data.inactivity_days, False)
    return {"train": train, "test": test, "current": current, "sources": sources, "start": start.isoformat(), "end": data.end.isoformat(), "training_cutoff": training_cutoff.isoformat(), "test_cutoff": test_cutoff.isoformat(), "inactivity_days": data.inactivity_days, "data_scope": data.data_scope, "currency": business.currency, "timezone": business.timezone}


def train_churn(db, business, user, data):
    dataset = churn_dataset(db, business, data)
    train, test, current = dataset["train"], dataset["test"], dataset["current"]
    artifact = fit_classifier([row["features"] for row in train], [row["label"] for row in train])
    probabilities = predict_classifier(artifact, [row["features"] for row in test])
    evaluation = classification_metrics([row["label"] for row in test], probabilities)
    baseline = classification_metrics([row["label"] for row in test], [artifact["training_prevalence"]]*len(test))
    # After frozen evaluation, refit with both fully observed, non-overlapping outcome windows.
    observed = train+test
    final_artifact = fit_classifier([row["features"] for row in observed], [row["label"] for row in observed])
    current_scores = predict_classifier(final_artifact, [row["features"] for row in current])
    names = {str(customer.id): customer.external_id for customer in db.scalars(select(Customer).where(Customer.business_id == business.id))}
    estimates = [{"customer_id": row["customer_id"], "external_id": names[row["customer_id"]], "estimated_inactivity_probability": round(probability, 6), "features": dict(zip(final_artifact["features"], row["features"]))} for row, probability in zip(current, current_scores, strict=True)]
    estimates.sort(key=lambda row: (-row["estimated_inactivity_probability"], row["customer_id"]))
    result = {"evaluation": evaluation, "baseline": baseline, "training_cutoff": dataset["training_cutoff"], "test_cutoff": dataset["test_cutoff"], "outcomes_observed_through": data.end.isoformat(), "training_customers": len(train), "test_customers": len(test), "predictions": estimates, "definition": f"No paid purchase during the {data.inactivity_days} days after a cutoff, among customers purchasing in the preceding 90 days.", "limitations": ["Inactivity is a proxy, not confirmed customer loss. Choose a window appropriate for your business cadence.", "Training and later evaluation use time-ordered cutoffs with disjoint outcome windows; customers may recur across cutoffs. Customer IDs are not model features.", "Feature tenure is measured only within the 90-day lookback; complaints/support data are not available.", "Estimated probabilities are not calibrated. A fixed 0.5 classification threshold is evaluated; no threshold tuning or pooled tenant model is used.", "This fixed model is not selected using test scores; compare it with the prevalence baseline before activation."]}
    run = ModelRun(business_id=business.id, created_by=user.id, task="churn", product_id=None, data_scope=data.data_scope, algorithm=final_artifact["algorithm"], config=json_ready(data.model_dump()) | {"currency": business.currency, "timezone": business.timezone}, dataset=json_ready(dataset), dataset_hash=fingerprint(dataset), artifact=final_artifact, result=result)
    db.add(run)
    return run


def summary(run, detail=False):
    result = {"id": str(run.id), "task": run.task, "data_scope": run.data_scope, "algorithm": run.algorithm, "implementation_version": run.implementation_version, "dataset_hash": run.dataset_hash, "artifact_reference": f"model_runs/{run.id}/artifact", "config": run.config, "active": run.active, "created_at": run.created_at.isoformat()}
    if detail:
        result |= {"result": run.result, "history": run.dataset.get("points", []), "source_count": len(run.dataset["sources"]), "artifact": run.artifact}
    return result


def stock_risk(db, business, product, scope, lead_days, incoming, safety):
    end = closed_today(business)-timedelta(days=1)
    dataset = series(db, business, end-timedelta(days=27), end, "daily", "demand", scope, product.id)
    rate = sum((Decimal(point["value"]) for point in dataset["points"]), ZERO)/28
    balance = db.get(InventoryBalance, (business.id, product.id))
    stock = balance.quantity if balance else ZERO
    required = rate*lead_days+safety
    gap = max(ZERO, required-stock-incoming)
    demo_movements = db.scalar(select(InventoryMovement.id).where(InventoryMovement.business_id == business.id, InventoryMovement.product_id == product.id, InventoryMovement.is_demo.is_(True)).limit(1)) is not None
    return json_ready({"calculation_type": "deterministic_inventory_risk", "product_sku": product.sku, "data_scope": scope, "lookback_start": dataset["start"], "lookback_end": dataset["end"], "daily_rate": rate.quantize(Decimal("0.001")), "current_stock": stock, "lead_days": lead_days, "incoming_assumption": incoming, "safety_assumption": safety, "required_quantity": required.quantize(Decimal("0.001")), "shortfall": gap.quantize(Decimal("0.001")), "days_cover": (stock/rate).quantize(Decimal("0.01")) if rate else None, "risk": "shortfall" if gap else "no_calculated_shortfall", "demo_stock_present": demo_movements, "source_order_count": dataset["paid_orders"], "limitations": ["Calculated from trailing recorded demand, not an ML probability or stockout-date guarantee.", "Stock is the current ledger balance across all demo labels; demand uses the selected scope. Keep demo and real data in separate businesses.", "Incoming units and lead time are assumptions; no purchase-order reconciliation exists.", "No-record days are zero; missing imports, stock constraints and changing demand can understate risk."]})
