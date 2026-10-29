from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.simulation.engine import calculate
from app.simulation.schemas import ScenarioInput


def parameters(**changes):
    return ScenarioInput(name="Assumed scenario", baseline_snapshot_id=uuid4(), **changes).model_dump(mode="json")


def baseline():
    return {"captured_at":"2026-10-29T00:00:00+00:00", "start":"2026-10-01", "end":"2026-10-28", "business":{"currency":"INR","timezone":"Asia/Kolkata","modules":["inventory"]}, "sources":{
        "products":[{"id":"P1","sku":"P1","name":"Demo product","supplier_id":"S1","unit_cost":"600","is_demo":True}],
        "suppliers":[{"id":"S1","external_id":"SUP1"}],
        "orders":[{"id":"O1","status":"paid","ordered_on":"2026-10-10"}],
        "order_items":[{"id":"I1","order_id":"O1","product_id":"P1","quantity":"1000.000","unit_price":"1000","unit_cost":"600","discount_amount":"0","tax_amount":"100"}],
        "balances":[{"product_id":"P1","quantity":"100.000"}],
        "expenses":[{"status":"paid","incurred_on":"2026-10-10","category":"marketing","amount":"50000"}],
        "expense_coverage":[{"start_date":"2026-10-01","end_date":"2026-10-28","complete":True}]}}


def test_zero_change_reproduces_financial_baseline_without_mutating_inputs():
    inputs = baseline()
    original = deepcopy(inputs)
    result = calculate(inputs,parameters())
    assert result["metrics"] == result["baseline_metrics"]
    assert result["metrics"]["operating_profit"] == "350000.00"
    assert result["kind"] == "hypothetical_simulation" and result["demo_records_present"]
    assert inputs == original


def test_price_response_is_explicit_decimal_and_sensitivity_is_not_a_guarantee():
    with pytest.raises(ValidationError): parameters(price_change_pct="10")
    result = calculate(baseline(),parameters(price_change_pct="10",price_elasticity="-1",sensitivity_elasticities=["-0.5","-1","-2"]))
    assert result["demand_units"] == "909.091"
    assert result["metrics"]["revenue"] == "1000000.10"
    assert result["metrics"]["operating_profit"] == "404545.50"
    assert len(result["sensitivity"]) == 3
    assert Decimal(result["sensitivity_extremes"]["best_operating_profit"]) > Decimal(result["sensitivity_extremes"]["worst_operating_profit"])
    fixed = calculate(baseline(),parameters(price_change_pct="10",price_elasticity="0"))
    assert fixed["demand_units"] == "1000.000" and fixed["metrics"]["revenue"] == "1100000.00"


def test_expense_changes_do_not_invent_marketing_returns_or_employee_productivity():
    result = calculate(baseline(),parameters(marketing_change_pct="100",employee_cost_change_pct="50"))
    assert result["metrics"]["revenue"] == "1000000.00"
    assert result["metrics"]["recorded_expenses"] == "100000.00"
    assert any("No paid payroll" in warning for warning in result["warnings"])


def test_replenishment_cash_is_separate_from_profit_and_stock_is_bounded():
    result = calculate(baseline(),parameters(product_sku="P1",replenishment_units="400",stock_constrained=True))
    assert result["inventory"][0]["fulfilled_units"] == "500.000"
    assert result["inventory"][0]["unfulfilled_units"] == "500.000"
    assert result["inventory"][0]["projected_closing_units"] == "0"
    assert result["replenishment_cash_outlay"] == "240000.00"
    assert result["metrics"]["operating_profit"] == "150000.00"
    assert result["metrics"]["recorded_expenses"] == "50000.00"


def test_loss_and_cost_assumptions_combine_without_double_counting():
    result = calculate(baseline(),parameters(demand_change_pct="100",customer_loss_pct="50",supplier_external_id="SUP1",unit_cost_change_pct="10"))
    assert result["demand_units"] == "1000.000"
    assert result["metrics"]["cogs"] == "660000.00"
    zero = calculate(baseline(),parameters(customer_loss_pct="100"))
    assert zero["metrics"]["revenue"] == "0.00" and zero["metrics"]["cogs"] == "0.00"
    assert zero["metrics"]["operating_profit"] == "-50000.00"


def test_unknown_costs_and_coverage_are_not_silently_filled():
    inputs = baseline()
    inputs["sources"]["order_items"][0]["unit_cost"] = None
    result = calculate(inputs,parameters())
    assert result["metrics"]["cogs"] is None and result["metrics"]["operating_profit"] is None
    inputs = baseline()
    inputs["sources"]["expense_coverage"] = []
    assert calculate(inputs,parameters())["metrics"]["operating_profit"] is None
    inputs["sources"]["products"][0]["unit_cost"] = None
    with pytest.raises(ValueError,match="replenishment unit-cost"):
        calculate(inputs,parameters(product_sku="P1",replenishment_units="1"))


@pytest.mark.parametrize("changes",[{"price_change_pct":"-100","price_elasticity":"0"},{"price_elasticity":"NaN"},{"demand_change_pct":"Infinity"},{"customer_loss_pct":"101"},{"sensitivity_elasticities":["-6"]},{"replenishment_units":"1"}])
def test_invalid_or_unbounded_assumptions_are_rejected(changes):
    with pytest.raises(ValidationError): parameters(**changes)


def test_unknown_targets_disabled_stock_and_excessive_quantities_fail_explicitly():
    with pytest.raises(ValueError,match="Product SKU"):
        calculate(baseline(),parameters(product_sku="FOREIGN"))
    with pytest.raises(ValueError,match="Supplier reference"):
        calculate(baseline(),parameters(supplier_external_id="FOREIGN"))
    inputs = baseline()
    inputs["business"]["modules"] = []
    with pytest.raises(ValueError,match="inventory-enabled"):
        calculate(inputs,parameters(stock_constrained=True))
    inputs = baseline()
    inputs["sources"]["order_items"][0]["quantity"] = "1000000000"
    with pytest.raises(ValueError,match="one billion"):
        calculate(inputs,parameters(demand_change_pct="200"))


def test_zero_price_lines_cannot_claim_a_defined_price_elasticity():
    inputs=baseline()
    inputs["sources"]["order_items"][0]["unit_price"]="0"
    with pytest.raises(ValueError,match="positive baseline prices"):
        calculate(inputs,parameters(price_change_pct="10",price_elasticity="-1"))
