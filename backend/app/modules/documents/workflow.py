"""Retry-safe synchronous extraction workflow for stored financial documents."""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.documents.extractors.bank_csv import extract_bank_csv
from app.modules.documents.extractors.invoice_pdf import extract_invoice_pdf
from app.modules.documents.models import Document
from app.modules.documents.storage import get_document_path
from app.modules.financial_records.models import BankTransaction, FieldProvenance, Invoice

logger = logging.getLogger(__name__)


def _stringify(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _provenance_rows(
    *,
    business_id: UUID,
    document_id: UUID,
    entity_type: str,
    entity_id: UUID,
    fields: dict,
    locations: dict[str, str],
) -> list[FieldProvenance]:
    return [
        FieldProvenance(
            business_id=business_id,
            source_document_id=document_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            extracted_value=_stringify(value),
            source_location=locations.get(field_name, "source document"),
            value_origin="extracted",
        )
        for field_name, value in fields.items()
    ]


def process_document(db: Session, document: Document) -> Document:
    """Extract once inside a DB transaction; failures remain visible/retryable."""
    try:
        path = get_document_path(document.storage_key)
        content = path.read_bytes()
        if document.document_type == "bank_csv":
            result = extract_bank_csv(content)
            if result.errors:
                document.validation_errors = result.errors
                document.status = "review_required"
                document.processed_at = datetime.now(UTC)
                db.commit()
                db.refresh(document)
                return document

            # Clear only prior unverified extraction from a failed attempt. A successful
            # review state is not reprocessed by the retry endpoint.
            db.execute(
                delete(FieldProvenance).where(FieldProvenance.source_document_id == document.id)
            )
            db.execute(
                delete(BankTransaction).where(BankTransaction.source_document_id == document.id)
            )
            for extracted in result.transactions:
                transaction_id = uuid4()
                fields = extracted["fields"]
                row = BankTransaction(
                    id=transaction_id,
                    business_id=document.business_id,
                    source_document_id=document.id,
                    source_row_number=extracted["source_row_number"],
                    transaction_date=fields["transaction_date"],
                    description=fields["description"],
                    amount=fields["amount"],
                    currency=fields["currency"],
                    external_reference=fields["external_reference"],
                    raw_data=extracted["raw_data"],
                    validation_errors=extracted["errors"],
                )
                db.add(row)
                locations = {name: extracted["source_location"] for name in fields}
                db.add_all(
                    _provenance_rows(
                        business_id=document.business_id,
                        document_id=document.id,
                        entity_type="bank_transaction",
                        entity_id=transaction_id,
                        fields=fields,
                        locations=locations,
                    )
                )
            document.validation_errors = [
                {
                    "code": "human_verification_required",
                    "message": (
                        "Review and verify each extracted transaction before treating it as "
                        "confirmed."
                    ),
                }
            ]
        else:
            result = extract_invoice_pdf(content)
            db.execute(
                delete(FieldProvenance).where(FieldProvenance.source_document_id == document.id)
            )
            db.execute(delete(Invoice).where(Invoice.source_document_id == document.id))
            invoice_id = uuid4()
            invoice = Invoice(
                id=invoice_id,
                business_id=document.business_id,
                source_document_id=document.id,
                **result.fields,
                validation_errors=result.errors,
            )
            db.add(invoice)
            db.add_all(
                _provenance_rows(
                    business_id=document.business_id,
                    document_id=document.id,
                    entity_type="invoice",
                    entity_id=invoice_id,
                    fields=result.fields,
                    locations=result.locations,
                )
            )
            document.validation_errors = [
                {
                    "code": "human_verification_required",
                    "message": (
                        "Review and verify extracted invoice fields before treating them as "
                        "confirmed."
                    ),
                }
            ]

        document.status = "review_required"
        document.processed_at = datetime.now(UTC)
        db.commit()
        db.refresh(document)
        return document
    except Exception:
        db.rollback()
        logger.exception("Document extraction failed for document %s", document.id)
        failed = db.get(Document, document.id)
        if failed is None:
            raise
        failed.status = "failed"
        failed.validation_errors = [
            {
                "code": "processing_failed",
                "message": (
                    "Processing failed. The private source file was retained; retry or upload a "
                    "corrected file."
                ),
            }
        ]
        failed.processed_at = datetime.now(UTC)
        db.commit()
        db.refresh(failed)
        return failed
