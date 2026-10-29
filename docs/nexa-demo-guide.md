# Explore the Nexa demo

Nexa has been populated at your request with synthetic retail data in INR. The history runs from **2 May to 28 October 2026**. Customer contacts use reserved example addresses; the documents describe demonstration policies only.

## 1. Open your workspace

Open **http://localhost:3000/workspace**, sign in with your existing account, refresh and select **Nexa**. No new account or password is needed.

The workspace contains 84 customers, 3 suppliers, 6 products, 342 orders (522 item rows), 538 inventory movements and 68 expenses. There are also 3 saved evaluated models and 7 searchable documents, including an image-only PDF processed through OCR.

## 2. Check the Overview

Set the reporting dates to **2026-09-29 through 2026-10-28** and apply the date filters.

| Metric | Expected result |
| --- | ---: |
| Revenue | ₹150,562.00 |
| Cost of goods sold | ₹81,550.00 |
| Gross profit | ₹69,012.00 |
| Recorded expenses | ₹26,300.00 |
| Operating profit | ₹42,712.00 |
| Paid orders | 70 |

Expense completeness was confirmed for this particular demo reporting period. Other date ranges can show operating profit as incomplete until their expense coverage is confirmed. Inventory represents the current ledger balance.

## 3. Inspect the source records

In **Data explorer**, switch between customers, suppliers, products, orders, inventory and expenses. Search for product **NX-PEN-01**: its current stock is deliberately eight units.

Inspect orders **NX-PENDING-001** and **NX-REFUNDED-001** using the status filter. They demonstrate orders excluded from paid-sales revenue. The large sales day on **14 October 2026** is an intentional synthetic spike for diagnostic exploration.

## 4. Explore Forecasts & risk

Three evaluated runs are already saved: sales forecast, product demand and customer inactivity. Open them to inspect their results and validation. They were not automatically activated; activation is an explicit choice after review.

Select **Training data → Labelled demonstration records only**. This also selects the demand scope for inventory risk. For the stock-risk example, use SKU **NX-PEN-01**, lead time **7 days**, incoming units **0** and safety stock **0**. The low stock is intended to demonstrate a calculated shortfall. This is a calculation from recorded demand and your assumptions, rather than a guaranteed future event.

If you train another run, use history start **2026-05-02**, observed-through **2026-10-28**, daily aggregation and a seven-period horizon. For product demand use **NX-PEN-01**; for inactivity use a 30-day window. Confirm complete history only for this supplied demo period. Customer inactivity scores are estimates rather than confirmed customer losses.

## 5. Ask questions about the documents

Open **Documents & answers**. All seven labelled demo documents should show ready. Start with the returns-policy document selected as the document scope, then ask:

- “According to the demo policy, how long do customers have to return an item?” — 30 days.
- “What proof is required for a return?” — the original receipt.

Inspect each source citation. Try the delivery-policy document for “How long does delivery take?” — five working days after dispatch. Other samples contain a 14-day invoice payment period, a twelve-month warranty and sample support contacts. The scanned warranty PDF demonstrates OCR and PDF page citations.

Answers use the local Qwen chat and embedding models. Numerical questions about live sales belong in Overview or Forecasts; document answers retrieve the uploaded policy text. The saved two-question evaluation retrieved the expected document for both questions and validated both citations; its literal reference matching was 0.5. Broader answer quality still needs human review.

## 6. Practise importing the raw files

The files are in **datasets/nexa-demo/** and in **datasets/nexa-demo.zip**. Six completed `DEMO-Nexa-…` imports are already recorded in Nexa. You do not need to upload them again to see the demo.

To practise a fresh import, create a separate **retail business using INR** with the relevant modules. In **Import data**, upload, review the mapping and preview, then confirm each file in this order:

1. customers.csv
2. suppliers.csv
3. products.csv
4. inventory.csv
5. orders.csv
6. expenses.csv

Keep `is_demo=true`. Product opening stock is zero because all stock is represented by the supplied movement ledger. That ledger already includes paid-sale deductions; adding another deduction would count them twice. Upload document files separately through **Documents & answers**. Saved model runs and expense-coverage confirmations are specific to the already prepared Nexa workspace; CSV imports alone do not recreate them.

Use a separate business for real data so demonstration records remain easy to identify. This walkthrough stops before Phase 6.

## Start after restarting the laptop

From the project folder run:

```sh
sh scripts/start_local_ai.sh
sh scripts/start_local_ocr.sh
docker compose up -d
```

Then reopen http://localhost:3000/workspace. The first local-model response can take longer while the model loads.
