"""Tenant-scoped persisted reconciliation, investigation and review history."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UnicodeText,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import MoneyAmount


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        Index("ix_recon_run_business_created", "business_id", "created_at"),
        UniqueConstraint("business_id", "idempotency_key", name="uq_recon_run_idempotency"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    started_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="completed")
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class MatchCandidate(Base):
    __tablename__ = "match_candidates"
    __table_args__ = (
        Index("ix_candidates_business_status", "business_id", "status"),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1", name="ck_candidate_confidence"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[UUID | None] = mapped_column(ForeignKey("bank_transactions.id"))
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id"))
    matching_method: Mapped[str] = mapped_column(String(40), nullable=False)
    scoring_factors: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    rationale: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    amounts_compared: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint("business_id", "transaction_id", name="uq_allocation_transaction"),
        Index("ix_allocations_invoice", "business_id", "invoice_id"),
        CheckConstraint("amount > 0", name="ck_allocation_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(ForeignKey("bank_transactions.id"), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("match_candidates.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MoneyAmount(), nullable=False)
    approved_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class ReconciliationException(Base):
    __tablename__ = "reconciliation_exceptions"
    __table_args__ = (Index("ix_exceptions_business_status", "business_id", "status"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    exception_type: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    invoice_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    candidate_id: Mapped[UUID | None] = mapped_column(ForeignKey("match_candidates.id"))
    summary: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class VendorAliasCandidate(Base):
    __tablename__ = "vendor_alias_candidates"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "normalized_name", "candidate_name", name="uq_vendor_alias_candidate"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False)
    verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (Index("ix_investigations_business_exception", "business_id", "exception_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    exception_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_exceptions.id"), nullable=False
    )
    started_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    report: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class InvestigationToolExecution(Base):
    __tablename__ = "investigation_tool_executions"
    __table_args__ = (Index("ix_tool_exec_investigation", "business_id", "investigation_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    investigation_id: Mapped[UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    record_references: Mapped[list] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        Index("ix_approval_business_candidate", "business_id", "candidate_id"),
        UniqueConstraint("business_id", "review_target_key", name="uq_approval_review_target"),
        CheckConstraint(
            "(candidate_id IS NOT NULL AND investigation_id IS NULL) OR "
            "(candidate_id IS NULL AND investigation_id IS NOT NULL)",
            name="ck_approval_target",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    candidate_id: Mapped[UUID | None] = mapped_column(ForeignKey("match_candidates.id"))
    investigation_id: Mapped[UUID | None] = mapped_column(ForeignKey("investigations.id"))
    review_target_key: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(UnicodeText)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_business_created", "business_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    before_state: Mapped[dict | None] = mapped_column(JSON)
    after_state: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(UnicodeText)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False
    )
