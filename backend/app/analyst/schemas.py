from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, model_validator
from app.schemas import Input

ToolName = Literal["query_sales", "query_inventory", "query_customers", "query_expenses", "search_business_documents", "run_sales_forecast", "predict_customer_churn", "detect_anomalies", "run_what_if_simulation", "compare_scenarios", "generate_business_report"]


class InvestigationInput(Input):
    question: str = Field(min_length=5, max_length=1500)
    start: date
    end: date
    product_sku: str | None = Field(default=None, min_length=1, max_length=80)
    model_data_scope: Literal["real", "demo"] = "real"
    forecast_run_id: UUID | None = None
    churn_run_id: UUID | None = None
    scenario_run_ids: list[UUID] = Field(default_factory=list, max_length=2)
    document_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end < self.start or (self.end-self.start).days > 365:
            raise ValueError("Choose a reporting period of 1–366 days")
        if self.start < date.min+timedelta(days=(self.end-self.start).days+1):
            raise ValueError("The selected window needs a preceding comparison period")
        return self


class Plan(Input):
    tools: list[ToolName] = Field(max_length=3)


class Selection(Input):
    supported: StrictBool
    finding_ids: list[str] = Field(max_length=6)
    recommendation_ids: list[str] = Field(max_length=3)
