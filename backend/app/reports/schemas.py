from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from app.schemas import Input


class ReportInput(Input):
    name:str=Field(min_length=1,max_length=100)
    kind:Literal["monthly","revenue_expenses","sales_forecast","inventory_risk","customer_inactivity","scenario_comparison","investigation"]
    snapshot_id:UUID|None=None
    model_run_id:UUID|None=None
    scenario_run_ids:list[UUID]=Field(default_factory=list,max_length=2)
    investigation_id:UUID|None=None
    horizon:int=Field(default=7,ge=1,le=30)
    lead_days:int=Field(default=7,ge=1,le=180)
    incoming_units:Decimal=Field(default=Decimal(0),ge=0,le=1000000000,decimal_places=3)
    safety_units:Decimal=Field(default=Decimal(0),ge=0,le=1000000000,decimal_places=3)

    @model_validator(mode="after")
    def references(self):
        expected={"monthly":"snapshot","revenue_expenses":"snapshot","inventory_risk":"snapshot","sales_forecast":"model","customer_inactivity":"model","scenario_comparison":"scenarios","investigation":"investigation"}[self.kind]
        supplied={key for key,value in [("snapshot",self.snapshot_id),("model",self.model_run_id),("scenarios",self.scenario_run_ids),("investigation",self.investigation_id)] if value}
        if supplied!={expected}:raise ValueError("Select only the source required for this report type")
        if expected=="scenarios" and (len(self.scenario_run_ids)!=2 or len(set(self.scenario_run_ids))!=2):raise ValueError("Select two different scenarios")
        if self.kind!="inventory_risk" and (self.incoming_units or self.safety_units or self.lead_days!=7):raise ValueError("Stock assumptions belong to inventory risk reports")
        if self.kind!="sales_forecast" and self.horizon!=7:raise ValueError("Forecast horizon belongs to sales forecast reports")
        return self
