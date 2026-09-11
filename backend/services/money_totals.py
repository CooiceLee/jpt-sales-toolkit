"""Amounts add up only within one currency.

Four deals of 10,000 EUR are 40,000 EUR. Added into one number and printed
under a dollar sign they become forty thousand dollars, which is not a rounding
error or an exchange-rate drift: it is a figure nobody agreed to, sitting where
a decision gets made. Nothing here converts anything - a conversion needs a
rate, a date and a source, and inventing one would be the same mistake wearing
a decimal point.
"""

from __future__ import annotations

# What the interface shows when a record has an amount but nobody said in what
# currency. Kept separate from the currencies people actually chose so the gap
# is visible instead of being folded into one of them.
UNSPECIFIED = "UNSPECIFIED"


def _amount(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def totals_by_currency(
    rows, amount_field: str, currency_field: str = "currency"
) -> dict:
    """Sum one amount per currency, and count what could not be summed.

    Returns the subtotals, how many records carried no amount at all, and how
    many carried an amount with no currency. A reader who can see those two
    counts knows how much of the picture the subtotals cover.
    """
    by_currency: dict[str, float] = {}
    missing_amount = 0
    missing_currency = 0
    for row in rows or []:
        number = _amount(row.get(amount_field))
        if number is None:
            missing_amount += 1
            continue
        code = str(row.get(currency_field) or "").strip().upper()
        if not code:
            missing_currency += 1
            code = UNSPECIFIED
        by_currency[code] = round(by_currency.get(code, 0.0) + number, 2)
    return {
        "by_currency": by_currency,
        "missing_amount": missing_amount,
        "missing_currency": missing_currency,
    }


def merge_totals(left: dict, right: dict) -> dict:
    """One picture from two sets of subtotals, still per currency."""
    by_currency = dict(left.get("by_currency") or {})
    for code, value in (right.get("by_currency") or {}).items():
        by_currency[code] = round(by_currency.get(code, 0.0) + value, 2)
    return {
        "by_currency": by_currency,
        "missing_amount": int(left.get("missing_amount") or 0)
        + int(right.get("missing_amount") or 0),
        "missing_currency": int(left.get("missing_currency") or 0)
        + int(right.get("missing_currency") or 0),
    }


def phrase(by_currency: dict | None) -> str:
    """The subtotals as words, largest first, for a written summary."""
    # A subtotal of zero stays: amounts recorded as zero are a different fact
    # from no amounts at all, and dropping them made the two read the same.
    rows = sorted(
        (by_currency or {}).items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    if not rows:
        return "not recorded"
    return ", ".join(
        f"{value:,.0f} {code}" if code != UNSPECIFIED
        else f"{value:,.0f} with no currency recorded"
        for code, value in rows
    )
