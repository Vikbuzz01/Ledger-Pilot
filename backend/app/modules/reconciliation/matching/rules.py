"""Deterministic normalization and matching rules."""

import re
import unicodedata
from datetime import date
from decimal import Decimal


def normalize_party(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    value = re.sub(r"\b(incorporated|corporation|limited|company|ltd|inc|llc|co)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def amount_value(value: Decimal | None) -> Decimal | None:
    return abs(value) if value is not None else None


def date_gap(left: date | None, right: date | None) -> int | None:
    return abs((left - right).days) if left and right else None
