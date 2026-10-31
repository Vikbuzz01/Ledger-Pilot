"""Restricted ORM tools; every operation takes an authorized business scope."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.businesses.models import Business
from app.modules.documents.models import Document
from app.modules.financial_records.models import BankTransaction, FieldProvenance, Invoice
from app.modules.reconciliation.models import (
    InvestigationToolExecution,
    ReconciliationException,
)


def _record_refs(value):
    refs = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"id", "source_document_id", "record_id", "exception_id"} and isinstance(
                child, str
            ):
                refs.add(child)
            refs.update(_record_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_record_refs(child))
    return refs


def transaction_detail(db: Session, business_id: UUID, record_id: UUID):
    row = db.scalar(
        select(BankTransaction).where(
            BankTransaction.business_id == business_id, BankTransaction.id == record_id
        )
    )
    if row is None:
        return None
    return {
        "id": str(row.id),
        "source_document_id": str(row.source_document_id),
        "date": str(row.transaction_date) if row.transaction_date else None,
        "description": row.description,
        "amount": str(row.amount),
        "currency": row.currency,
        "reference": row.external_reference,
        "source_row": row.source_row_number,
    }


def invoice_detail(db: Session, business_id: UUID, record_id: UUID):
    row = db.scalar(
        select(Invoice).where(Invoice.business_id == business_id, Invoice.id == record_id)
    )
    if row is None:
        return None
    return {
        "id": str(row.id),
        "source_document_id": str(row.source_document_id),
        "invoice_number": row.invoice_number,
        "vendor": row.vendor_name,
        "date": str(row.invoice_date) if row.invoice_date else None,
        "amount": str(row.total_amount),
        "currency": row.currency,
    }


def provenance(db: Session, business_id: UUID, record_ids: list[UUID]):
    rows = (
        db.scalars(
            select(FieldProvenance).where(
                FieldProvenance.business_id == business_id,
                FieldProvenance.entity_id.in_(record_ids),
            )
        ).all()
        if record_ids
        else []
    )
    return [
        {
            "id": str(row.id),
            "record_id": str(row.entity_id),
            "field": row.field_name,
            "extracted_value": row.extracted_value,
            "source_document_id": str(row.source_document_id),
            "location": row.source_location,
            "origin": row.value_origin,
            "verified_by": str(row.verified_by_user_id) if row.verified_by_user_id else None,
        }
        for row in rows
    ]


def execute_investigation_tools(
    db: Session, business_id: UUID, investigation_id: UUID, exception: ReconciliationException
) -> dict:
    tx_ids = [UUID(value) for value in exception.transaction_ids]
    inv_ids = [UUID(value) for value in exception.invoice_ids]
    tx = [value for ident in tx_ids if (value := transaction_detail(db, business_id, ident))]
    inv = [value for ident in inv_ids if (value := invoice_detail(db, business_id, ident))]
    business = db.scalar(select(Business).where(Business.id == business_id))
    source_ids = {UUID(row["source_document_id"]) for row in tx + inv}
    documents = (
        db.scalars(
            select(Document).where(Document.business_id == business_id, Document.id.in_(source_ids))
        ).all()
        if source_ids
        else []
    )
    results = {
        "retrieve_business_context": {
            "records": [{"id": str(business.id), "name": business.name}] if business else []
        },
        "retrieve_transaction_details": {"records": tx},
        "retrieve_invoice_details": {"records": inv},
        "retrieve_source_provenance": {"records": provenance(db, business_id, tx_ids + inv_ids)},
        "retrieve_document_extraction_details": {
            "records": [
                {
                    "id": str(document.id),
                    "document_type": document.document_type,
                    "status": document.status,
                    "validation_errors": document.validation_errors,
                }
                for document in documents
            ]
        },
        "compare_candidate_records": {
            "comparisons": [
                {
                    "transaction_id": transaction["id"],
                    "invoice_id": invoice["id"],
                    "amount_difference": str(
                        abs(Decimal(transaction["amount"])) - Decimal(invoice["amount"])
                    ),
                    "currency_equal": transaction["currency"] == invoice["currency"],
                    "counterparty_text": transaction["description"],
                    "invoice_vendor": invoice["vendor"],
                }
                for transaction in tx
                for invoice in inv
                if transaction.get("amount") not in (None, "None")
                and invoice.get("amount") not in (None, "None")
            ]
        },
    }
    # Targeted searches are constrained to the current business and exact supplied facts.
    amounts = {Decimal(item["amount"]) for item in tx if item["amount"] not in (None, "None")}
    if amounts:
        rows = db.scalars(
            select(Invoice).where(
                Invoice.business_id == business_id, Invoice.total_amount.in_(list(amounts))
            )
        ).all()
        results["search_invoices_by_amount"] = {
            "records": [invoice_detail(db, business_id, row.id) for row in rows]
        }
    refs = {item["reference"] for item in tx if item.get("reference")}
    if refs:
        rows = db.scalars(
            select(BankTransaction).where(
                BankTransaction.business_id == business_id,
                BankTransaction.external_reference.in_(list(refs)),
            )
        ).all()
        results["search_transactions_by_reference"] = {
            "records": [transaction_detail(db, business_id, row.id) for row in rows]
        }
    if inv:
        vendor_names = [
            row.vendor_name
            for ident in inv_ids
            if (
                row := db.scalar(
                    select(Invoice).where(Invoice.business_id == business_id, Invoice.id == ident)
                )
            )
            and row.vendor_name
        ]
        if vendor_names:
            rows = db.scalars(
                select(Invoice).where(
                    Invoice.business_id == business_id, Invoice.vendor_name.in_(vendor_names)
                )
            ).all()
            results["search_invoices_by_vendor"] = {
                "records": [invoice_detail(db, business_id, row.id) for row in rows]
            }
    # Historical outcome retrieval remains business bounded.
    previous = db.scalars(
        select(ReconciliationException)
        .where(
            ReconciliationException.business_id == business_id,
            ReconciliationException.exception_type == exception.exception_type,
            ReconciliationException.id != exception.id,
        )
        .limit(20)
    ).all()
    results["retrieve_previous_reconciliation_outcomes"] = {
        "records": [
            {
                "exception_id": str(item.id),
                "type": item.exception_type,
                "status": item.status,
                "summary": item.summary,
            }
            for item in previous
        ]
    }
    for name, result in results.items():
        db.add(
            InvestigationToolExecution(
                business_id=business_id,
                investigation_id=investigation_id,
                tool_name=name,
                record_references=sorted(_record_refs(result)),
                result=result,
            )
        )
    return {
        "exception": {
            "id": str(exception.id),
            "type": exception.exception_type,
            "summary": exception.summary,
        },
        "tools": results,
        "available_record_ids": sorted(
            _record_refs(
                {
                    name: result
                    for name, result in results.items()
                    if name
                    not in {
                        "retrieve_business_context",
                        "retrieve_previous_reconciliation_outcomes",
                    }
                }
            )
        ),
    }
