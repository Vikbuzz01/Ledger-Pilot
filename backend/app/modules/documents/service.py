"""Upload, access, retry, and user-validation services for private documents."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.documents.models import Document
from app.modules.documents.schemas import DocumentType, InvoiceVerification, TransactionVerification
from app.modules.documents.storage import save_document
from app.modules.documents.workflow import process_document
from app.modules.financial_records.models import BankTransaction, FieldProvenance, Invoice
from app.modules.identity.models import User


def _safe_filename(filename: str | None) -> str:
    value = (filename or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    value = "".join(char for char in value if char.isprintable()).strip()
    return value[:255] or "upload"


def _validate_upload(document_type: DocumentType, filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.casefold()
    if document_type == DocumentType.BANK_CSV:
        if extension != ".csv":
            raise HTTPException(
                status_code=415, detail="Bank statement uploads must use a .csv file"
            )
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=415, detail="CSV must be UTF-8 encoded") from None
        if b"\x00" in content:
            raise HTTPException(status_code=415, detail="CSV contains invalid binary data")
        return "text/csv"
    if extension != ".pdf" or b"%PDF-" not in content[:1024]:
        raise HTTPException(status_code=415, detail="Invoice uploads must be valid PDF files")
    return "application/pdf"


def upload_document(
    db: Session,
    business_id: UUID,
    user: User,
    document_type: DocumentType,
    filename: str | None,
    content: bytes,
) -> tuple[Document, bool]:
    settings = get_settings()
    max_bytes = settings.max_document_upload_mb * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the configured {settings.max_document_upload_mb} MiB limit",
        )

    original_filename = _safe_filename(filename)
    content_type = _validate_upload(document_type, original_filename, content)
    file_hash = hashlib.sha256(content).hexdigest()
    existing = db.scalar(
        select(Document).where(
            Document.business_id == business_id,
            Document.sha256 == file_hash,
        )
    )
    if existing is not None:
        return existing, True

    document_id = uuid4()
    suffix = ".csv" if document_type == DocumentType.BANK_CSV else ".pdf"
    storage_key = f"{business_id}/{document_id}{suffix}"
    document = Document(
        id=document_id,
        business_id=business_id,
        uploaded_by_user_id=user.id,
        document_type=document_type.value,
        original_filename=original_filename,
        storage_key=storage_key,
        sha256=file_hash,
        content_type=content_type,
        size_bytes=len(content),
        status="processing",
        validation_errors=[],
    )

    saved_path = None
    try:
        db.add(document)
        db.flush()
        saved_path = save_document(storage_key, content)
        db.commit()
        db.refresh(document)
    except IntegrityError:
        db.rollback()
        if saved_path is not None:
            saved_path.unlink(missing_ok=True)
        duplicate = db.scalar(
            select(Document).where(
                Document.business_id == business_id,
                Document.sha256 == file_hash,
            )
        )
        if duplicate is not None:
            return duplicate, True
        raise HTTPException(status_code=409, detail="Document could not be recorded") from None
    except Exception:
        db.rollback()
        if saved_path is not None:
            saved_path.unlink(missing_ok=True)
        raise

    return process_document(db, document), False


def list_business_documents(db: Session, business_id: UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.business_id == business_id)
            .order_by(Document.created_at.desc())
        ).all()
    )


def get_business_document(db: Session, business_id: UUID, document_id: UUID) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.business_id == business_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def get_document_detail(db: Session, document: Document) -> dict:
    invoices = list(
        db.scalars(select(Invoice).where(Invoice.source_document_id == document.id)).all()
    )
    transactions = list(
        db.scalars(
            select(BankTransaction)
            .where(BankTransaction.source_document_id == document.id)
            .order_by(BankTransaction.source_row_number)
        ).all()
    )
    provenance = list(
        db.scalars(
            select(FieldProvenance)
            .where(FieldProvenance.source_document_id == document.id)
            .order_by(
                FieldProvenance.entity_type, FieldProvenance.entity_id, FieldProvenance.field_name
            )
        ).all()
    )
    return {
        "document": document,
        "invoices": invoices,
        "transactions": transactions,
        "provenance": provenance,
    }


def retry_document(db: Session, document: Document) -> Document:
    if document.status in {"processed", "review_required"}:
        return document
    if document.status == "processing":
        raise HTTPException(status_code=409, detail="Document processing is already in progress")
    claimed = db.execute(
        update(Document)
        .where(Document.id == document.id, Document.status == "failed")
        .values(status="processing", validation_errors=[])
    ).rowcount
    db.commit()
    db.refresh(document)
    if claimed != 1:
        if document.status in {"processed", "review_required"}:
            return document
        raise HTTPException(status_code=409, detail="Document processing is already in progress")
    return process_document(db, document)


def _field_errors(record, required_fields: tuple[str, ...]) -> list[dict[str, str]]:
    errors = []
    for field_name in required_fields:
        value = getattr(record, field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(
                {
                    "field": field_name,
                    "code": "required_value_missing",
                    "message": f"Enter and verify {field_name.replace('_', ' ')}.",
                }
            )
    return errors


def _verify_fields(
    db: Session,
    document: Document,
    record,
    entity_type: str,
    updates: dict,
    user: User,
    required_fields: tuple[str, ...],
) -> None:
    fields = set(updates)
    if not fields:
        raise HTTPException(status_code=422, detail="Provide at least one field to verify")
    for name in required_fields:
        if name in updates and updates[name] is None:
            raise HTTPException(status_code=422, detail=f"{name.replace('_', ' ')} cannot be empty")
    for name, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
            if name in required_fields and not value:
                raise HTTPException(
                    status_code=422, detail=f"{name.replace('_', ' ')} cannot be empty"
                )
        setattr(record, name, value)
        provenance = db.scalar(
            select(FieldProvenance).where(
                FieldProvenance.source_document_id == document.id,
                FieldProvenance.entity_type == entity_type,
                FieldProvenance.entity_id == record.id,
                FieldProvenance.field_name == name,
            )
        )
        if provenance is None:
            provenance = FieldProvenance(
                business_id=document.business_id,
                source_document_id=document.id,
                entity_type=entity_type,
                entity_id=record.id,
                field_name=name,
                extracted_value=None,
                source_location="user-supplied correction",
                value_origin="user_verified",
            )
            db.add(provenance)
        provenance.value_origin = "user_verified"
        provenance.verified_by_user_id = user.id
        provenance.verified_at = datetime.now(UTC)
    record.validation_errors = _field_errors(record, required_fields)
    db.flush()
    _refresh_document_status(db, document)
    db.commit()
    db.refresh(document)


def _refresh_document_status(db: Session, document: Document) -> None:
    if document.document_type == DocumentType.INVOICE_PDF.value:
        rows = list(
            db.scalars(select(Invoice).where(Invoice.source_document_id == document.id)).all()
        )
        required = ("invoice_number", "vendor_name", "invoice_date", "total_amount", "currency")
        entity_type = "invoice"
    else:
        rows = list(
            db.scalars(
                select(BankTransaction).where(BankTransaction.source_document_id == document.id)
            ).all()
        )
        required = ("transaction_date", "description", "amount", "currency")
        entity_type = "bank_transaction"
    if not rows:
        document.status = "review_required"
        return

    verified = {
        (item.entity_id, item.field_name)
        for item in db.scalars(
            select(FieldProvenance).where(
                FieldProvenance.source_document_id == document.id,
                FieldProvenance.entity_type == entity_type,
                FieldProvenance.value_origin == "user_verified",
            )
        ).all()
    }
    complete = all(
        not row.validation_errors
        and all((row.id, field_name) in verified for field_name in required)
        for row in rows
    )
    if complete:
        document.status = "processed"
        document.validation_errors = []
    else:
        document.status = "review_required"
        document.validation_errors = [
            {
                "code": "human_verification_required",
                "message": "Extracted fields require review and explicit user verification.",
            }
        ]


def verify_invoice(
    db: Session, document: Document, invoice_id: UUID, data: InvoiceVerification, user: User
) -> Invoice:
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.business_id == document.business_id,
            Invoice.source_document_id == document.id,
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice record not found")
    _verify_fields(
        db,
        document,
        invoice,
        "invoice",
        data.model_dump(exclude_unset=True),
        user,
        ("invoice_number", "vendor_name", "invoice_date", "total_amount", "currency"),
    )
    return invoice


def verify_transaction(
    db: Session, document: Document, transaction_id: UUID, data: TransactionVerification, user: User
) -> BankTransaction:
    transaction = db.scalar(
        select(BankTransaction).where(
            BankTransaction.id == transaction_id,
            BankTransaction.business_id == document.business_id,
            BankTransaction.source_document_id == document.id,
        )
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction record not found")
    _verify_fields(
        db,
        document,
        transaction,
        "bank_transaction",
        data.model_dump(exclude_unset=True),
        user,
        ("transaction_date", "description", "amount", "currency"),
    )
    return transaction
