# What-If Lab — deterministic engine version 1

Scenarios are **hypothetical calculations**, distinct from historical actuals and ML forecasts. They replay a saved twin's sale mix as a hypothetical period of the same length. No order, expense, stock balance, model or snapshot is changed by previewing or running a simulation. The operator supplies assumptions; the engine does not infer demand elasticity, marketing ROI, productivity or a calibrated churn effect.

## Workflow and API

Open **What-If Lab**, select a saved baseline, name the scenario and enter changes. Preview the exact assumptions and methodology. Confirm the hypothetical interpretation, then **Run & save scenario**. Editing inputs invalidates the UI preview. The server additionally requires a matching hash of the canonical parameters, transformation version and immutable baseline hash, preventing a changed request from using an earlier preview confirmation.

All routes use `/api/v1/businesses/{business_id}/simulations`:

| Method | Route | Contract |
| --- | --- | --- |
| POST | `/preview` | ScenarioInput; calculates without persisting a run. |
| POST | `/runs` | Same fields plus `preview_hash` and `assumptions_confirmed: true`; persists an immutable run. |
| GET | `/runs` | Up to 40 projected summaries, newest first. |
| GET | `/runs/{id}` | Verify hash, saved baseline and exact calculation replay. |
| GET | `/compare?left={id}&right={id}` | Compare two verified scenarios sharing the same snapshot. |
| GET | `/runs/{id}/export` | Download CSV containing provenance, assumptions, limitations and outputs. |

All members can read saved runs, compare and export; owners, administrators and analysts may preview/run. Every route verifies tenant membership. Mutations require Origin/CSRF protection. A composite tenant foreign key binds the simulation to its own business's snapshot. Limits: 60 previews and 20 runs per operator/business/hour; 40 retained runs per business. Preview/run use the bounded baseline captured in Phase 6. No new AI/provider configuration or Python/frontend dependency is required.

## Assumptions and formulas

`name` and `baseline_snapshot_id` are required. Percentages and monetary inputs use Decimal. Optional `product_sku` selects the price/demand/customer-loss scope; blank means all products. Optional `supplier_external_id` selects only the unit-cost-change scope; otherwise unit costs follow the product scope. Both references must exist in the saved inputs, regardless of current records.

For each affected paid sale line:

```
price factor = 1 + price_change_pct / 100
demand factor = 1 + demand_change_pct / 100
loss factor = 1 - customer_loss_pct / 100
hypothetical units = round_to_0.001(
  original units × price factor ^ price_elasticity × demand factor × loss factor
)
```

Nonzero price changes require an explicitly supplied `price_elasticity` from −5 to 0. Choosing zero explicitly assumes fixed demand in response to price. Zero-price affected lines reject a nonzero price-change scenario because the price ratio is undefined. Use a product scope or demand-only scenario instead. Price changes are bounded from −90% to +200%; additional demand from −100% to +200%; additional customer loss from 0% to 100%. The loss parameter is a uniform extra reduction in demand, not the model's observed inactivity rate or a causal churn estimate.

Hypothetical line revenue uses the historical unit price multiplied by the price factor, new units, currency rounding and a proportionally scaled discount. Discounts preserve their original relative share and cannot exceed rounded gross line sales. Tax stays excluded. Historical per-line costs are multiplied by the unit-cost factor for the selected product/supplier scope. Applicable unknown nonzero-line costs remain unknown. Aggregate metrics reuse the Phase 3 financial authority.

`marketing_change_pct` changes only paid marketing-category expenses; `employee_cost_change_pct` changes only paid payroll-category expenses. Amounts round per expense. They create no automatic revenue/demand benefit. A percentage change on an absent category has no effect and produces a warning. The payroll assumption changes cost rather than employee headcount or utilization. Other expenses remain unchanged. Operating profit requires complete applicable costs and the exact-period expense coverage saved in the baseline.

### Inventory and replenishment

`replenishment_units` requires a product SKU. Its unit-cost assumption can be entered explicitly, otherwise it uses the product's saved current unit cost. Missing current cost requires an explicit assumption. The engine reports **replenishment cash outlay separately**; it does not subtract the inventory purchase again as operating expense or historical COGS. Supplier cost changes affect historical sale costs; the replenishment quote is a separate explicit/current-cost assumption.

Starting stock is the balance at snapshot capture, independent of the historical reporting-period end. The optional `stock_constrained` flag limits hypothetical sales to this stock plus the supplied incoming units. Allocation is proportional across each product's paid sale lines, rounding down to 0.001 units so allocations never exceed available stock. This can leave small rounding remainders. Planned demand, fulfilled and unfulfilled units, closing stock and additional supply needed are disclosed.

Without stock constraints, revenue assumes sufficient supply; additional required units are reported rather than inventing a purchase order. No delivery timing, intra-period stock arrivals, stockouts by day, branch transfer or purchasing reconciliation is modelled. Inventory constraints/replenishment require the inventory module in the saved baseline.

### Sensitivity and comparison

Up to five explicitly supplied sensitivity elasticities repeat the calculation with only elasticity changed. The UI suggests −0.5, −1 and −2; these are labelled assumptions, not fitted estimates. The selected central assumption remains separate. Best/worst operating profit refers only to these supplied cases, without probability or guaranteed bounds. Missing operating profit remains missing.

All monetary/elasticity arithmetic uses Decimal precision 34 and ROUND_HALF_UP, except bounded stock allocation's ROUND_DOWN. Quantity and monetary range limits reject oversized results. A zero-change unconstrained scenario reproduces baseline financial totals. No future order count or average order value is invented from projected unit demand.

Comparisons use right minus left for scenarios sharing the same baseline. Missing values have no calculated change; zero baselines have no percentage change; gross-margin changes use percentage points. A saved run retains parameters, version, baseline reference/hash, result/hash, creator and timestamp. A PostgreSQL trigger protects captured scenario evidence. Saved reads recalculate from the original snapshot inputs and require identical results. CSV exports include the business, period, capture time, baseline/simulation hashes, demonstration flag, parameters, formulas, caveats, stock and sensitivity outputs. Text metadata is protected against spreadsheet formula prefixes.

## Nexa walkthrough

1. Open **Digital twin** and inspect **[DEMO] Nexa October baseline** (29 September–28 October 2026). Its revenue is ₹150,562 and operating profit ₹42,712. The previous 30-day snapshot is also available for historical comparison.
2. Open **What-If Lab**, select the October baseline and enter a scenario name.
3. Try a **10% price increase**, with elasticity **−1**, leaving product blank to apply it to all products. Preview the suggested sensitivity cases, review and confirm, then save. The engine adjusts units as well as prices.
4. Save another scenario using the same baseline with a different explicit elasticity, then compare their hypothetical totals.
5. For inventory, select SKU **NX-PEN-01**, set incoming units to **20**, and enable the stock constraint. Costs use the saved current product cost unless overridden. Inspect cash outlay, planned/fulfilled demand and remaining supply needs.
6. Download the scenario CSV. The original Overview totals and stock records remain unchanged.

Only saved baselines with paid sale lines can be simulated. Incomplete expense coverage is retained; for example the previous Nexa period does not acquire a fabricated operating profit. These demo results are not real-business predictions. Phase 8 adds the bounded AI analyst separately.
