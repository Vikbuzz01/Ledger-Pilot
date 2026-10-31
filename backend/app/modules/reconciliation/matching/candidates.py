"""Candidate generation independent from scoring and persistence."""

from itertools import combinations

from app.modules.reconciliation.matching.rules import amount_value, normalize_party
from app.modules.reconciliation.matching.scoring import score_pair


def generate_candidates(transactions, invoices, verified_aliases=frozenset()):
    pairs = []
    for tx in transactions:
        for invoice in invoices:
            if not tx.amount or not invoice.total_amount or not tx.currency or not invoice.currency:
                continue
            score, factors, rationale = score_pair(tx, invoice, verified_aliases)
            if score >= 0.35 or factors.get("amount_exact"):
                pairs.append(
                    {
                        "transaction": tx,
                        "invoice": invoice,
                        "score": score,
                        "factors": factors,
                        "rationale": rationale,
                    }
                )
    # Propose splits only when party/currency evidence agrees and sums match exactly.
    for invoice in invoices:
        if not invoice.total_amount or not invoice.currency:
            continue
        possible = [
            tx
            for tx in transactions
            if tx.amount
            and tx.currency == invoice.currency
            and normalize_party(tx.description)
            and normalize_party(invoice.vendor_name)
            and (
                normalize_party(tx.description) in normalize_party(invoice.vendor_name)
                or normalize_party(invoice.vendor_name) in normalize_party(tx.description)
                or (normalize_party(invoice.vendor_name), normalize_party(tx.description))
                in verified_aliases
            )
        ]
        for n in (2, 3, 4):
            for group in combinations(possible, n):
                if (
                    sum((amount_value(tx.amount) for tx in group), start=invoice.total_amount * 0)
                    == invoice.total_amount
                ):
                    pairs.append(
                        {
                            "transaction": None,
                            "transactions": list(group),
                            "invoice": invoice,
                            "score": __import__("decimal").Decimal("0.88"),
                            "factors": {"amount_sum_exact": True, "transaction_count": n},
                            "rationale": (
                                "Multiple same-currency transactions sum exactly to this invoice; "
                                "verify the split before allocation."
                            ),
                        }
                    )
    return pairs
