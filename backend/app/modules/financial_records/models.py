"""SQL Server financial records with exact decimal amounts and field provenance."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Unicode,
    UnicodeText,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "source_document_id",
            "source_row_number",
            name="uq_transactions_document_row",
        ),
        CheckConstraint("source_row_number >= 2", name="ck_transactions_source_row_number"),
        Index("ix_transactions_business_date", "business_id", "transaction_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", name="fk_transactions_business"), nullable=False
    )
    source_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", name="fk_transactions_source_document"), nullable=False
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Unicode(500))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4, asdecimal=True))
    currency: Mapped[str | None] = mapped_column(String(3))
    external_reference: Mapped[str | None] = mapped_column(Unicode(200))
    raw_data: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    validation_errors: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.sysutcdatetime()
    )


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("business_id", "source_document_id", name="uq_invoices_source_document"),
        Index("ix_invoices_business_number", "business_id", "invoice_number"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", name="fk_invoices_business"), nullable=False
    )
    source_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", name="fk_invoices_source_document"), nullable=False
    )
    invoice_number: Mapped[str | None] = mapped_column(Unicode(120))
    vendor_name: Mapped[str | None] = mapped_column(Unicode(200))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4, asdecimal=True))
    currency: Mapped[str | None] = mapped_column(String(3))
    validation_errors: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.sysutcdatetime()
    )


class FieldProvenance(Base):
    __tablename__ = "field_provenance"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id", "field_name", name="uq_field_provenance_entity_field"
        ),
        CheckConstraint(
            "entity_type IN ('invoice', 'bank_transaction')", name="ck_field_provenance_entity"
        ),
        CheckConstraint(
            "value_origin IN ('extracted', 'user_verified', 'system_derived')",
            name="ck_field_provenance_origin",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", name="fk_field_provenance_business"), nullable=False
    )
    source_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", name="fk_field_provenance_source_document"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_value: Mapped[str | None] = mapped_column(UnicodeText)
    source_location: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    value_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", name="fk_field_provenance_verifier")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
