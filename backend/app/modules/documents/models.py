"""Business-owned document metadata stored in Microsoft SQL Server."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Unicode,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("business_id", "sha256", name="uq_documents_business_hash"),
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        CheckConstraint("document_type IN ('bank_csv', 'invoice_pdf')", name="ck_documents_type"),
        CheckConstraint(
            "status IN ('processing', 'review_required', 'processed', 'failed')",
            name="ck_documents_status",
        ),
        CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
        Index("ix_documents_business_created", "business_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", name="fk_documents_business"), nullable=False
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", name="fk_documents_uploader"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    original_filename: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    validation_errors: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.sysutcdatetime()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
