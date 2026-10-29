# Explicit demonstration imports

These reproducible synthetic records are labelled `is_demo=true` and use INR. They are not real business performance or ML training evidence. No dataset is imported automatically.

Choose the folder matching the business profile. In Import data, upload and confirm customers, suppliers, products, inventory (except services), orders, and expenses in that order. Inventory begins with explicit 100-unit restocks before any sale movements. Orders do not auto-adjust inventory.

Report on 2026-10-01 through 2026-10-28. Orders O027 and O028 demonstrate pending and fully refunded exclusions. Services represent commercial invoice lines; project utilization and billable-hour tracking are not implemented. Expense data is illustrative; review the period coverage acknowledgement before confirming it.

For the longer, separate model-workflow demonstration, see [forecasting/README.md](forecasting/README.md). Its explicitly synthetic training and evaluation establish functionality only, not real-business predictive accuracy.
