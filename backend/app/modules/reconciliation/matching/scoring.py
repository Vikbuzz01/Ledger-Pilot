"""Transparent deterministic candidate scoring; no financial value uses float."""

from decimal import Decimal
from difflib import SequenceMatcher

from app.modules.reconciliation.matching.rules import normalize_party


def score_pair(transaction, invoice, verified_aliases=frozenset()) -> tuple[Decimal, dict, str]:
    tx_amount = abs(transaction.amount)
    inv_amount = invoice.total_amount
    factors: dict[str, str | bool | int | None] = {}
    score = Decimal("0")
    if tx_amount == inv_amount:
        factors["amount_relation"] = "exact"
        score += Decimal("0.50")
        factors["amount_exact"] = True
    else:
        factors["amount_relation"] = "partial" if tx_amount < inv_amount else "exceeds"
        factors["amount_exact"] = False
    party = normalize_party(transaction.description)
    vendor = normalize_party(invoice.vendor_name)
    ratio = SequenceMatcher(None, party, vendor).ratio() if party and vendor else 0.0
    factors["counterparty_similarity"] = round(ratio, 4)
    alias_match = (vendor, party) in verified_aliases
    factors["verified_alias"] = alias_match
    if alias_match:
        score += Decimal("0.30")
    elif party and vendor and (party in vendor or vendor in party):
        score += Decimal("0.30")
    elif ratio >= 0.80:
        score += Decimal("0.24")
    elif ratio >= 0.60:
        score += Decimal("0.12")
    exact_ref = bool(
        transaction.external_reference
        and invoice.invoice_number
        and transaction.external_reference.strip().casefold()
        == invoice.invoice_number.strip().casefold()
    )
    factors["reference_exact"] = exact_ref
    if exact_ref:
        score += Decimal("0.15")
    gap = (
        abs((transaction.transaction_date - invoice.invoice_date).days)
        if transaction.transaction_date and invoice.invoice_date
        else None
    )
    factors["date_gap_days"] = gap
    if gap is not None and gap <= 7:
        score += Decimal("0.05")
    currency_ok = transaction.currency == invoice.currency
    factors["currency_compatible"] = currency_ok
    if not currency_ok:
        return (
            Decimal("0"),
            factors,
            "Currency is missing or incompatible; this pair cannot be allocated.",
        )
    if tx_amount < inv_amount:
        rationale = "Transaction amount is below the invoice total; this may be a partial payment."
        score = max(
            score,
            Decimal("0.45")
            if factors["counterparty_similarity"] and ratio >= 0.60
            else Decimal("0"),
        )
    elif tx_amount > inv_amount:
        rationale = (
            "Transaction amount exceeds invoice total; review for mismatch or a combined payment."
        )
    else:
        rationale = (
            "Candidate ranked from amount, counterparty, reference, date, and currency evidence."
        )
    return min(score, Decimal("1")), factors, rationale
