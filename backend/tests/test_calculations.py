from decimal import Decimal as D
import pytest
from app.data.calculations import financial_summary, line_amounts, money


def test_line_rounding_discounts_taxes_and_cogs():
    revenue, cogs, payable = line_amounts(D("1.5"), D("10.01"), D("4.005"), D("1.00"), D("2.00"), "INR")
    assert (revenue, cogs, payable) == (D("14.02"), D("6.01"), D("16.02"))


def test_financial_formulas_use_order_count_not_line_count():
    result = financial_summary([(D("100"), D("40")), (D("50"), D("20"))], [D("10"), D("5")], 1, "USD", True)
    assert result == {"revenue":D("150.00"),"cogs":D("60.00"),"gross_profit":D("90.00"),"gross_margin_pct":D("60.00"),"recorded_expenses":D("15.00"),"operating_profit":D("75.00"),"average_order_value":D("150.00"),"paid_orders":1}


def test_unknown_cost_and_unconfirmed_expenses_stay_incomplete():
    result = financial_summary([(D("100"), None)], [], 1, "USD", False)
    assert result["revenue"] == D("100.00")
    assert result["cogs"] is result["gross_profit"] is result["operating_profit"] is None
    assert financial_summary([(D("100"), D("20"))], [], 1, "USD", False)["operating_profit"] is None


def test_zero_revenue_and_empty_history_do_not_divide_by_zero():
    result = financial_summary([], [], 0, "INR", False)
    assert result["average_order_value"] is result["gross_margin_pct"] is None
    assert result["revenue"] == D("0.00")


@pytest.mark.parametrize("currency,value,expected", [("JPY","2.5","3"),("KWD","1.2345","1.235"),("INR","0.005","0.01")])
def test_currency_minor_units(currency, value, expected):
    assert money(D(value), currency) == D(expected)


@pytest.mark.parametrize("quantity,price,discount,tax", [("0","10","0","0"),("1","10","11","0"),("1","10","0.001","0"),("1","10","0","-1")])
def test_invalid_financial_inputs(quantity, price, discount, tax):
    with pytest.raises(ValueError):
        line_amounts(D(quantity), D(price), None, D(discount), D(tax), "INR")


def test_no_implicit_currency_conversion_or_unknown_precision():
    with pytest.raises(ValueError, match="supported currency"):
        money(D("10"), "ZZZ")
