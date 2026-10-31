"""Authorized reconciliation, exception, investigation, approval, and audit APIs."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.modules.documents.models import Document
from app.modules.financial_records.models import BankTransaction, Invoice
from app.modules.identity.dependencies import CurrentUser, DbSession, require_business_membership
from app.modules.reconciliation.investigation.workflow import (
    get_investigation,
    start_investigation,
    tool_history,
)
from app.modules.reconciliation.models import (
    AuditEvent,
    Investigation,
    MatchCandidate,
    PaymentAllocation,
    ReconciliationException,
    ReconciliationRun,
    VendorAliasCandidate,
)
from app.modules.reconciliation.schemas import (
    AliasRead,
    ApprovalRead,
    AuditRead,
    CandidateRead,
    DecisionRequest,
    ExceptionRead,
    InvestigationDecisionRequest,
    InvestigationRead,
    InvoiceBalanceRead,
    ResolutionRequest,
    RunRead,
    RunRequest,
)
from app.modules.reconciliation.service import (
    decide_candidate,
    list_run_rows,
    review_investigation,
    start_run,
)

router = APIRouter(
    prefix="/api/v1/businesses/{business_id}/reconciliation", tags=["reconciliation"]
)
READ = {"owner", "admin", "member", "viewer"}
WRITE = {"owner", "admin", "member"}


@router.post("/runs", response_model=RunRead, status_code=201)
def create_run(business_id: UUID, data: RunRequest, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, WRITE)
    return start_run(db, business_id, user, data.idempotency_key)


@router.get("/runs", response_model=list[RunRead])
def runs(business_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    return list(
        db.scalars(
            select(ReconciliationRun)
            .where(ReconciliationRun.business_id == business_id)
            .order_by(ReconciliationRun.created_at.desc())
        ).all()
    )


@router.get("/runs/{run_id}/candidates", response_model=list[CandidateRead])
def candidates(business_id: UUID, run_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    return list_run_rows(db, MatchCandidate, business_id, run_id)


@router.get("/runs/{run_id}/exceptions", response_model=list[ExceptionRead])
def run_exceptions(business_id: UUID, run_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    return list_run_rows(db, ReconciliationException, business_id, run_id)


@router.get("/exceptions", response_model=list[ExceptionRead])
def exceptions(business_id: UUID, db: DbSession, user: CurrentUser, status: str | None = None):
    require_business_membership(business_id, db, user, READ)
    query = select(ReconciliationException).where(
        ReconciliationException.business_id == business_id
    )
    if status:
        query = query.where(ReconciliationException.status == status)
    return list(db.scalars(query.order_by(ReconciliationException.created_at.desc())).all())


@router.post("/candidates/{candidate_id}/decision", response_model=CandidateRead)
def candidate_decision(
    business_id: UUID, candidate_id: UUID, data: DecisionRequest, db: DbSession, user: CurrentUser
):
    require_business_membership(business_id, db, user, WRITE)
    return decide_candidate(db, business_id, candidate_id, user, data.decision, data.reason)


@router.post(
    "/exceptions/{exception_id}/investigations", response_model=InvestigationRead, status_code=201
)
def investigate(business_id: UUID, exception_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, WRITE)
    return start_investigation(db, business_id, exception_id, user)


@router.get("/investigations/{investigation_id}", response_model=InvestigationRead)
def investigation(business_id: UUID, investigation_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    return get_investigation(db, business_id, investigation_id)


@router.get("/investigations/{investigation_id}/tools")
def investigation_tools(
    business_id: UUID, investigation_id: UUID, db: DbSession, user: CurrentUser
):
    require_business_membership(business_id, db, user, READ)
    return tool_history(db, business_id, investigation_id)


@router.post("/exceptions/{exception_id}/resolve", response_model=ExceptionRead)
def resolve_exception(
    business_id: UUID, exception_id: UUID, data: ResolutionRequest, db: DbSession, user: CurrentUser
):
    require_business_membership(business_id, db, user, WRITE)
    item = db.scalar(
        select(ReconciliationException).where(
            ReconciliationException.business_id == business_id,
            ReconciliationException.id == exception_id,
        )
    )
    if item is None:
        raise HTTPException(404, "Exception not found")
    if item.status == "resolved":
        raise HTTPException(409, "Exception is already resolved")
    before = {"status": item.status}
    item.status = "resolved"
    db.add(
        AuditEvent(
            business_id=business_id,
            actor_user_id=user.id,
            action="manual_exception_resolution",
            entity_type="reconciliation_exception",
            entity_id=item.id,
            before_state=before,
            after_state={"status": item.status},
            reason=data.reason,
        )
    )
    db.commit()
    db.refresh(item)
    return item


@router.post("/investigations/{investigation_id}/decision", response_model=ApprovalRead)
def investigation_decision(
    business_id: UUID,
    investigation_id: UUID,
    data: InvestigationDecisionRequest,
    db: DbSession,
    user: CurrentUser,
):
    require_business_membership(business_id, db, user, WRITE)
    return review_investigation(db, business_id, investigation_id, user, data.decision, data.reason)


@router.get("/audit", response_model=list[AuditRead])
def audit_history(business_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.business_id == business_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(500)
        ).all()
    )


@router.get("/invoice-balances", response_model=list[InvoiceBalanceRead])
def invoice_balances(business_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.business_id == business_id)
        .order_by(Invoice.invoice_date.desc())
    ).all()
    result = []
    for invoice in invoices:
        paid = sum(
            db.scalars(
                select(PaymentAllocation.amount).where(
                    PaymentAllocation.business_id == business_id,
                    PaymentAllocation.invoice_id == invoice.id,
                )
            ).all(),
            Decimal("0"),
        )
        total = invoice.total_amount or Decimal("0")
        result.append(
            {
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "vendor_name": invoice.vendor_name,
                "currency": invoice.currency,
                "total_amount": total,
                "paid_amount": paid,
                "outstanding_amount": max(total - paid, Decimal("0")),
            }
        )
    return result


@router.get("/aliases", response_model=list[AliasRead])
def aliases(business_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    return list(
        db.scalars(
            select(VendorAliasCandidate)
            .where(VendorAliasCandidate.business_id == business_id)
            .order_by(VendorAliasCandidate.created_at.desc())
        ).all()
    )


@router.post("/aliases/{alias_id}/verify", response_model=AliasRead)
def verify_alias(business_id: UUID, alias_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, {"owner", "admin"})
    item = db.scalar(
        select(VendorAliasCandidate).where(
            VendorAliasCandidate.business_id == business_id,
            VendorAliasCandidate.id == alias_id,
        )
    )
    if item is None:
        raise HTTPException(404, "Vendor alias candidate not found")
    if item.verified:
        raise HTTPException(409, "Alias candidate is already verified")
    before = {"verified": item.verified}
    item.verified = True
    db.add(
        AuditEvent(
            business_id=business_id,
            actor_user_id=user.id,
            action="vendor_alias_verified",
            entity_type="vendor_alias_candidate",
            entity_id=item.id,
            before_state=before,
            after_state={"verified": True},
        )
    )
    db.commit()
    db.refresh(item)
    return item


@router.get("/summary")
def summary(business_id: UUID, db: DbSession, user: CurrentUser):
    require_business_membership(business_id, db, user, READ)
    total_transactions = (
        db.scalar(
            select(func.count(BankTransaction.id))
            .join(Document, Document.id == BankTransaction.source_document_id)
            .where(BankTransaction.business_id == business_id, Document.status == "processed")
        )
        or 0
    )
    matched_transactions = (
        db.scalar(
            select(func.count(PaymentAllocation.id)).where(
                PaymentAllocation.business_id == business_id
            )
        )
        or 0
    )
    in_progress = (
        db.scalar(
            select(func.count(Investigation.id)).where(
                Investigation.business_id == business_id, Investigation.status == "running"
            )
        )
        or 0
    )
    run = db.scalar(
        select(ReconciliationRun)
        .where(ReconciliationRun.business_id == business_id)
        .order_by(ReconciliationRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        return {
            "run_id": None,
            "candidates": 0,
            "approved": 0,
            "exceptions": 0,
            "pending_approvals": 0,
            "total_transactions": total_transactions,
            "matched_transactions": matched_transactions,
            "unmatched_transactions": max(total_transactions - matched_transactions, 0),
            "reconciliation_progress_percent": round(
                matched_transactions * 100 / total_transactions, 1
            )
            if total_transactions
            else 0,
            "investigations_in_progress": in_progress,
            "invoices": db.scalar(
                select(func.count(Invoice.id)).where(Invoice.business_id == business_id)
            )
            or 0,
        }
    candidate_rows = list_run_rows(db, MatchCandidate, business_id, run.id)
    exception_rows = list_run_rows(db, ReconciliationException, business_id, run.id)
    return {
        "run_id": str(run.id),
        "candidates": len(candidate_rows),
        "approved": sum(row.status == "approved" for row in candidate_rows),
        "exceptions": sum(row.status == "open" for row in exception_rows),
        "pending_approvals": sum(row.status == "proposed" for row in candidate_rows),
        "total_transactions": total_transactions,
        "matched_transactions": matched_transactions,
        "unmatched_transactions": max(total_transactions - matched_transactions, 0),
        "reconciliation_progress_percent": round(matched_transactions * 100 / total_transactions, 1)
        if total_transactions
        else 0,
        "investigations_in_progress": in_progress,
        "invoices": db.scalar(
            select(func.count(Invoice.id)).where(Invoice.business_id == business_id)
        )
        or 0,
    }
