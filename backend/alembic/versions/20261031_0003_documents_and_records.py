"""Private documents, structured financial records, and field provenance.

Revision ID: 20261031_0003
Revises: 20261031_0002
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261031_0003"
down_revision: str | None = "20261031_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("business_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.Unicode(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "document_type IN ('bank_csv', 'invoice_pdf')", name="ck_documents_type"
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'review_required', 'processed', 'failed')",
            name="ck_documents_status",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_documents_business"),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], name="fk_documents_uploader"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("business_id", "sha256", name="uq_documents_business_hash"),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
    )
    op.create_index("ix_documents_business_created", "documents", ["business_id", "created_at"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("business_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.Unicode(length=120), nullable=True),
        sa.Column("vendor_name", sa.Unicode(length=200), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_invoices_business"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["documents.id"], name="fk_invoices_source_document"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint(
            "business_id", "source_document_id", name="uq_invoices_source_document"
        ),
    )
    op.create_index("ix_invoices_business_number", "invoices", ["business_id", "invoice_number"])

    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("business_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Unicode(length=500), nullable=True),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("external_reference", sa.Unicode(length=200), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.CheckConstraint("source_row_number >= 2", name="ck_transactions_source_row_number"),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"], name="fk_transactions_business"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["documents.id"], name="fk_transactions_source_document"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bank_transactions"),
        sa.UniqueConstraint(
            "business_id",
            "source_document_id",
            "source_row_number",
            name="uq_transactions_document_row",
        ),
    )
    op.create_index(
        "ix_transactions_business_date", "bank_transactions", ["business_id", "transaction_date"]
    )

    op.create_table(
        "field_provenance",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("business_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=24), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("extracted_value", sa.UnicodeText(), nullable=True),
        sa.Column("source_location", sa.Unicode(length=160), nullable=False),
        sa.Column("value_origin", sa.String(length=20), nullable=False),
        sa.Column("verified_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entity_type IN ('invoice', 'bank_transaction')", name="ck_field_provenance_entity"
        ),
        sa.CheckConstraint(
            "value_origin IN ('extracted', 'user_verified', 'system_derived')",
            name="ck_field_provenance_origin",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"], name="fk_field_provenance_business"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["documents.id"], name="fk_field_provenance_source_document"
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"], ["users.id"], name="fk_field_provenance_verifier"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_field_provenance"),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "field_name", name="uq_field_provenance_entity_field"
        ),
    )


def downgrade() -> None:
    op.drop_table("field_provenance")
    op.drop_index("ix_transactions_business_date", table_name="bank_transactions")
    op.drop_table("bank_transactions")
    op.drop_index("ix_invoices_business_number", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_documents_business_created", table_name="documents")
    op.drop_table("documents")
