"""Deterministic per-tenant statistical models. Financial aggregation happens in Decimal upstream."""
from decimal import Decimal, ROUND_HALF_UP
from math import ceil, isfinite

import numpy as np


def decimal_value(value, places):
    if not isfinite(float(value)) or abs(float(value)) > 1e18:
        raise ValueError("Model output exceeds the supported numerical range")
    return Decimal(str(max(0.0, float(value)))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def metrics(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if len(actual) == 0 or len(actual) != len(predicted) or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Evaluation requires finite, matched observations")
    errors = actual - predicted
    denominator = float(np.abs(actual).sum())
    return {"mae": round(float(np.abs(errors).mean()), 6), "rmse": round(float(np.sqrt((errors ** 2).mean())), 6), "wape_pct": round(float(np.abs(errors).sum()) / denominator * 100, 4) if denominator else None, "observations": len(actual)}


def features(history, index, scale, training_size, season):
    window = history[-season:]
    return [1.0, index / training_size, history[-1] / scale, history[-season] / scale, float(np.mean(window)) / scale]


def fit(values, algorithm, season):
    values = np.asarray(values, dtype=float)
    if algorithm == "seasonal_naive":
        return {"algorithm": algorithm, "season": season, "last_cycle": values[-season:].tolist()}
    if algorithm != "ridge_autoregression" or len(values) < season + 12:
        raise ValueError("Not enough training observations for the requested model")
    scale = max(float(values.mean()), 1.0)
    x = np.asarray([features(values[:index], index, scale, len(values), season) for index in range(season, len(values))])
    y = values[season:] / scale
    penalty = np.eye(x.shape[1]) * 0.1
    penalty[0, 0] = 0
    coefficients = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    return {"algorithm": algorithm, "season": season, "coefficients": coefficients.tolist(), "scale": scale, "training_size": len(values), "tail": values[-season:].tolist(), "ridge_alpha": 0.1, "features": ["intercept", "elapsed_bucket/training_size", "lag_1/scale", "seasonal_lag/scale", "seasonal_mean/scale"]}


def predict(artifact, horizon):
    if not 1 <= horizon <= 30:
        raise ValueError("Forecast horizon must be 1–30 periods")
    season = artifact["season"]
    if artifact["algorithm"] == "seasonal_naive":
        cycle = artifact["last_cycle"]
        return [float(cycle[index % len(cycle)]) for index in range(horizon)]
    if artifact["algorithm"] != "ridge_autoregression":
        raise ValueError("Unsupported model artifact")
    history = list(artifact["tail"])
    for index in range(horizon):
        x = features(history, artifact["training_size"] + index, artifact["scale"], artifact["training_size"], season)
        value = max(0.0, float(np.dot(x, artifact["coefficients"])) * artifact["scale"])
        if not isfinite(value) or value > 1e18:
            raise ValueError("Forecast diverged; no result was saved")
        history.append(value)
    return history[-horizon:]


def train_forecast(points, aggregation, horizon, places):
    n = len(points)
    minimum, ridge_minimum, season = (28, 56, 7) if aggregation == "daily" else (12, 40, 1)
    if n < minimum or sum(Decimal(point["value"]) > 0 for point in points) < 5:
        raise ValueError(f"Insufficient history: need at least {minimum} complete {aggregation} buckets and five nonzero buckets")
    if aggregation == "weekly" and horizon > 12:
        raise ValueError("Weekly forecasts support 1–12 weeks")
    values = np.asarray([float(point["value"]) for point in points])
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("History must contain finite nonnegative values")
    train_end = int(n * 0.6)
    validation_end = int(n * 0.8)
    train, validation, test = values[:train_end], values[train_end:validation_end], values[validation_end:]
    if int((train > 0).sum()) < 5:
        raise ValueError("Insufficient history before validation: need five nonzero training buckets")
    candidates, validation_predictions, test_predictions = {}, {}, {}
    algorithms = ["seasonal_naive"] + (["ridge_autoregression"] if n >= ridge_minimum else [])
    for algorithm in algorithms:
        first_model = fit(train, algorithm, season)
        validation_predictions[algorithm] = [float(decimal_value(value, places)) for value in forecast_long(first_model, len(validation))]
        second_model = fit(values[:validation_end], algorithm, season)
        # Evaluation can span >30 buckets, but never consume held-out values recursively.
        test_predictions[algorithm] = [float(decimal_value(value, places)) for value in forecast_long(second_model, len(test))]
        candidates[algorithm] = {"validation": metrics(validation, validation_predictions[algorithm]), "test": metrics(test, test_predictions[algorithm])}
    selected = min(algorithms, key=lambda name: (candidates[name]["validation"]["mae"], algorithms.index(name)))
    model = fit(values, selected, season)
    forecast = [decimal_value(value, places) for value in predict(model, horizon)]
    residuals = np.abs(validation - np.asarray(validation_predictions[selected]))
    rank = ceil((len(residuals) + 1) * 0.9)
    band = float(np.sort(residuals)[rank - 1]) if rank <= len(residuals) and len(residuals) >= 10 else None
    evaluation = [{"date": points[validation_end + index]["date"], "actual": str(decimal_value(actual, places)), "prediction": str(decimal_value(test_predictions[selected][index], places)), "baseline": str(decimal_value(test_predictions["seasonal_naive"][index], places))} for index, actual in enumerate(test)]
    return model, {"selected_model": selected, "selection": "Lowest validation MAE; chronological test was not used for selection", "candidates": candidates, "split": {"train_start": points[0]["date"], "train_end": points[train_end-1]["date"], "validation_start": points[train_end]["date"], "validation_end": points[validation_end-1]["date"], "test_start": points[validation_end]["date"], "test_end": points[-1]["date"]}, "test_points": evaluation, "forecast_values": [str(value) for value in forecast], "residual_band": str(decimal_value(band, places)) if band is not None else None, "band_description": "90% nominal split-conformal-style absolute validation-error band; temporal dependence/drift violate exchangeability. Not a guaranteed prediction interval. Band omitted beyond validation horizon.", "band_max_horizon": len(validation), "baseline_only": len(algorithms) == 1, "training_buckets": n}


def forecast_long(artifact, horizon):
    # Same recursion as predict, bounded by the dataset size, for chronological evaluation.
    if artifact["algorithm"] == "seasonal_naive":
        cycle = artifact["last_cycle"]
        return [float(cycle[index % len(cycle)]) for index in range(horizon)]
    history = list(artifact["tail"])
    for index in range(horizon):
        row = features(history, artifact["training_size"] + index, artifact["scale"], artifact["training_size"], artifact["season"])
        value = max(0.0, float(np.dot(row, artifact["coefficients"])) * artifact["scale"])
        if not isfinite(value) or value > 1e18:
            raise ValueError("Forecast diverged; no result was saved")
        history.append(value)
    return history[-horizon:]


def anomalies(points):
    """Past-only rolling median/MAD diagnostic; not a fraud classifier."""
    values = [float(point["value"]) for point in points]
    output = []
    for index in range(14, len(values)):
        previous = np.asarray(values[max(0, index-28):index])
        median = float(np.median(previous))
        mad = float(np.median(np.abs(previous-median)))
        difference = abs(values[index]-median)
        score = 0.6745*difference/mad if mad else None
        flagged = score > 3.5 if score is not None else difference > max(abs(median)*0.5, 1.0)
        if flagged:
            output.append({"date": points[index]["date"], "value": points[index]["value"], "past_median": round(median, 6), "modified_z_score": round(score, 4) if score is not None else None, "method": "rolling_median_mad" if mad else "zero_mad_deviation_rule", "definition": "Statistical deviation from the preceding 14–28 buckets; inspect source records, not a confirmed business incident"})
    return output[:100]
