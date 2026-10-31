"""Create a repeat-safe, synthetic-only SQLite demonstration workspace."""

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.modules.businesses.models import Business, BusinessMembership
from app.modules.documents.models import Document
from app.modules.documents.storage import save_document
from app.modules.financial_records.models import BankTransaction, FieldProvenance, Invoice
from app.modules.identity.models import User
from app.modules.identity.security import hash_password
from app.modules.reconciliation.models import AuditEvent
from app.modules.reconciliation.service import start_run

DEMO_EMAIL = "demo@ledgerpilot.com"
DEMO_PASSWORD = "LedgerPilot-Demo-2026!"
DEMO_BUSINESS = "Northstar Demo Studio"


def _pdf(number: str, vendor: str, amount: Decimal) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), vendor)
    page.insert_text((72, 100), f"Invoice Number: {number}")
    page.insert_text((72, 125), "Invoice Date: 2026-10-01")
    page.insert_text((72, 150), "Currency: USD")
    page.insert_text((72, 175), f"Total Due: ${amount:.2f}")
    content = pdf.tobytes()
    pdf.close()
    return content


def _document(db, business_id, user_id, file_name, content, kind):
    document_id = uuid4()
    extension = ".csv" if kind == "bank_csv" else ".pdf"
    key = f"{business_id}/{document_id}{extension}"
    digest = hashlib.sha256(content).hexdigest()
    save_document(key, content)
    row = Document(
        id=document_id,
        business_id=business_id,
        uploaded_by_user_id=user_id,
        document_type=kind,
        original_filename=file_name,
        storage_key=key,
        sha256=digest,
        content_type="text/csv" if kind == "bank_csv" else "application/pdf",
        size_bytes=len(content),
        status="processed",
        validation_errors=[],
        processed_at=datetime.now(UTC),
    )
    db.add(row)
    return row


def _provenance(db, business_id, document_id, entity_type, entity_id, user_id, values, location):
    for name, value in values.items():
        db.add(
            FieldProvenance(
                business_id=business_id,
                source_document_id=document_id,
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=name,
                extracted_value=str(value),
                source_location=location,
                value_origin="user_verified",
                verified_by_user_id=user_id,
                verified_at=datetime.now(UTC),
            )
        )


def seed_demo() -> bool:
    settings = get_settings()
    if settings.database_mode != "sqlite":
        raise RuntimeError("The synthetic demo seed is restricted to DATABASE_MODE=sqlite")
    engine = get_engine()
    with Session(engine) as db:
        existing = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing:
            business = db.scalar(
                select(Business).where(
                    Business.created_by_user_id == existing.id,
                    Business.name == DEMO_BUSINESS,
                )
            )
            if business:
                return False
            raise RuntimeError("Demo account exists without its expected business; inspect DB")

        user = User(
            email=DEMO_EMAIL,
            full_name="LedgerPilot Demo",
            password_hash=hash_password(DEMO_PASSWORD),
        )
        db.add(user)
        db.flush()
        business = Business(name=DEMO_BUSINESS, created_by_user_id=user.id)
        db.add(business)
        db.flush()
        db.add(BusinessMembership(business_id=business.id, user_id=user.id, role="owner"))

        tx_specs = [
            (
                "Northstar Office Supply",
                Decimal("125.50"),
                "NS-1001",
                "Northstar Office Supply",
                "INV-1001",
            ),
            ("Harbor Print Works", Decimal("40.00"), "HP-40", "Harbor Print Works", "INV-2001"),
            ("Harbor Print Works", Decimal("60.00"), "HP-60", "Harbor Print Works", "INV-2001"),
            ("Cedar Cloud Services", Decimal("30.00"), "CC-30", "Cedar Cloud Services", "INV-3001"),
            ("Unknown Merchant", Decimal("22.10"), "UN-1", "", ""),
        ]
        csv_content = (
            "Date,Description,Amount,Currency,Reference\n"
            + "".join(
                f"2026-10-{index + 2:02d},{description},-{amount:.2f},USD,{reference}\n"
                for index, (description, amount, reference, _, _) in enumerate(tx_specs)
            )
        ).encode("utf-8")
        bank_doc = _document(
            db, business.id, user.id, "synthetic-bank-statement.csv", csv_content, "bank_csv"
        )
        db.flush()
        for index, (description, amount, reference, _, _) in enumerate(tx_specs):
            transaction = BankTransaction(
                business_id=business.id,
                source_document_id=bank_doc.id,
                source_row_number=index + 2,
                transaction_date=date(2026, 10, index + 2),
                description=description,
                amount=-amount,
                currency="USD",
                external_reference=reference,
                raw_data={"synthetic": "true"},
                validation_errors=[],
            )
            db.add(transaction)
            db.flush()
            _provenance(
                db,
                business.id,
                bank_doc.id,
                "bank_transaction",
                transaction.id,
                user.id,
                {
                    "transaction_date": transaction.transaction_date.isoformat(),
                    "description": description,
                    "amount": format(-amount, "f"),
                    "currency": "USD",
                },
                f"CSV row {index + 2}",
            )

        invoice_specs = [
            ("INV-1001", "Northstar Office Supply", Decimal("125.50")),
            ("INV-2001", "Harbor Print Works", Decimal("100.00")),
            ("INV-3001", "Cedar Cloud Services", Decimal("80.00")),
        ]
        for number, vendor, amount in invoice_specs:
            content = _pdf(number, vendor, amount)
            document = _document(
                db,
                business.id,
                user.id,
                f"synthetic-{number.lower()}.pdf",
                content,
                "invoice_pdf",
            )
            db.flush()
            invoice = Invoice(
                business_id=business.id,
                source_document_id=document.id,
                invoice_number=number,
                vendor_name=vendor,
                invoice_date=date(2026, 10, 1),
                total_amount=amount,
                currency="USD",
                validation_errors=[],
            )
            db.add(invoice)
            db.flush()
            _provenance(
                db,
                business.id,
                document.id,
                "invoice",
                invoice.id,
                user.id,
                {
                    "invoice_number": number,
                    "vendor_name": vendor,
                    "invoice_date": invoice.invoice_date.isoformat(),
                    "total_amount": format(amount, "f"),
                    "currency": "USD",
                },
                "PDF page 1",
            )

        db.add(
            AuditEvent(
                business_id=business.id,
                actor_user_id=user.id,
                action="synthetic_demo_seeded",
                entity_type="business",
                entity_id=business.id,
                after_state={"synthetic": True},
                reason="Generated demo-only sample records",
            )
        )
        db.commit()
        start_run(db, business.id, user, "ledgerpilot-demo-initial-run")
    return True


if __name__ == "__main__":
    created = seed_demo()
    print(
        "Synthetic LedgerPilot demo workspace created."
        if created
        else "Demo workspace already exists; no changes made."
    )
