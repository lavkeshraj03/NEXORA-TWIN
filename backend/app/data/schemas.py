from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from app.schemas import Input

Ref = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")]
Amount = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4, le=Decimal("1000000000"))]
Quantity = Annotated[Decimal, Field(gt=0, le=Decimal("1000000000"), max_digits=18, decimal_places=3)]


class CustomerInput(Input):
    external_id: Ref
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    is_demo: bool = False


class ProductInput(Input):
    sku: Ref
    name: str = Field(min_length=1, max_length=160)
    unit_price: Amount
    unit_cost: Amount | None = None
    supplier_external_id: Ref | None = None
    initial_stock: Annotated[Decimal, Field(ge=0, le=Decimal("1000000000"), max_digits=18, decimal_places=3)] = Decimal(0)
    is_demo: bool = False


class OrderRow(Input):
    external_id: Ref
    ordered_on: date
    customer_external_id: Ref
    product_sku: Ref
    quantity: Quantity
    unit_price: Amount
    unit_cost: Amount | None = None
    discount_amount: Amount = Decimal(0)
    tax_amount: Amount = Decimal(0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    status: Literal["paid", "pending", "cancelled", "refunded"] = "paid"
    is_demo: bool = False


class InventoryInput(Input):
    external_id: Ref
    product_sku: Ref
    occurred_on: date
    quantity_delta: Annotated[Decimal, Field(ge=Decimal("-1000000000"), le=Decimal("1000000000"), max_digits=18, decimal_places=3)]
    reason: Literal["restock", "sale", "adjustment", "waste"]
    is_demo: bool = False

    @field_validator("quantity_delta")
    @classmethod
    def nonzero(cls, value):
        if not value:
            raise ValueError("Inventory movement cannot be zero")
        return value

    @model_validator(mode="after")
    def valid_direction(self):
        if self.reason == "restock" and self.quantity_delta < 0:
            raise ValueError("Restock quantity must be positive")
        if self.reason in {"sale", "waste"} and self.quantity_delta > 0:
            raise ValueError("Sale and waste quantities must be negative")
        return self


class ExpenseInput(Input):
    external_id: Ref
    incurred_on: date
    category: Literal["rent", "payroll", "marketing", "utilities", "transport", "other"]
    amount: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4, le=Decimal("1000000000"))]
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    status: Literal["paid", "voided"] = "paid"
    is_demo: bool = False


class MappingInput(Input):
    mapping: dict[str, str]


class ConfirmInput(Input):
    confirmed: Literal[True]
    preview_updated_at: datetime


class CoverageInput(Input):
    start_date: date
    end_date: date
    complete: bool

    @model_validator(mode="after")
    def valid_period(self):
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 365:
            raise ValueError("Choose a reporting range of 1–366 days")
        return self


class StatusInput(Input):
    status: Literal["paid", "cancelled", "refunded", "voided"]
    reason: str = Field(min_length=5, max_length=200)


SCHEMAS = {"customers": CustomerInput, "suppliers": CustomerInput, "products": ProductInput, "orders": OrderRow, "inventory": InventoryInput, "expenses": ExpenseInput}
