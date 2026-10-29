"""Explicit, repeat-safe demo package for an existing owner's empty retail workspace.

Generate files first with --generate-only. Run the load inside the backend container
so indexing, retrieval identities and provider URLs match the running application.
No login/session/password is fabricated, and existing operational data is never reset.
"""
import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import UUID

VERSION = "nexa-demo-v1"
PRODUCTS = [
    ("NX-NBK-01", "Demo notebook", "120.00", "65.00", "NX-SUP-01", 90),
    ("NX-PEN-01", "Demo desk pen", "40.00", "18.00", "NX-SUP-01", 8),
    ("NX-BAG-01", "Demo laptop bag", "850.00", "480.00", "NX-SUP-02", 35),
    ("NX-BTL-01", "Demo water bottle", "300.00", "160.00", "NX-SUP-02", 55),
    ("NX-DSK-01", "Demo desk organizer", "450.00", "240.00", "NX-SUP-03", 40),
    ("NX-CBL-01", "Demo USB-C cable", "250.00", "120.00", "NX-SUP-03", 25),
]


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate(folder, end):
    folder.mkdir(parents=True, exist_ok=True)
    start = end-timedelta(days=179)
    customers = [{"external_id": f"NX-C{index:03d}", "name": f"Demo customer {index:03d}", "email": f"customer{index:03d}@nexa.example", "is_demo": "true"} for index in range(1, 85)]
    suppliers = [{"external_id": f"NX-SUP-{index:02d}", "name": f"Demo supplier {index}", "email": f"supplier{index}@nexa.example", "is_demo": "true"} for index in range(1, 4)]
    products = [{"sku": sku, "name": name, "unit_price": price, "unit_cost": cost, "supplier_external_id": supplier, "initial_stock": "0", "is_demo": "true"} for sku, name, price, cost, supplier, remaining in PRODUCTS]
    orders = []

    def line(external, day, customer, product, quantity, status="paid", discount=False):
        sku, _, price, cost, _, _ = product
        price = Decimal(price)
        reduction = (price*quantity*Decimal("0.05")).quantize(Decimal("0.01")) if discount else Decimal("0.00")
        orders.append({"external_id": external, "ordered_on": day.isoformat(), "customer_external_id": customer, "product_sku": sku, "quantity": str(quantity), "unit_price": str(price), "unit_cost": cost, "discount_amount": str(reduction), "tax_amount": "0.00", "currency": "INR", "status": status, "is_demo": "true"})

    for index in range(180):
        day = start+timedelta(days=index)
        customer = f"NX-C{1+index%4:03d}"
        for offset in range(2):
            product = PRODUCTS[(index+offset*3)%6]
            quantity = 2+index%5+index//60
            if index == 165: quantity *= 8  # Explicit synthetic spike for source inspection.
            line(f"NX-ORD-{index+1:04d}", day, customer, product, quantity, discount=index%9 == 0)
    # Eighty additional customers supply fully observed inactivity outcome windows.
    for index in range(80):
        days = [end-timedelta(days=61+index%10)]
        if index < 40: days.append(end-timedelta(days=53))
        if index%2 == 0: days.append(end-timedelta(days=23))
        for number, day in enumerate(days):
            line(f"NX-COHORT-{index:03d}-{number}", day, f"NX-C{index+5:03d}", PRODUCTS[index%6], 1)
    line("NX-PENDING-001", end-timedelta(days=1), "NX-C001", PRODUCTS[0], 2, "pending")
    line("NX-REFUNDED-001", end-timedelta(days=2), "NX-C002", PRODUCTS[0], 2, "refunded")
    orders.sort(key=lambda row: (row["ordered_on"], row["external_id"], row["product_sku"]))
    sold = defaultdict(int)
    for row in orders:
        if row["status"] == "paid": sold[row["product_sku"]] += int(row["quantity"])
    inventory = []
    for sku, name, price, cost, supplier, remaining in PRODUCTS:
        restock = min(40, sold[sku]//4)
        for external, day, quantity, reason in [
            (f"NX-OPEN-{sku}", start, sold[sku]+remaining+2-restock, "restock"),
            (f"NX-RESTOCK-{sku}", start+timedelta(days=60), restock, "restock"),
            (f"NX-WASTE-{sku}", end-timedelta(days=1), -2, "waste"),
        ]:
            inventory.append({"external_id": external, "product_sku": sku, "occurred_on": day.isoformat(), "quantity_delta": str(quantity), "reason": reason, "is_demo": "true"})
    for index, row in enumerate(orders):
        if row["status"] == "paid":
            inventory.append({"external_id": f"NX-MOVE-{index+1:04d}", "product_sku": row["product_sku"], "occurred_on": row["ordered_on"], "quantity_delta": str(-int(row["quantity"])), "reason": "sale", "is_demo": "true"})
    inventory.sort(key=lambda row: (row["occurred_on"], 0 if row["reason"] == "restock" else 1, row["external_id"]))
    expenses = []

    def expense(day, category, amount):
        expenses.append({"external_id": f"NX-EXP-{len(expenses)+1:04d}", "incurred_on": day.isoformat(), "category": category, "amount": amount, "currency": "INR", "status": "paid", "is_demo": "true"})

    for index in range(0, 180, 7):
        day = start+timedelta(days=index)
        expense(day, "marketing", "900.00")
        expense(day, "transport", "300.00")
    for index in range(180):
        day = start+timedelta(days=index)
        if day.day == 1:
            expense(day, "rent", "8000.00")
            expense(day, "payroll", "12000.00")
        if day.day == 15: expense(day, "utilities", "1500.00")
    rows = {"customers": customers, "suppliers": suppliers, "products": products, "orders": orders, "inventory": inventory, "expenses": expenses}
    balances = defaultdict(int)
    for movement in inventory:
        balances[movement["product_sku"]] += int(movement["quantity_delta"])
        if balances[movement["product_sku"]] < 0: raise ValueError("Generated inventory would go negative")
    if dict(balances) != {product[0]: product[5] for product in PRODUCTS}: raise ValueError("Generated inventory does not reconcile")
    for resource, values in rows.items(): write_csv(folder/f"{resource}.csv", values)
    documents = folder/"documents"
    documents.mkdir(exist_ok=True)
    documents.joinpath("demo-returns-policy.txt").write_text("# DEMO Nexa Returns Policy\n\nSynthetic demonstration only; this is not Nexa's actual policy.\n\nReturns are accepted within thirty days of purchase. Customers must provide the original receipt.\n\nRefunds are issued to the original payment method after the returned goods are inspected.\n\nCustom-made items cannot be returned unless they are defective.\n")
    documents.joinpath("demo-business-guide.txt").write_text("# DEMO Nexa Business Guide\n\nThis is a synthetic retail workspace for learning NEXORA TWIN. It sells notebooks, pens, laptop bags, bottles, desk organizers and USB-C cables.\n\nSupport hours are 09:00 to 17:00, Monday to Friday. The demonstration support contact is support@nexa.example.\n\nEvery imported sale, expense, customer, supplier, product and stock movement is labelled is_demo=true. Numerical dashboards and forecasts use stored records; document Q&A explains document evidence only.\n")
    manifest = {"version": VERSION, "synthetic": True, "currency": "INR", "history_start": start.isoformat(), "history_end": end.isoformat(), "report_start": (end-timedelta(days=29)).isoformat(), "report_end": end.isoformat(), "resource_rows": {name: len(values) for name, values in rows.items()}, "orders": len({row["external_id"] for row in orders}), "paid_orders": len({row["external_id"] for row in orders if row["status"] == "paid"}), "expected_stock": {product[0]: str(product[5]) for product in PRODUCTS}, "demand_sku": "NX-PEN-01"}
    selected = [row for row in orders if row["status"] == "paid" and manifest["report_start"] <= row["ordered_on"] <= manifest["report_end"]]
    revenue = sum(((Decimal(row["quantity"])*Decimal(row["unit_price"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)-Decimal(row["discount_amount"]) for row in selected), Decimal(0))
    cogs = sum(((Decimal(row["quantity"])*Decimal(row["unit_cost"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for row in selected), Decimal(0))
    costs = sum((Decimal(row["amount"]) for row in expenses if manifest["report_start"] <= row["incurred_on"] <= manifest["report_end"]), Decimal(0))
    manifest["expected_metrics"] = {"revenue": str(revenue), "cogs": str(cogs), "gross_profit": str(revenue-cogs), "recorded_expenses": str(costs), "operating_profit": str(revenue-cogs-costs), "paid_orders": len({row["external_id"] for row in selected})}
    folder.joinpath("manifest.json").write_text(json.dumps(manifest, indent=2))
    folder.joinpath("README.md").write_text(f"# Explicit Nexa demonstration data\n\nSynthetic only. Generated for {start} through {end}; reporting example {manifest['report_start']} through {end}. All operational rows carry is_demo=true. No real customer/supplier contact data is included.\n\nThese files were explicitly requested and loaded into the empty Nexa workspace. To practise a fresh import, create a separate retail demo business (INR) and confirm customers, suppliers, products, inventory, orders, then expenses in that order. Inventory entries already reconcile the paid sales; do not add a second stock deduction for the same sale.\n\nThere are {manifest['orders']} orders and {len(orders)} order-item rows. Pending and fully refunded examples are excluded from dashboard revenue. Stock for NX-PEN-01 intentionally finishes at eight units to demonstrate calculated shortfall. The synthetic sales spike is a diagnostic example, not a real incident.\n\nFor Forecasts & risk select Labelled demonstration records only. Raw document samples live in documents/. See docs/nexa-demo-guide.md for the walkthrough.\n")
    return manifest


def load(folder, business_id, owner_id):
    import time
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
    from app.api.businesses import access
    from app.data.imports import parse_file
    from app.data.models import ExpenseCoverage, ImportBatch, InventoryBalance, Product
    from app.data.service import MODELS, dashboard, json_ready, persist_rows, validate_rows
    from app.db.session import get_engine
    from app.documents.models import Document, DocumentVersion
    from app.documents.pipeline import enqueue
    from app.documents.router import EvaluationCase, EvaluationInput, evaluate, reindex
    from app.documents.rag import ask
    from app.ml.models import ModelRun
    from app.ml.router import ChurnInput, ForecastInput, train_forecast, train_inactivity
    from app.models import AuditLog, Business, User

    manifest = json.loads((folder/"manifest.json").read_text())
    start, end = date.fromisoformat(manifest["history_start"]), date.fromisoformat(manifest["history_end"])
    report_start = date.fromisoformat(manifest["report_start"])
    marker = VERSION+":"+end.isoformat()
    with Session(get_engine(), expire_on_commit=False) as db:
        user = db.get(User, owner_id)
        if user is None: raise ValueError("Owner account not found")
        business, membership = access(db, user, business_id, "data:write", lock=True)
        if membership.role != "owner" or business.business_type != "retail" or business.currency != "INR" or "inventory" not in business.modules:
            raise ValueError("This demo requires the specified account to own an INR retail business with inventory")
        existing_marker = db.scalar(select(AuditLog).where(AuditLog.business_id == business_id, AuditLog.event == "demo.nexa.loaded", AuditLog.target_id == marker))
        if existing_marker is None:
            if any(db.scalar(select(func.count()).select_from(model).where(model.business_id == business_id)) for model in list(MODELS.values())+[Document, ModelRun]):
                raise ValueError("Refusing to mix demo data into a nonempty business; use a new demo workspace")
            # One transaction for all six linked resources: no partial operational load.
            for resource in ["customers", "suppliers", "products", "inventory", "orders", "expenses"]:
                raw = (folder/f"{resource}.csv").read_bytes()
                columns, rows = parse_file(resource+".csv", raw)
                parsed, errors, context = validate_rows(db, business, resource, rows)
                if errors: raise ValueError(f"{resource}: {errors[:3]}")
                count = persist_rows(db, business, resource, parsed, context)
                db.flush()
                db.add(ImportBatch(business_id=business_id, resource=resource, currency="INR", filename=f"DEMO-Nexa-{resource}.csv", content_hash=hashlib.sha256(raw).hexdigest(), status="committed", columns=columns, raw_rows=rows, mapping={column: column for column in columns}, errors=[], valid_count=len(rows), imported_count=count, is_demo=True))
            db.add(ExpenseCoverage(business_id=business_id, start_date=report_start, end_date=end, complete=True, confirmed_by=user.id))
            db.flush()
            verified = dashboard(db, business, report_start, end)["metrics"]
            for field, expected in manifest["expected_metrics"].items():
                if Decimal(str(verified[field])) != Decimal(str(expected)): raise ValueError(f"Financial reconciliation failed: {field}")
            holdings = db.execute(select(Product.sku, InventoryBalance.quantity).join(InventoryBalance, (InventoryBalance.business_id == Product.business_id) & (InventoryBalance.product_id == Product.id)).where(Product.business_id == business_id)).all()
            if {sku: int(quantity) for sku, quantity in holdings} != {sku: int(value) for sku, value in manifest["expected_stock"].items()}: raise ValueError("Loaded stock does not reconcile")
            db.add(AuditLog(business_id=business_id, user_id=user.id, event="demo.nexa.loaded", target_id=marker))
            db.commit()
            print("Loaded all six demo resources atomically.", flush=True)
        else:
            print("Existing demo marker found; operational records left unchanged.", flush=True)
        report = dashboard(db, business, report_start, end)
        print("DASHBOARD:", json.dumps(json_ready(report["metrics"])), flush=True)
        for task in ["sales", "demand", "churn"]:
            existing = db.scalar(select(ModelRun).where(ModelRun.business_id == business_id, ModelRun.task == task, ModelRun.data_scope == "demo"))
            if existing is None:
                if task == "churn":
                    run = train_inactivity(business_id, ChurnInput(end=end, inactivity_days=30, data_scope="demo", coverage_confirmed=True), user=user, db=db)
                else:
                    run = train_forecast(business_id, ForecastInput(task=task, start=start, end=end, horizon=7, aggregation="daily", data_scope="demo", coverage_confirmed=True, product_sku=manifest["demand_sku"] if task == "demand" else None), user=user, db=db)
                print("Saved evaluated demo model:", task, run["id"], flush=True)
        # Stage each labelled source only once; worker uses the running provider configuration.
        versions = []
        for source in sorted((folder/"documents").iterdir()):
            if source.suffix.lower() not in {".txt", ".pdf", ".docx", ".csv", ".xlsx"}: continue
            title = "[DEMO] Nexa "+source.stem.removeprefix("demo-").replace("-", " ").title()
            document = db.scalar(select(Document).where(Document.business_id == business_id, Document.title == title))
            if document is None:
                access(db, user, business_id, "documents:write", lock=True)
                document = Document(business_id=business_id, title=title, visibility="team")
                db.add(document); db.flush()
                raw = source.read_bytes()
                version = DocumentVersion(business_id=business_id, document_id=document.id, version=1, filename=source.name, raw=raw, content_hash=hashlib.sha256(raw).hexdigest(), status="queued")
                db.add(version); db.flush()
                db.add(AuditLog(business_id=business_id, user_id=user.id, event="demo.document_uploaded", target_id=str(document.id)))
                db.commit(); enqueue(version.id)
            else:
                version = db.scalar(select(DocumentVersion).where(DocumentVersion.business_id == business_id, DocumentVersion.document_id == document.id).order_by(DocumentVersion.version.desc()).limit(1))
                if version.status in {"failed", "awaiting_configuration"}:
                    reindex(business_id, document.id, version.id, user=user, db=db)
                    db.refresh(version)
            versions.append((source.name, document.id, version.id))
        db.commit()
        for filename, document_id, version_id in versions:
            deadline = time.monotonic()+200
            while time.monotonic() < deadline:
                db.expire_all()
                version = db.get(DocumentVersion, version_id)
                if version.status == "ready": break
                if version.status in {"failed", "awaiting_configuration"}: raise ValueError(f"{filename}: {version.error}")
                db.commit(); time.sleep(0.5)
            if version.status != "ready": raise ValueError(f"{filename}: indexing timed out")
            print("Indexed demo document:", filename, flush=True)
        db.commit()
        policy = next(document_id for filename, document_id, version_id in versions if filename == "demo-returns-policy.txt")
        _, actor = access(db, user, business_id, "documents:read", lock=True)
        answer = ask(db, business_id, actor.role, user.id, "How long do customers have to return an item?", [policy])
        if answer["insufficient"] or not answer["citations"]: raise ValueError("Demo policy did not produce a grounded answer")
        db.add(AuditLog(business_id=business_id, user_id=user.id, event="demo.rag_verified")); db.commit()
        print("LIVE POLICY ANSWER:", answer["answer"], flush=True)
        evaluation = evaluate(business_id, EvaluationInput(cases=[
            EvaluationCase(question="How long do customers have to return an item?", expected_document_ids=[policy], expected_answer="thirty days"),
            EvaluationCase(question="What proof is required for a return?", expected_document_ids=[policy], expected_answer="original receipt"),
        ]), user=user, db=db)
        print("DEMO EVALUATION:", json.dumps(evaluation), flush=True)
        final = {name: db.scalar(select(func.count()).select_from(model).where(model.business_id == business_id)) for name, model in MODELS.items()}
        final |= {"documents": len(versions), "model_runs": db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.business_id == business_id))}
        print("COMPLETE:", json.dumps({"business": business.name, "counts": final, "metrics": json_ready(report["metrics"]), "report_start": report_start.isoformat(), "report_end": end.isoformat()}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--business-id", type=UUID)
    parser.add_argument("--owner-id", type=UUID)
    args = parser.parse_args()
    if args.generate_only:
        if args.end is None: parser.error("--end is required for generation")
        print(json.dumps(generate(args.data_dir, args.end), indent=2))
    else:
        if args.business_id is None or args.owner_id is None: parser.error("Loading requires --business-id and --owner-id")
        load(args.data_dir, args.business_id, args.owner_id)


if __name__ == "__main__":
    main()
