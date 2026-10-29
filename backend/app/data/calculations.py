"""Monetary authority for Phase 3. Decimal only; no model or UI arithmetic."""
from decimal import Decimal, ROUND_HALF_UP

CURRENCY_DIGITS = {"INR": 2, "USD": 2, "EUR": 2, "GBP": 2, "AUD": 2, "CAD": 2, "SGD": 2, "AED": 2, "JPY": 0, "BHD": 3, "KWD": 3}
ZERO = Decimal(0)


def money(value: Decimal, currency: str) -> Decimal:
    if currency not in CURRENCY_DIGITS:
        raise ValueError("Financial calculations require a supported currency: " + ", ".join(CURRENCY_DIGITS))
    return value.quantize(Decimal(1).scaleb(-CURRENCY_DIGITS[currency]), rounding=ROUND_HALF_UP)


def line_amounts(quantity: Decimal, price: Decimal, cost: Decimal | None, discount: Decimal, tax: Decimal, currency: str) -> tuple[Decimal, Decimal | None, Decimal]:
    if quantity <= 0 or min(price, discount, tax) < 0 or (cost is not None and cost < 0):
        raise ValueError("Quantities must be positive and monetary inputs nonnegative")
    if money(discount, currency) != discount or money(tax, currency) != tax:
        raise ValueError("Discount and tax must use the currency's minor-unit precision")
    revenue = money(quantity * price, currency) - discount
    if revenue < 0:
        raise ValueError("Discount cannot exceed the line sale amount")
    cogs = money(quantity * cost, currency) if cost is not None else None
    if max(revenue + tax, cogs or ZERO) > Decimal("99999999999999.9999"):
        raise ValueError("Line amount exceeds the supported monetary range")
    return revenue, cogs, revenue + tax


def financial_summary(lines: list[tuple[Decimal, Decimal | None]], expenses: list[Decimal], order_count: int, currency: str, expenses_complete: bool) -> dict:
    revenue = money(sum((line[0] for line in lines), ZERO), currency)
    cogs = money(sum((line[1] for line in lines), ZERO), currency) if all(line[1] is not None for line in lines) else None
    gross = revenue - cogs if cogs is not None else None
    recorded_expenses = money(sum(expenses, ZERO), currency)
    return {
        "revenue": revenue, "cogs": cogs, "gross_profit": gross,
        "gross_margin_pct": (gross / revenue * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if gross is not None and revenue else None,
        "recorded_expenses": recorded_expenses,
        "operating_profit": gross - recorded_expenses if gross is not None and expenses_complete else None,
        "average_order_value": money(revenue / order_count, currency) if order_count else None,
        "paid_orders": order_count,
    }
