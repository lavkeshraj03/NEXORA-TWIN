import json
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest

from app.ml.classification import classification_metrics, fit_classifier, predict_classifier
from app.ml.forecasting import anomalies, fit, forecast_long, metrics, predict, train_forecast
from app.ml.service import churn_snapshot


def points(values):
    start = date(2025, 1, 1)
    return [{"date": (start+timedelta(days=index)).isoformat(), "value": str(value)} for index, value in enumerate(values)]


def test_forecast_evaluates_future_and_reloadable_json_artifact():
    history = points([100+index*3+(index%7)*2 for index in range(120)])
    artifact, result = train_forecast(history, "daily", 7, 2)
    assert result["split"]["train_end"] < result["split"]["validation_start"] <= result["split"]["validation_end"] < result["split"]["test_start"]
    assert set(result["candidates"]) == {"seasonal_naive", "ridge_autoregression"}
    assert len(result["test_points"]) == 24
    assert predict(json.loads(json.dumps(artifact)), 7) == predict(artifact, 7)
    assert all(Decimal(value) >= 0 for value in result["forecast_values"])


def test_test_values_cannot_select_the_model_or_change_validation_scores():
    values = [100+index*3 for index in range(100)]
    _, first = train_forecast(points(values), "daily", 7, 2)
    _, changed = train_forecast(points(values[:80]+[10000]*20), "daily", 7, 2)
    assert first["selected_model"] == changed["selected_model"]
    for name in first["candidates"]:
        assert first["candidates"][name]["validation"] == changed["candidates"][name]["validation"]
    assert first["test_points"][0]["prediction"] == changed["test_points"][0]["prediction"]
    assert first["candidates"][first["selected_model"]]["test"] != changed["candidates"][changed["selected_model"]]["test"]


def test_baseline_short_history_and_missing_intervals_are_explicit():
    _, result = train_forecast(points([10]*28), "daily", 7, 2)
    assert result["baseline_only"] and result["selected_model"] == "seasonal_naive"
    assert result["residual_band"] is None
    with pytest.raises(ValueError, match="Insufficient"):
        train_forecast(points([10]*27), "daily", 7, 2)
    with pytest.raises(ValueError, match="Insufficient"):
        train_forecast(points([0]*100), "daily", 7, 2)
    with pytest.raises(ValueError, match="before validation"):
        train_forecast(points([0]*90+[10]*10), "daily", 7, 2)


def test_long_history_evaluation_and_nonnegative_bounded_inference():
    _, result = train_forecast(points([10+index%7 for index in range(366)]), "daily", 30, 3)
    assert result["candidates"]["seasonal_naive"]["test"]["observations"] == 74
    model = fit(np.arange(1, 70), "ridge_autoregression", 7)
    assert len(forecast_long(model, 74)) == 74
    with pytest.raises(ValueError): predict(model, 31)


def test_metrics_and_anomaly_sources_are_not_fabricated():
    assert metrics([0, 0], [1, 1])["wape_pct"] is None
    assert metrics([10, 20], [12, 16])["mae"] == 3
    history = points([10]*28+[100])
    alerts = anomalies(history)
    assert len(alerts) == 1 and alerts[0]["date"] == history[-1]["date"]
    assert alerts[0]["method"] == "zero_mad_deviation_rule"


def test_inactivity_features_do_not_include_future_purchases():
    cutoff = date(2026, 1, 1)
    past = [{"customer_id": "C1", "date": cutoff-timedelta(days=3), "amount": Decimal("10")}]
    future = {"customer_id": "C1", "date": cutoff+timedelta(days=7), "amount": Decimal("999999")}
    first = churn_snapshot(past, cutoff, 30, True)[0]
    changed = churn_snapshot(past+[future], cutoff, 30, True)[0]
    assert first["features"] == changed["features"] == [3, 1, 10.0, 3]
    assert first["label"] == 1 and changed["label"] == 0


def test_logistic_model_and_classification_tie_metrics():
    x = [[float(index), index%3, index*2, 30] for index in range(80)]
    labels = [int(index >= 40) for index in range(80)]
    artifact = fit_classifier(x, labels)
    scores = predict_classifier(json.loads(json.dumps(artifact)), x)
    result = classification_metrics(labels, scores)
    assert result["roc_auc"] > 0.95 and result["f1"] > 0.9
    assert classification_metrics(labels, [0.5]*80)["roc_auc"] == 0.5
    assert classification_metrics(labels, [0.5]*80)["pr_auc_average_precision"] == 0.5
    with pytest.raises(ValueError, match="50"):
        fit_classifier(x[:20], labels[:20])
    with pytest.raises(ValueError, match="both"):
        classification_metrics([0]*20, [0.1]*20)
