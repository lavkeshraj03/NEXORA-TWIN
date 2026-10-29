import os
from decimal import Decimal
from uuid import UUID
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_identity_integration import accounts, create, DATA
from app.data.models import OrderItem

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv("RUN_INTEGRATION")!="1",reason="Requires migrated PostgreSQL/Redis")]
DATES="?start=2026-10-01&end=2026-10-31"


def add(client,headers,path,resource,rows):
    response=client.post(path+"/"+resource,headers=headers,json={"rows":rows})
    assert response.status_code==201,response.text
    return response.json()


def seed(client,headers,path):
    add(client,headers,path,"customers",[{"external_id":"C1","name":"Demo customer","is_demo":True}])
    add(client,headers,path,"suppliers",[{"external_id":"S1","name":"Demo supplier","is_demo":True}])
    add(client,headers,path,"products",[{"sku":"P1","name":"Demo product","unit_price":"10","unit_cost":"4","supplier_external_id":"S1","initial_stock":"20","is_demo":True}])


def order(external="O1",**overrides):
    return {"external_id":external,"ordered_on":"2026-10-10","customer_external_id":"C1","product_sku":"P1","quantity":"3","unit_price":"10","unit_cost":"4","discount_amount":"2","tax_amount":"3","is_demo":True}|overrides


def test_real_financial_dashboard_and_inventory_reconciliation(accounts):
    owner,_,headers,_,_,_,_=accounts
    business=create(owner,headers)
    path=f"/api/v1/businesses/{business['id']}"
    seed(owner,headers,path)
    add(owner,headers,path,"orders",[order(),order("O2",status="pending"),order("O3",status="refunded"),order("O4",status="cancelled")])
    add(owner,headers,path,"expenses",[{"external_id":"E1","incurred_on":"2026-10-10","category":"rent","amount":"5.50","is_demo":True}])
    result=owner.get(path+"/dashboard"+DATES)
    assert result.status_code==200,result.text
    report=result.json()
    assert report["metrics"]["revenue"]=="28.00"
    assert report["metrics"]["cogs"]=="12.00"
    assert report["metrics"]["gross_profit"]=="16.00"
    assert report["metrics"]["gross_margin_pct"]=="57.14"
    assert report["metrics"]["average_order_value"]=="28.00"
    assert report["metrics"]["operating_profit"] is None
    assert report["metrics"]["paid_orders"]==1
    assert report["demo_records"]>0 and report["inventory"]["value"]=="80.00"
    assert owner.put(path+"/expense-coverage",headers=headers,json={"start_date":"2026-10-01","end_date":"2026-10-31","complete":True}).status_code==200
    assert owner.get(path+"/dashboard"+DATES).json()["metrics"]["operating_profit"]=="10.50"
    add(owner,headers,path,"inventory",[{"external_id":"M1","product_sku":"P1","occurred_on":"2026-10-10","quantity_delta":"-3","reason":"sale"}])
    assert owner.get(path+"/dashboard"+DATES).json()["inventory"]["value"]=="68.00"
    assert sum(Decimal(item["quantity_delta"]) for item in owner.get(path+"/inventory").json()["items"])==Decimal("17")
    assert owner.put(path,headers=headers,json=DATA|{"currency":"USD"}).status_code==409


def test_unknown_cost_retention_refund_and_stock_guard(accounts):
    owner,_,headers,_,_,_,_=accounts
    business=create(owner,headers)
    path=f"/api/v1/businesses/{business['id']}"
    seed(owner,headers,path)
    add(owner,headers,path,"orders",[order("OLD",ordered_on="2026-09-10"),order(unit_cost=None)])
    report=owner.get(path+"/dashboard"+DATES).json()
    assert report["metrics"]["gross_profit"] is None and report["missing_cost_lines"]==1
    assert report["retention"]=={"eligible":1,"retained":1,"percentage":"100.00"}
    record=next(item for item in owner.get(path+"/orders").json()["items"] if item["external_id"]=="O1")
    assert owner.patch(path+"/orders/"+record["id"],headers=headers,json={"status":"refunded","reason":"Full return recorded"}).status_code==200
    assert owner.get(path+"/dashboard"+DATES).json()["metrics"]["revenue"]=="0.00"
    assert owner.post(path+"/inventory",headers=headers,json={"rows":[{"external_id":"BAD","product_sku":"P1","occurred_on":"2026-10-10","quantity_delta":"-99","reason":"sale"}]}).status_code==422
    assert owner.get(path+"/products").json()["items"][0]["stock_quantity"]=="20.000"


def test_import_mapping_confirmation_idempotency_and_isolation(accounts):
    owner,other,headers,other_headers,_,_,_=accounts
    one=create(owner,headers)
    two=create(owner,headers,name="Other owned business")
    path=f"/api/v1/businesses/{one['id']}"
    raw=b"Client Code,Client Name,Synthetic\nA1,First,true\nA2,Second,true\n"
    response=owner.post(path+"/imports",params={"resource":"customers","filename":"customers.csv"},headers=headers,content=raw)
    assert response.status_code==200,response.text
    batch=response.json()
    assert batch["status"]=="preview" and owner.get(path+"/customers").json()["total"]==0
    validated=owner.post(path+f"/imports/{batch['id']}/validate",headers=headers,json={"mapping":{"external_id":"Client Code","name":"Client Name","is_demo":"Synthetic"}})
    assert validated.status_code==200,validated.text
    batch=validated.json()
    assert batch["valid_count"]==2 and batch["error_count"]==0
    assert owner.post(path+f"/imports/{batch['id']}/commit",headers=headers,json={"confirmed":True,"preview_updated_at":"2000-01-01T00:00:00Z"}).status_code==409
    confirm={"confirmed":True,"preview_updated_at":batch["updated_at"]}
    committed=owner.post(path+f"/imports/{batch['id']}/commit",headers=headers,json=confirm)
    assert committed.status_code==200,committed.text
    assert committed.json()["imported_count"]==2
    assert owner.post(path+f"/imports/{batch['id']}/commit",headers=headers,json=confirm).status_code==200
    assert owner.post(path+"/imports",params={"resource":"customers","filename":"again.csv"},headers=headers,content=raw).json()["id"]==batch["id"]
    assert owner.get(path+"/customers").json()["total"]==2
    assert owner.get(path+"/customers?search=Second&sort=reference&limit=1").json()["items"][0]["external_id"]=="A2"
    assert other.get(path+f"/imports/{batch['id']}").status_code==404
    assert owner.get(f"/api/v1/businesses/{two['id']}/imports/{batch['id']}").status_code==404
    assert other.post(path+f"/imports/{batch['id']}/commit",headers=other_headers,json=confirm).status_code==404


def test_invalid_rows_are_atomic_and_errors_downloadable(accounts):
    owner,_,headers,_,_,_,_=accounts
    business=create(owner,headers)
    path=f"/api/v1/businesses/{business['id']}"
    raw=b"external_id,name,email\nC1,Valid,valid@example.com\nC2,Invalid,not-an-email\n"
    batch=owner.post(path+"/imports",headers=headers,params={"resource":"customers","filename":"bad.csv"},content=raw).json()
    assert batch["error_count"]==1 and batch["valid_count"]==1
    assert owner.post(path+f"/imports/{batch['id']}/commit",headers=headers,json={"confirmed":True,"preview_updated_at":batch["updated_at"]}).status_code==409
    assert owner.get(path+"/customers").json()["total"]==0
    errors=owner.get(path+f"/imports/{batch['id']}/errors")
    assert errors.status_code==200 and "text/csv" in errors.headers["content-type"] and "email" in errors.text


def test_database_foreign_keys_roles_and_exports_are_tenant_scoped(accounts):
    owner,other,headers,other_headers,_,two,connection=accounts
    one=create(owner,headers)
    another=create(owner,headers,name="Separate")
    path=f"/api/v1/businesses/{one['id']}"
    second=f"/api/v1/businesses/{another['id']}"
    seed(owner,headers,path)
    seed(owner,headers,second)
    add(owner,headers,path,"orders",[order()])
    record=owner.get(path+"/orders").json()["items"][0]
    foreign_product=owner.get(second+"/products").json()["items"][0]
    with Session(connection,join_transaction_mode="create_savepoint") as db:
        db.add(OrderItem(business_id=UUID(one["id"]),order_id=UUID(record["id"]),product_id=UUID(foreign_product["id"]),quantity=Decimal(1),unit_price=Decimal(1),unit_cost=None,discount_amount=Decimal(0),tax_amount=Decimal(0)))
        with pytest.raises(IntegrityError) as error:
            db.flush()
        assert error.value.orig.diag.constraint_name=="fk_item_tenant_product"
        db.rollback()
    assert owner.get(path+"/products/"+foreign_product["id"]).status_code==404
    assert other.get(path+"/dashboard"+DATES).status_code==404 and other.get(path+"/customers/export").status_code==404
    assert owner.post(path+"/members",headers=headers,json={"email":two["user"]["email"],"role":"viewer"}).status_code==201
    assert other.get(path+"/dashboard"+DATES).status_code==200
    assert other.post(path+"/customers",headers=other_headers,json={"rows":[{"external_id":"C2","name":"Forbidden"}]}).status_code==403
    exported=owner.get(path+"/customers/export")
    assert exported.status_code==200 and "attachment" in exported.headers["content-disposition"]
    assert owner.get(path+"/transactions").json()["items"][0]["source"]=="orders"


def test_profile_specific_inventory_and_reporting_ranges(accounts):
    owner,_,headers,_,_,_,_=accounts
    business=create(owner,headers,business_type="services")
    path=f"/api/v1/businesses/{business['id']}"
    assert "inventory" not in owner.get(path+"/data-schema").json()["resources"]
    report=owner.get(path+"/dashboard"+DATES).json()
    assert report["inventory"] is None and report["labels"]["customers"]=="Clients"
    assert owner.get(path+"/dashboard?start=2026-11-01&end=2026-10-01").status_code==422


def test_expense_changes_retract_completeness(accounts):
    owner,_,headers,_,_,_,_=accounts
    business=create(owner,headers)
    path=f"/api/v1/businesses/{business['id']}"
    coverage={"start_date":"2026-10-01","end_date":"2026-10-31","complete":True}
    assert owner.put(path+"/expense-coverage",headers=headers,json=coverage).status_code==200
    assert owner.get(path+"/dashboard"+DATES).json()["metrics"]["operating_profit"]=="0.00"
    add(owner,headers,path,"expenses",[{"external_id":"E1","incurred_on":"2026-10-10","category":"rent","amount":"5.50"}])
    assert owner.get(path+"/dashboard"+DATES).json()["metrics"]["operating_profit"] is None
    assert owner.put(path+"/expense-coverage",headers=headers,json=coverage).status_code==200
    assert owner.get(path+"/dashboard"+DATES).json()["metrics"]["operating_profit"]=="-5.50"
    record=owner.get(path+"/expenses").json()["items"][0]
    assert owner.patch(path+"/expenses/"+record["id"],headers=headers,json={"status":"voided","reason":"Duplicate rent entry"}).status_code==200
    assert owner.get(path+"/dashboard"+DATES).json()["metrics"]["operating_profit"] is None
    assert owner.put(path+"/expense-coverage",headers=headers,json=coverage).status_code==200
    batch=owner.post(path+"/imports",headers=headers,params={"resource":"expenses","filename":"expenses.csv"},content=b"external_id,incurred_on,category,amount\nE2,2026-10-11,rent,2.00\n").json()
    assert owner.post(path+f"/imports/{batch['id']}/commit",headers=headers,json={"confirmed":True,"preview_updated_at":batch["updated_at"]}).status_code==200
    assert owner.get(path+"/dashboard"+DATES).json()["metrics"]["operating_profit"] is None


@pytest.mark.parametrize("reason,quantity",[("restock","-1"),("sale","1"),("waste","1")])
def test_stock_movement_direction(reason,quantity):
    from app.data.schemas import InventoryInput
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        InventoryInput(external_id="M1",product_sku="P1",occurred_on="2026-10-10",quantity_delta=quantity,reason=reason)
