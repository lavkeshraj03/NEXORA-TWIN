# Explicit Nexa demonstration data

Synthetic only. Generated for 2026-05-02 through 2026-10-28; reporting example 2026-09-29 through 2026-10-28. All operational rows carry is_demo=true. No real customer/supplier contact data is included.

These files were explicitly requested and loaded into the empty Nexa workspace. To practise a fresh import, create a separate retail demo business (INR) and confirm customers, suppliers, products, inventory, orders, then expenses in that order. Inventory entries already reconcile the paid sales; do not add a second stock deduction for the same sale.

There are 342 orders and 522 order-item rows. Pending and fully refunded examples are excluded from dashboard revenue. Stock for NX-PEN-01 intentionally finishes at eight units to demonstrate calculated shortfall. The synthetic sales spike is a diagnostic example, not a real incident.

For Forecasts & risk select Labelled demonstration records only. Raw document samples live in documents/. See docs/nexa-demo-guide.md for the walkthrough.
