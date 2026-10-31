"""Shared conservative parsers for dates, currency codes, and decimal amounts."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_AMOUNT_PATTERN = re.compile(r"^-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,4})?$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_SUPPORTED_CURRENCIES = {"USD", "CAD", "AUD", "EUR", "GBP", "INR", "JPY", "CHF"}


def parse_amount(value: str | None) -> Decimal | None:
    if value is None:
        return None
    raw = value.strip()
    negative_parentheses = raw.startswith("(") and raw.endswith(")")
    if negative_parentheses:
        raw = raw[1:-1].strip()
    # Strip only common display symbols. A comma is accepted only as a 3-digit
    # thousands separator, preventing a locale decimal comma from becoming x100.
    raw = re.sub(r"^(?:USD|CAD|AUD|EUR|GBP|INR|JPY|CHF)\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"[$€£₹\s]", "", raw)
    if not _AMOUNT_PATTERN.fullmatch(raw):
        return None
    try:
        result = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    if negative_parentheses:
        result = -result
    if result.adjusted() > 14 or result.as_tuple().exponent < -4:
        return None
    return result


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
        if parsed.isoformat() == raw:
            return parsed
    except ValueError:
        pass
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if match:
        first, second, year = map(int, match.groups())
        if first <= 12 and second <= 12:
            return None  # Month/day order cannot be established from the source.
        month, day = (first, second) if first <= 12 else (second, first)
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def parse_currency(value: str | None) -> str | None:
    if value is None:
        return None
    currency = value.strip().upper()
    return (
        currency
        if _CURRENCY_PATTERN.fullmatch(currency) and currency in _SUPPORTED_CURRENCIES
        else None
    )
