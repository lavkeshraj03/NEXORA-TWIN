from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from app.schemas import Input


class ScenarioInput(Input):
    name: str = Field(min_length=1, max_length=100)
    baseline_snapshot_id: UUID
    product_sku: str | None = Field(default=None, min_length=1, max_length=80)
    supplier_external_id: str | None = Field(default=None, min_length=1, max_length=80)
    price_change_pct: Decimal = Field(default=Decimal(0), ge=-90, le=200, decimal_places=2)
    price_elasticity: Decimal | None = Field(default=None, ge=-5, le=0, decimal_places=3)
    demand_change_pct: Decimal = Field(default=Decimal(0), ge=-100, le=200, decimal_places=2)
    unit_cost_change_pct: Decimal = Field(default=Decimal(0), ge=-100, le=200, decimal_places=2)
    marketing_change_pct: Decimal = Field(default=Decimal(0), ge=-100, le=300, decimal_places=2)
    employee_cost_change_pct: Decimal = Field(default=Decimal(0), ge=-100, le=200, decimal_places=2)
    customer_loss_pct: Decimal = Field(default=Decimal(0), ge=0, le=100, decimal_places=2)
    replenishment_units: Decimal = Field(default=Decimal(0), ge=0, le=1000000, decimal_places=3)
    replenishment_unit_cost: Decimal | None = Field(default=None, ge=0, le=1000000000, decimal_places=4)
    stock_constrained: bool = False
    sensitivity_elasticities: list[Decimal] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def assumptions(self):
        self.name = self.name.strip()
        if not self.name: raise ValueError("Enter a scenario name")
        if self.price_change_pct and self.price_elasticity is None:
            raise ValueError("Price changes require an explicit elasticity assumption, including zero for fixed demand")
        if self.replenishment_units and not self.product_sku:
            raise ValueError("Replenishment requires a product SKU")
        if any(not value.is_finite() or value < -5 or value > 0 or value.as_tuple().exponent < -3 for value in self.sensitivity_elasticities):
            raise ValueError("Sensitivity elasticities must be finite values from -5 to 0 with up to three decimal places")
        return self


class RunInput(ScenarioInput):
    preview_hash: str = Field(min_length=64, max_length=64)
    assumptions_confirmed: Literal[True]
