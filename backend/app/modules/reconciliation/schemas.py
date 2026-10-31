"""Validated request and response contracts for reconciliation workflows."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RunRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=100)


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    status: str
    created_at: datetime


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    run_id: UUID
    transaction_id: UUID | None
    invoice_id: UUID | None
    matching_method: str
    scoring_factors: dict
    confidence_score: Decimal
    status: str
    rationale: str
    amounts_compared: dict
    evidence: dict


class ExceptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    run_id: UUID
    exception_type: str
    transaction_ids: list
    invoice_ids: list
    candidate_id: UUID | None
    summary: str
    status: str


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject|request_information)$")
    reason: str | None = Field(default=None, max_length=2000)


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    exception_id: UUID
    status: str
    report: dict | None
    created_at: datetime


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID
    action: str
    entity_type: str
    entity_id: UUID
    before_state: dict | None
    after_state: dict | None
    reason: str | None
    created_at: datetime


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    candidate_id: UUID | None
    investigation_id: UUID | None
    decision: str
    reason: str | None
    created_at: datetime


class ResolutionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class InvestigationDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject|request_information)$")
    reason: str | None = Field(default=None, max_length=2000)


class AliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    normalized_name: str
    candidate_name: str
    evidence: list
    verified: bool
    created_at: datetime


class InvoiceBalanceRead(BaseModel):
    invoice_id: UUID
    invoice_number: str | None
    vendor_name: str | None
    currency: str | None
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
