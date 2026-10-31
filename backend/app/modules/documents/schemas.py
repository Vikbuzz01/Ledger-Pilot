"""Validated document-upload and document-status response schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentType(StrEnum):
    BANK_CSV = "bank_csv"
    INVOICE_PDF = "invoice_pdf"


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    REVIEW_REQUIRED = "review_required"
    PROCESSED = "processed"
    FAILED = "failed"


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    document_type: DocumentType
    original_filename: str
    sha256: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    validation_errors: list[dict[str, str]]
    created_at: datetime
    processed_at: datetime | None


class UploadResult(BaseModel):
    document: DocumentRead
    duplicate: bool


class FieldProvenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: UUID
    field_name: str
    extracted_value: str | None
    source_document_id: UUID
    source_location: str
    value_origin: str
    verified_at: datetime | None


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_number: str | None
    vendor_name: str | None
    invoice_date: date | None
    due_date: date | None
    total_amount: Decimal | None
    currency: str | None
    validation_errors: list[dict[str, str]]


class BankTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_row_number: int
    transaction_date: date | None
    description: str | None
    amount: Decimal | None
    currency: str | None
    external_reference: str | None
    validation_errors: list[dict[str, str]]


class DocumentDetail(BaseModel):
    document: DocumentRead
    invoices: list[InvoiceRead]
    transactions: list[BankTransactionRead]
    provenance: list[FieldProvenanceRead]


class InvoiceVerification(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=120)
    vendor_name: str | None = Field(default=None, max_length=200)
    invoice_date: date | None = None
    due_date: date | None = None
    total_amount: Decimal | None = Field(default=None, max_digits=19, decimal_places=4)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")

    @field_validator("invoice_number", "vendor_name", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class TransactionVerification(BaseModel):
    transaction_date: date | None = None
    description: str | None = Field(default=None, max_length=500)
    amount: Decimal | None = Field(default=None, max_digits=19, decimal_places=4)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")
    external_reference: str | None = Field(default=None, max_length=200)

    @field_validator("description", "external_reference", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value
