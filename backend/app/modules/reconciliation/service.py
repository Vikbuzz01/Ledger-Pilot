"""Tenant-scoped reconciliation generation and human-confirmed allocation."""

from decimal import Decimal
from difflib import SequenceMatcher
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.documents.models import Document
from app.modules.financial_records.models import BankTransaction, Invoice
from app.modules.identity.models import User
from app.modules.reconciliation.matching.candidates import generate_candidates
from app.modules.reconciliation.matching.rules import normalize_party
from app.modules.reconciliation.models import (
    ApprovalDecision,
    AuditEvent,
    Investigation,
    MatchCandidate,
    PaymentAllocation,
    ReconciliationException,
    ReconciliationRun,
    VendorAliasCandidate,
)


def _exception(
    db, business_id, run_id, kind, summary, tx_ids=None, inv_ids=None, candidate_id=None
):
    item = ReconciliationException(
        business_id=business_id,
        run_id=run_id,
        exception_type=kind,
        transaction_ids=[str(x) for x in (tx_ids or [])],
        invoice_ids=[str(x) for x in (inv_ids or [])],
        candidate_id=candidate_id,
        summary=summary,
    )
    db.add(item)
    return item


def _verified_records(db: Session, business_id: UUID):
    docs = select(Document.id).where(
        Document.business_id == business_id, Document.status == "processed"
    )
    txs = list(
        db.scalars(
            select(BankTransaction).where(
                BankTransaction.business_id == business_id,
                BankTransaction.source_document_id.in_(docs),
                BankTransaction.amount.is_not(None),
                BankTransaction.currency.is_not(None),
            )
        ).all()
    )
    invoices = list(
        db.scalars(
            select(Invoice).where(
                Invoice.business_id == business_id,
                Invoice.source_document_id.in_(docs),
                Invoice.total_amount.is_not(None),
                Invoice.currency.is_not(None),
            )
        ).all()
    )
    return txs, invoices


def start_run(db: Session, business_id: UUID, user: User, idempotency_key: str | None):
    key = idempotency_key or str(uuid4())
    prior = db.scalar(
        select(ReconciliationRun).where(
            ReconciliationRun.business_id == business_id,
            ReconciliationRun.idempotency_key == key,
        )
    )
    if prior:
        return prior
    run = ReconciliationRun(
        business_id=business_id,
        started_by_user_id=user.id,
        idempotency_key=key,
        status="processing",
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        prior = db.scalar(
            select(ReconciliationRun).where(
                ReconciliationRun.business_id == business_id,
                ReconciliationRun.idempotency_key == key,
            )
        )
        if prior is not None:
            return prior
        raise HTTPException(409, "A reconciliation run conflicts with existing records") from None
    txs, invoices = _verified_records(db, business_id)
    for tx in txs:
        for invoice in invoices:
            if (
                tx.currency != invoice.currency
                and abs(tx.amount) == invoice.total_amount
                and SequenceMatcher(
                    None, normalize_party(tx.description), normalize_party(invoice.vendor_name)
                ).ratio()
                >= 0.60
            ):
                _exception(
                    db,
                    business_id,
                    run.id,
                    "currency_mismatch",
                    "Amount and counterparty appear related, but currencies are incompatible.",
                    [tx.id],
                    [invoice.id],
                )
    verified_aliases = {
        (row.normalized_name, normalize_party(row.candidate_name))
        for row in db.scalars(
            select(VendorAliasCandidate).where(
                VendorAliasCandidate.business_id == business_id,
                VendorAliasCandidate.verified == 1,
            )
        ).all()
    }
    pairs = generate_candidates(txs, invoices, verified_aliases)
    tx_candidates: dict[UUID, list[dict]] = {}
    inv_candidates: dict[UUID, list[dict]] = {}
    used_tx_ids: set[UUID] = set()
    used_inv_ids: set[UUID] = set()
    for pair in pairs:
        tx = pair.get("transaction")
        group = pair.get("transactions", [tx] if tx else [])
        invoice = pair["invoice"]
        relation = pair["factors"].get("amount_relation", "exact")
        method = (
            "split_payment"
            if len(group) > 1
            else {
                "exact": "exact_amount",
                "partial": "partial_payment",
                "exceeds": "amount_mismatch",
            }.get(relation, "candidate")
        )
        item = MatchCandidate(
            business_id=business_id,
            run_id=run.id,
            transaction_id=tx.id if tx else None,
            invoice_id=invoice.id,
            matching_method=method,
            scoring_factors=pair["factors"],
            confidence_score=pair["score"],
            status="proposed",
            rationale=pair["rationale"],
            amounts_compared={
                "transactions": [str(abs(t.amount)) for t in group],
                "invoice": str(invoice.total_amount),
                "currency": invoice.currency,
            },
            evidence={
                "transaction_ids": [str(t.id) for t in group],
                "invoice_id": str(invoice.id),
                "transaction_sources": [str(t.source_document_id) for t in group],
                "invoice_source": str(invoice.source_document_id),
                "invoice_reference": invoice.invoice_number,
                "invoice_vendor": invoice.vendor_name,
                "transaction_references": [t.external_reference for t in group],
                "transaction_descriptions": [t.description for t in group],
            },
        )
        db.add(item)
        for t in group:
            tx_candidates.setdefault(t.id, []).append({"pair": pair, "candidate": item})
        inv_candidates.setdefault(invoice.id, []).append({"pair": pair, "candidate": item})
        if item.confidence_score >= Decimal("0.75"):
            used_tx_ids.update(t.id for t in group)
            used_inv_ids.add(invoice.id)
        if (
            pair["factors"].get("amount_exact")
            and pair["factors"].get("counterparty_similarity", 0) < 0.45
        ):
            _exception(
                db,
                business_id,
                run.id,
                "conflicting_counterparty",
                "Amount matches, but counterparty identity evidence conflicts.",
                [t.id for t in group],
                [invoice.id],
                item.id,
            )
        if (
            pair["factors"].get("date_gap_days") is not None
            and pair["factors"]["date_gap_days"] > 7
        ):
            _exception(
                db,
                business_id,
                run.id,
                "date_discrepancy",
                "Transaction and invoice dates differ by more than seven days.",
                [t.id for t in group],
                [invoice.id],
                item.id,
            )
        if pair["factors"].get("amount_relation") == "exceeds" and len(group) == 1:
            _exception(
                db,
                business_id,
                run.id,
                "amount_mismatch",
                pair["rationale"],
                [group[0].id],
                [invoice.id],
                item.id,
            )
        if pair["factors"].get("amount_relation") == "partial" and len(group) == 1:
            _exception(
                db,
                business_id,
                run.id,
                "partial_payment",
                pair["rationale"],
                [group[0].id],
                [invoice.id],
                item.id,
            )
        if len(group) > 1:
            _exception(
                db,
                business_id,
                run.id,
                "split_payment",
                pair["rationale"],
                [t.id for t in group],
                [invoice.id],
                item.id,
            )

    alias_seen = set()
    for tx in txs:
        if tx.id not in tx_candidates:
            _exception(
                db,
                business_id,
                run.id,
                "unmatched_transaction",
                "No verified invoice candidate was found.",
                [tx.id],
            )
        # Retain a possible vendor alias, explicitly unverified.
        normalized = normalize_party(tx.description)
        for invoice in invoices:
            other = normalize_party(invoice.vendor_name)
            ratio = SequenceMatcher(None, normalized, other).ratio() if normalized and other else 0
            if normalized != other and ratio >= 0.65:
                alias_key = (other, tx.description or "")
                if alias_key in alias_seen:
                    continue
                alias_seen.add(alias_key)
                alias = db.scalar(
                    select(VendorAliasCandidate).where(
                        VendorAliasCandidate.business_id == business_id,
                        VendorAliasCandidate.normalized_name == other,
                        VendorAliasCandidate.candidate_name == (tx.description or ""),
                    )
                )
                if alias is None:
                    db.add(
                        VendorAliasCandidate(
                            business_id=business_id,
                            normalized_name=other,
                            candidate_name=tx.description or "",
                            evidence=[
                                {
                                    "transaction_id": str(tx.id),
                                    "invoice_id": str(invoice.id),
                                    "similarity": round(ratio, 3),
                                }
                            ],
                        )
                    )

    for invoice in invoices:
        if invoice.id not in inv_candidates:
            _exception(
                db,
                business_id,
                run.id,
                "missing_invoice",
                "No verified bank transaction candidate was found for this invoice.",
                inv_ids=[invoice.id],
            )

    # Duplicate detection preserves all source rows and only raises review exceptions.
    for i, left in enumerate(txs):
        for right in txs[i + 1 :]:
            same_identity = normalize_party(left.description) == normalize_party(
                right.description
            ) or (
                left.external_reference is not None
                and right.external_reference is not None
                and left.external_reference.casefold() == right.external_reference.casefold()
            )
            same = (
                same_identity
                and left.transaction_date == right.transaction_date
                and abs(left.amount) == abs(right.amount)
                and left.currency == right.currency
            )
            if same:
                _exception(
                    db,
                    business_id,
                    run.id,
                    "duplicate_transaction",
                    "Transactions share date, amount, currency, and reference; "
                    "review for duplication.",
                    [left.id, right.id],
                )
    for i, left in enumerate(invoices):
        for right in invoices[i + 1 :]:
            same_identity = normalize_party(left.vendor_name) == normalize_party(right.vendor_name)
            same_amount_date = (
                left.invoice_date == right.invoice_date and left.total_amount == right.total_amount
            )
            near_number = bool(
                left.invoice_number
                and right.invoice_number
                and SequenceMatcher(
                    None, left.invoice_number.casefold(), right.invoice_number.casefold()
                ).ratio()
                >= 0.85
            )
            if (same_identity and same_amount_date) or (same_identity and near_number):
                _exception(
                    db,
                    business_id,
                    run.id,
                    "duplicate_invoice",
                    "Invoices have similar supplier, date, or reference; no record was removed.",
                    inv_ids=[left.id, right.id],
                )
    run.status = "completed"
    db.add(
        AuditEvent(
            business_id=business_id,
            actor_user_id=user.id,
            action="reconciliation_run_completed",
            entity_type="reconciliation_run",
            entity_id=run.id,
            after_state={"candidate_count": len(pairs)},
        )
    )
    db.commit()
    db.refresh(run)
    return run


def list_run_rows(db: Session, model, business_id: UUID, run_id: UUID):
    run = db.scalar(
        select(ReconciliationRun).where(
            ReconciliationRun.id == run_id, ReconciliationRun.business_id == business_id
        )
    )
    if run is None:
        raise HTTPException(404, "Reconciliation run not found")
    return list(
        db.scalars(
            select(model).where(model.business_id == business_id, model.run_id == run_id)
        ).all()
    )


def decide_candidate(
    db: Session,
    business_id: UUID,
    candidate_id: UUID,
    user: User,
    decision: str,
    reason: str | None,
):
    candidate = db.scalar(
        select(MatchCandidate).where(
            MatchCandidate.id == candidate_id, MatchCandidate.business_id == business_id
        )
    )
    if candidate is None:
        raise HTTPException(404, "Match candidate not found")
    if candidate.status != "proposed":
        raise HTTPException(409, "Only proposed candidates can be reviewed")
    if db.scalar(
        select(ApprovalDecision).where(
            ApprovalDecision.business_id == business_id,
            ApprovalDecision.candidate_id == candidate_id,
        )
    ):
        raise HTTPException(409, "This proposal already has a review decision")
    before = {"status": candidate.status}
    if decision == "approve":
        if not candidate.invoice_id:
            raise HTTPException(422, "Candidate is missing its invoice reference")
        invoice = db.scalar(
            select(Invoice)
            .where(Invoice.id == candidate.invoice_id, Invoice.business_id == business_id)
            .with_for_update()
            .with_hint(Invoice, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        )
        if invoice is None or not invoice.total_amount:
            raise HTTPException(409, "Invoice is unavailable for allocation")
        tx_ids = [UUID(value) for value in candidate.evidence.get("transaction_ids", [])]
        txs = list(
            db.scalars(
                select(BankTransaction).where(
                    BankTransaction.business_id == business_id,
                    BankTransaction.id.in_(tx_ids),
                    BankTransaction.currency == invoice.currency,
                )
            ).all()
        )
        if len(txs) != len(tx_ids) or not txs:
            raise HTTPException(409, "Candidate transaction evidence is unavailable")
        source_ids = {invoice.source_document_id, *(tx.source_document_id for tx in txs)}
        verified_sources = set(
            db.scalars(
                select(Document.id).where(
                    Document.business_id == business_id,
                    Document.status == "processed",
                    Document.id.in_(source_ids),
                )
            ).all()
        )
        if verified_sources != source_ids:
            raise HTTPException(409, "Candidate includes records that are no longer verified")
        if any(not tx.amount for tx in txs):
            raise HTTPException(409, "Candidate transaction has no verified amount")
        already = sum(
            db.scalars(
                select(PaymentAllocation.amount).where(
                    PaymentAllocation.business_id == business_id,
                    PaymentAllocation.invoice_id == invoice.id,
                )
            ).all(),
            Decimal("0"),
        )
        proposed_total = sum((abs(tx.amount) for tx in txs), Decimal("0"))
        if already + proposed_total > invoice.total_amount:
            raise HTTPException(409, "Approval would over-allocate the invoice")
        for tx in txs:
            if db.scalar(
                select(PaymentAllocation.id).where(
                    PaymentAllocation.business_id == business_id,
                    PaymentAllocation.transaction_id == tx.id,
                )
            ):
                raise HTTPException(409, "A transaction has already been allocated")
            db.add(
                PaymentAllocation(
                    business_id=business_id,
                    transaction_id=tx.id,
                    invoice_id=invoice.id,
                    candidate_id=candidate.id,
                    amount=abs(tx.amount),
                    approved_by_user_id=user.id,
                )
            )
        candidate.status = "approved"
        consumed_tx_ids = {tx.id for tx in txs}
        invoice_settled = already + proposed_total == invoice.total_amount
        alternatives = db.scalars(
            select(MatchCandidate).where(
                MatchCandidate.business_id == business_id,
                MatchCandidate.status == "proposed",
                MatchCandidate.id != candidate.id,
            )
        ).all()
        for alternative in alternatives:
            alternative_tx_ids = {
                UUID(value) for value in alternative.evidence.get("transaction_ids", [])
            }
            if consumed_tx_ids.intersection(alternative_tx_ids) or (
                invoice_settled and alternative.invoice_id == invoice.id
            ):
                alternative.status = "superseded"
        if invoice_settled:
            open_exceptions = db.scalars(
                select(ReconciliationException).where(
                    ReconciliationException.business_id == business_id,
                    ReconciliationException.status == "open",
                    ReconciliationException.exception_type.in_(
                        ["partial_payment", "split_payment"]
                    ),
                )
            ).all()
            for exception in open_exceptions:
                if str(invoice.id) in exception.invoice_ids:
                    exception.status = "resolved"
    else:
        candidate.status = "rejected" if decision == "reject" else "information_requested"
    decision_row = ApprovalDecision(
        business_id=business_id,
        candidate_id=candidate.id,
        review_target_key=f"candidate:{candidate.id}",
        reviewer_user_id=user.id,
        decision=decision,
        reason=reason,
    )
    db.add(decision_row)
    db.add(
        AuditEvent(
            business_id=business_id,
            actor_user_id=user.id,
            action=decision,
            entity_type="match_candidate",
            entity_id=candidate.id,
            before_state=before,
            after_state={"status": candidate.status},
            reason=reason,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Review conflicts with an existing decision or allocation"
        ) from None
    db.refresh(candidate)
    return candidate


def review_investigation(
    db: Session,
    business_id: UUID,
    investigation_id: UUID,
    user: User,
    decision: str,
    reason: str | None,
):
    investigation = db.scalar(
        select(Investigation).where(
            Investigation.id == investigation_id,
            Investigation.business_id == business_id,
        )
    )
    if investigation is None:
        raise HTTPException(404, "Investigation not found")
    target_key = f"investigation:{investigation.id}"
    if db.scalar(
        select(ApprovalDecision.id).where(
            ApprovalDecision.business_id == business_id,
            ApprovalDecision.review_target_key == target_key,
        )
    ):
        raise HTTPException(409, "This investigation recommendation already has a decision")
    if investigation.status != "completed" or not investigation.report:
        raise HTTPException(409, "There is no completed recommendation to review")
    row = ApprovalDecision(
        business_id=business_id,
        investigation_id=investigation.id,
        review_target_key=target_key,
        reviewer_user_id=user.id,
        decision=decision,
        reason=reason,
    )
    db.add(row)
    db.add(
        AuditEvent(
            business_id=business_id,
            actor_user_id=user.id,
            action=f"ai_recommendation_{decision}",
            entity_type="investigation",
            entity_id=investigation.id,
            after_state={"decision": decision},
            reason=reason,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Investigation recommendation already has a decision") from None
    db.refresh(row)
    return row
