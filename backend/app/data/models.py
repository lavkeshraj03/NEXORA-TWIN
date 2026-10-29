from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def identity(table: str, external: str = "external_id"):
    return (UniqueConstraint("business_id", "id", name=f"uq_{table}_tenant_id"), UniqueConstraint("business_id", external, name=f"uq_{table}_external"))


class Customer(Record, Base):
    __tablename__ = "customers"
    external_id: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(254))
    __table_args__ = identity("customers")


class Supplier(Record, Base):
    __tablename__ = "suppliers"
    external_id: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(254))
    __table_args__ = identity("suppliers")


class Product(Record, Base):
    __tablename__ = "products"
    sku: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    supplier_id: Mapped[UUID | None] = mapped_column(nullable=True)
    __table_args__ = identity("products", "sku") + (
        ForeignKeyConstraint(["business_id", "supplier_id"], ["suppliers.business_id", "suppliers.id"], name="fk_product_tenant_supplier"),
        CheckConstraint("unit_price >= 0 AND (unit_cost IS NULL OR unit_cost >= 0)", name="product_prices_valid"),
    )


class Order(Record, Base):
    __tablename__ = "orders"
    external_id: Mapped[str] = mapped_column(String(80))
    customer_id: Mapped[UUID] = mapped_column()
    ordered_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    status_reason: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = identity("orders") + (
        ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.id"], name="fk_order_tenant_customer"),
        CheckConstraint("status IN ('paid','pending','cancelled','refunded')", name="order_status_valid"),
        Index("orders_tenant_date", "business_id", "ordered_on"),
    )


class OrderItem(Record, Base):
    __tablename__ = "order_items"
    order_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    __table_args__ = (
        UniqueConstraint("business_id", "order_id", "product_id", name="uq_order_product_line"),
        ForeignKeyConstraint(["business_id", "order_id"], ["orders.business_id", "orders.id"], ondelete="CASCADE", name="fk_item_tenant_order"),
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.id"], name="fk_item_tenant_product"),
        CheckConstraint("quantity > 0 AND unit_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND (unit_cost IS NULL OR unit_cost >= 0)", name="order_item_amounts_valid"),
        Index("items_tenant_order", "business_id", "order_id"),
    )


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal(0))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.id"], ondelete="CASCADE", name="fk_balance_tenant_product"),
        CheckConstraint("quantity >= 0", name="inventory_nonnegative"),
    )


class InventoryMovement(Record, Base):
    __tablename__ = "inventory_movements"
    external_id: Mapped[str] = mapped_column(String(160))
    product_id: Mapped[UUID] = mapped_column()
    occurred_on: Mapped[date] = mapped_column(Date)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    reason: Mapped[str] = mapped_column(String(24))
    __table_args__ = identity("inventory_movements") + (
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.id"], name="fk_movement_tenant_product"),
        CheckConstraint("quantity_delta <> 0", name="movement_nonzero"),
    )


class Expense(Record, Base):
    __tablename__ = "expenses"
    external_id: Mapped[str] = mapped_column(String(80))
    incurred_on: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16))
    status_reason: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = identity("expenses") + (
        CheckConstraint("amount > 0", name="expense_positive"),
        CheckConstraint("status IN ('paid','voided')", name="expense_status_valid"),
        Index("expenses_tenant_date", "business_id", "incurred_on"),
    )


class ExpenseCoverage(Base):
    __tablename__ = "expense_coverage"
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, primary_key=True)
    end_date: Mapped[date] = mapped_column(Date, primary_key=True)
    complete: Mapped[bool] = mapped_column(Boolean)
    confirmed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("end_date >= start_date", name="coverage_period_valid"),)


class ImportBatch(Record, Base):
    __tablename__ = "import_batches"
    resource: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    filename: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="preview")
    columns: Mapped[list[str]] = mapped_column(JSONB)
    raw_rows: Mapped[list[dict]] = mapped_column(JSONB)
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    valid_count: Mapped[int] = mapped_column(default=0)
    imported_count: Mapped[int] = mapped_column(default=0)
    __table_args__ = (UniqueConstraint("business_id", "resource", "content_hash", name="uq_import_content"), CheckConstraint("status IN ('preview','validated','committed')", name="import_status_valid"))
