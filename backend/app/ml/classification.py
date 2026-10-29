"""Small, deterministic L2 logistic model; no IDs or future transactions in features."""
import numpy as np


def fit_classifier(x, labels):
    x, labels = np.asarray(x, dtype=float), np.asarray(labels, dtype=float)
    if len(x) < 50 or min(int(labels.sum()), int((1-labels).sum())) < 10:
        raise ValueError("Churn training needs 50 eligible customers and at least ten examples in each class")
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-9] = 1
    features = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    weights = np.zeros(features.shape[1])
    for _ in range(500):
        probabilities = 1 / (1 + np.exp(-np.clip(features @ weights, -35, 35)))
        gradient = features.T @ (probabilities - labels) / len(x)
        gradient[1:] += 0.01 * weights[1:]
        weights -= 0.1 * gradient
    return {"algorithm": "logistic_inactivity", "weights": weights.tolist(), "mean": mean.tolist(), "scale": scale.tolist(), "l2": 0.01, "iterations": 500, "training_prevalence": float(labels.mean()), "features": ["purchase_recency_days", "purchase_frequency_90d", "average_order_value_90d", "tenure_within_90d"]}


def predict_classifier(artifact, x):
    if not x:
        return []
    x = np.asarray(x, dtype=float)
    features = np.column_stack([np.ones(len(x)), (x - np.asarray(artifact["mean"])) / np.asarray(artifact["scale"])])
    values = 1 / (1 + np.exp(-np.clip(features @ np.asarray(artifact["weights"]), -35, 35)))
    return values.tolist()


def classification_metrics(labels, probabilities):
    labels, probabilities = np.asarray(labels, dtype=int), np.asarray(probabilities, dtype=float)
    if len(labels) != len(probabilities) or len(labels) < 20 or len(set(labels.tolist())) != 2:
        raise ValueError("Churn evaluation needs 20 eligible customers and both outcome classes")
    predictions = probabilities >= 0.5
    tp, fp, fn = int(((labels == 1) & predictions).sum()), int(((labels == 0) & predictions).sum()), int(((labels == 1) & ~predictions).sum())
    precision, recall = tp / (tp + fp) if tp + fp else 0, tp / (tp + fn) if tp + fn else 0
    # Threshold groups give correct tie handling for ROC and average precision.
    order = np.argsort(-probabilities, kind="stable")
    y, scores = labels[order], probabilities[order]
    positive, negative = int(labels.sum()), int((1-labels).sum())
    tp_count, fp_count, last_recall, last_fpr, average_precision, auc = 0, 0, 0.0, 0.0, 0.0, 0.0
    index = 0
    while index < len(y):
        end = index + 1
        while end < len(y) and scores[end] == scores[index]: end += 1
        tp_count += int(y[index:end].sum())
        fp_count += end-index-int(y[index:end].sum())
        current_recall, fpr = tp_count/positive, fp_count/negative
        average_precision += (current_recall-last_recall) * tp_count/(tp_count+fp_count)
        auc += (fpr-last_fpr) * (current_recall+last_recall)/2
        last_recall, last_fpr, index = current_recall, fpr, end
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(2*precision*recall/(precision+recall), 4) if precision+recall else 0, "roc_auc": round(auc, 4), "pr_auc_average_precision": round(average_precision, 4), "observations": len(labels), "positive_class": "No paid purchase in the next inactivity window", "threshold": 0.5}
