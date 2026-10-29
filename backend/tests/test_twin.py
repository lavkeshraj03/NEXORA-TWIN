from copy import deepcopy

from app.twin.service import compare


def test_comparison_preserves_units_missing_baselines_and_unequal_windows():
    left = {"business":{"id":"same","currency":"INR","timezone":"Asia/Kolkata"}, "period":{"start":"2026-09-01","end":"2026-09-30","days":30}, "metrics":{"revenue":"0.00","gross_margin_pct":"12.50","operating_profit":None,"paid_orders":2}, "source_versions":{"orders":{"sha256":"old"}}}
    right = deepcopy(left)
    right["period"] = {"start":"2026-10-01","end":"2026-10-28","days":28}
    right["metrics"] = {"revenue":"20.00","gross_margin_pct":"10.00","operating_profit":"-2.00","paid_orders":1}
    right["source_versions"]["orders"]["sha256"] = "new"
    result = compare(left, right)
    assert result["equal_period_length"] is False and result["same_period"] is False
    assert result["metrics"]["revenue"]["percentage_change"] is None
    assert result["metrics"]["operating_profit"]["absolute_change"] is None
    assert result["metrics"]["gross_margin_pct"]["absolute_change"] == "-2.50"
    assert result["metrics"]["gross_margin_pct"]["unit"] == "percentage_points"
    assert result["metrics"]["paid_orders"]["absolute_change"] == "-1"
    assert result["source_changes"] == ["orders"]


def test_negative_profit_baseline_uses_absolute_denominator():
    state = {"business":{"id":"same","currency":"INR","timezone":"UTC"}, "period":{"days":1}, "metrics":{"operating_profit":"-10.00"}, "source_versions":{}}
    right = deepcopy(state)
    right["metrics"]["operating_profit"] = "-5.00"
    assert compare(state,right)["metrics"]["operating_profit"]["percentage_change"] == "50.00"
