"""Runs authorized read-only evidence tools then validates optional provider output."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.models import User
from app.modules.reconciliation.investigation.evaluators import evaluate_report
from app.modules.reconciliation.investigation.provider import configured_provider
from app.modules.reconciliation.investigation.schemas import (
    InvestigationReport,
    ProviderUnavailable,
)
from app.modules.reconciliation.investigation.tools import execute_investigation_tools
from app.modules.reconciliation.models import (
    AuditEvent,
    Investigation,
    InvestigationToolExecution,
    ReconciliationException,
)


def start_investigation(
    db: Session, business_id: UUID, exception_id: UUID, user: User, provider=None
):
    exception = db.scalar(
        select(ReconciliationException).where(
            ReconciliationException.business_id == business_id,
            ReconciliationException.id == exception_id,
        )
    )
    if exception is None:
        raise HTTPException(404, "Exception not found")
    investigation = Investigation(
        business_id=business_id,
        exception_id=exception.id,
        started_by_user_id=user.id,
        status="running",
    )
    db.add(investigation)
    db.flush()
    try:
        provider = provider or configured_provider()
    except ProviderUnavailable as exc:
        investigation.status = "unavailable"
        db.add(
            AuditEvent(
                business_id=business_id,
                actor_user_id=user.id,
                action="investigation_unavailable",
                entity_type="investigation",
                entity_id=investigation.id,
                after_state={"status": "unavailable"},
                reason=str(exc),
            )
        )
        db.commit()
        db.refresh(investigation)
        return investigation
    try:
        context = execute_investigation_tools(db, business_id, investigation.id, exception)
        report = provider.investigate(context)
        validated = evaluate_report(InvestigationReport.model_validate(report), context)
        investigation.report = validated.model_dump(mode="json")
        investigation.status = "completed"
        db.add(
            AuditEvent(
                business_id=business_id,
                actor_user_id=user.id,
                action="investigation_completed",
                entity_type="investigation",
                entity_id=investigation.id,
                after_state={"status": "completed", "exception_id": str(exception.id)},
            )
        )
    except Exception as exc:
        investigation.status = "failed"
        db.add(
            AuditEvent(
                business_id=business_id,
                actor_user_id=user.id,
                action="investigation_failed",
                entity_type="investigation",
                entity_id=investigation.id,
                after_state={"status": "failed"},
                reason=type(exc).__name__,
            )
        )
    db.commit()
    db.refresh(investigation)
    return investigation


def get_investigation(db: Session, business_id: UUID, investigation_id: UUID):
    item = db.scalar(
        select(Investigation).where(
            Investigation.business_id == business_id, Investigation.id == investigation_id
        )
    )
    if item is None:
        raise HTTPException(404, "Investigation not found")
    return item


def tool_history(db: Session, business_id: UUID, investigation_id: UUID):
    item = get_investigation(db, business_id, investigation_id)
    return list(
        db.scalars(
            select(InvestigationToolExecution)
            .where(
                InvestigationToolExecution.business_id == business_id,
                InvestigationToolExecution.investigation_id == item.id,
            )
            .order_by(InvestigationToolExecution.executed_at)
        ).all()
    )
