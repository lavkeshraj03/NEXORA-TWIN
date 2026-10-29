# Phase 5 — evaluated models

The Forecasts & risk screen trains tenant-specific sales/demand forecasters and a customer-inactivity classifier from actual stored paid orders. Numerical work uses NumPy statistical models; no LLM, provider credential, external training service or shared tenant model is involved. Demonstration mode is explicit and separate from real-record mode. Synthetic evaluation demonstrates functionality, not accuracy on a real business.

## Use

Import historical customers/products/orders first. Open Forecasts & risk, choose task, scope, a closed business-local date range and horizon. Confirm that the required history is fully imported: no-record buckets are treated as zero only under that acknowledgement. Missing imports cannot be distinguished automatically from genuine zero sales.

Daily histories require 28 buckets for an evaluated seasonal-naive baseline, 56 for a ridge candidate, and at least five nonzero buckets in the training partition. Weekly histories require 12 complete weeks for the baseline and 40 for ridge, from Monday through Sunday. Horizons are 1–30 days or 1–12 weeks. Training must end before the current business-local day and covers at most 730 days / 30000 sale lines. At most 20 immutable model runs are retained per business in this release. Longer history is not automatically better; imported coverage and business regime still matter.

For an explicit demonstration, use a separate retail business and import the retail customers/suppliers/products, then datasets/forecasting/orders.csv. Its 140 synthetic days cover 2026-06-11 through 2026-10-28. Choose that range and **Labelled demonstration records only**. Do not import both the short retail order file and this longer file unless you intend their combined dataset. This file has no automatic stock movements and is never auto-seeded.

## Forecasting method

Aggregation uses Decimal net line sales (quantity × price, line-rounded, minus discount, excluding tax) or product units. Only current-status paid orders qualify; pending/cancelled/refunded orders are excluded, so refunds can restate historical source values. Real mode excludes any sale line labelled demo at order or item level; demo mode includes such labelled lines only. Master-record demo flags do not override sale-line provenance. No currencies are converted.

The split is chronological: first 60% training, next 20% validation, final 20% test. There is no shuffle. Scaling and lag features use training information only. Candidates are a seasonal-naive baseline (repeat the last seven daily buckets / last weekly bucket) and a fixed-alpha ridge autoregression. Ridge uses intercept, elapsed time, lag one, seasonal lag and seasonal rolling mean; target scaling is fitted on the available past. Its L2 penalty is 0.1 and the intercept is unpenalized. The implementation uses a small NumPy linear solve, not a scikit-learn dependency.

The winner is the lowest validation MAE, preferring the baseline on ties. Test scores do not select the winner. Both candidates are refitted on training+validation before fixed-origin multi-step test forecasting. After evaluation, the selected algorithm is refitted on all observed history and its JSON parameters are stored for inference. Test predictions never consume held-out actual values recursively. Test length follows the split, which can differ from the requested deployment horizon; test results are not horizon-specific accuracy guarantees.

Evaluation stores MAE, RMSE and WAPE; WAPE is null when actual absolute totals are zero. ML calculations use floating point after exact historical aggregation. Output sales estimates use currency minor-unit strings and demand uses three decimals; these are statistical estimates, not accounting totals.

An optional residual band uses the selected candidate's absolute validation errors with finite-sample 90% nominal rank, requiring at least ten residuals. It is shown only within the validation horizon. Temporal dependence, model refitting and drift violate exchangeability assumptions: it is a diagnostic residual band, **not a calibrated or guaranteed prediction interval**. Unsupported bands remain null. The UI carries this limitation.

The design follows the chronology concerns in the [time-series validation reference](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) and the L2 objective described in the [ridge reference](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html). This release uses its own fixed split and explicitly bounded NumPy implementation, rather than those library estimators.

## Customer inactivity

The positive outcome is **no paid purchase in the next N days**, for customers with at least one paid purchase in the preceding 90 days. N is operator-selected from 14–90 days, default 30. This is inactivity, not confirmed customer loss; choose a cadence appropriate for the business profile.

Training features are purchase recency, 90-day frequency, 90-day average order value and tenure observed within that lookback. Complaints/support records are not available. Feature values never include purchases after the feature cutoff. Training cutoff is observed_end−2N, test cutoff observed_end−N; the subsequent outcome windows are disjoint and fully observed. Customers may recur across cutoffs, reflecting temporal generalization to an existing customer base. IDs are not model features. Later customers without qualifying early history are not silently inserted into training.

The classifier is fixed L2 logistic regression with training-only feature standardization, 500 deterministic gradient steps and a fixed 0.5 reporting threshold. It needs 50 training customers, ten examples/class, and 20 test customers with both classes. It reports precision, recall, F1, ROC-AUC and average precision alongside a training-prevalence baseline. No test-based hyperparameter or threshold selection occurs. After frozen evaluation it refits on both fully observed snapshots and estimates inactivity from the latest cutoff's features. Probabilities are uncalibrated and are labelled accordingly. At most 1000 purchasing customers and 30000 sale lines are supported. Refit at a later cutoff to obtain updated estimates; old predictions remain reproducible.

## Inventory and anomaly diagnostics

Inventory risk is explicitly deterministic: trailing 28-day recorded mean product demand × assumed lead days + assumed safety stock, compared with current ledger stock + assumed incoming units. Days of cover is null for zero demand. Lead time/incoming are assumptions, not verified purchase orders. Demand uses the selected real/demo scope; stock is the full current ledger, with a visible warning when demonstration stock movements exist. Use separate demo businesses. Missing sales, stock constraints and regime changes can understate risk. This is not a learned stockout probability or a guaranteed stockout date.

Anomalies are diagnostic deviations from the preceding 14–28 buckets' median/MAD (modified z-score >3.5). For zero MAD, flag deviations exceeding max(50% of absolute median, 1 unit). No future buckets enter the comparison. Up to 100 deviations per run are retained with date/value/method. Inspect source snapshots for the relevant day/week. These are not confirmed business incidents, causal explanations or fraud predictions.

## API and authorization

Every route starts `/api/v1/businesses/{business_id}/ml`. All roles may read model results and calculate diagnostics. Owners/administrators/analysts may train; only owners/administrators activate. Mutations require allowed Origin and CSRF. Training is limited to ten attempts/hour per business/user. Every model/product/source query is tenant scoped; product references use composite tenant foreign keys.

| Route | Behavior |
|---|---|
| POST /forecasts | `{task,start,end,aggregation,horizon,product_sku?,data_scope,coverage_confirmed:true}`; demand requires SKU, sales uses all products |
| POST /churn | `{end,inactivity_days,data_scope,coverage_confirmed:true}` |
| GET /runs?limit=20&offset=0 | Paginated model metadata |
| GET /runs/{id} | Saved configuration, history, evaluation, estimates and JSON artifact |
| GET /runs/{id}/sources?on=YYYY-MM-DD&limit=25&offset=0 | Immutable source values; on filters the day or entire weekly bucket |
| POST /runs/{id}/activate | Explicitly select active version for task/product/data scope |
| POST /runs/{id}/predict | `{horizon}`; load the saved forecast artifact without retraining |
| GET /runs/{id}/monitor | Compare live historical sources with the saved fingerprint |
| GET /runs/{id}/monitor?coverage_confirmed=true | Also score fully closed forecast periods whose imported coverage you confirm |
| GET /inventory-risk?product_sku=...&lead_days=7&incoming=0&safety=0&data_scope=real | Labelled deterministic calculation |

Model versions are UUIDs, with implementation version, dataset hash, feature definitions, training windows, evaluation and safe JSON parameters. No pickle, arbitrary uploaded model, filesystem artifact path or executable deserialization is used. A partial unique index with NULLS NOT DISTINCT allows only one active model per business/task/scope/product. Activation is an explicit operator selection, not an automatic quality certification. Any saved compatible version can serve inference. Source changes never mutate or silently retrain an existing model; monitoring reports stale sources. Forecast accuracy metrics are absent until closed future outcomes and explicit coverage confirmation exist. Churn monitoring checks historical source drift; later outcomes require a new labelled run.

## Verification and limits

Run backend tests with RUN_INTEGRATION=1, frontend typecheck/tests/build, Alembic upgrade/check and `PYTHONPATH=. .venv/bin/python ../scripts/verify_ml_http.py` from backend while the Docker stack is running. The HTTP script imports explicitly synthetic history, trains sales/demand/churn, reloads predictions, checks activation, source drift and tenant isolation, then removes only its own records.

No real-business predictive accuracy, calibration, load capacity or economic benefit is claimed. There is no pooled training, promotion/price/availability feature feed, hyperparameter search, multiple-fold backtesting, automated retraining, model-retention/deletion UI or external model registry. Training is synchronous and bounded for this MVP; large training jobs require a dedicated worker. Production needs workload limits, retention, fairness/segment review and monitoring thresholds based on business-specific validation. Phase 4 local-provider acceptance is now recorded separately in phase4-verification.md; numerical Phase 5 does not call that provider.
