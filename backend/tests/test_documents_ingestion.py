"""Synthetic CSV/PDF upload, idempotency, provenance, and tenancy tests."""

import shutil
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import app
from app.modules.businesses.models import Business, BusinessMembership
from app.modules.documents.models import Document
from app.modules.financial_records.models import BankTransaction, FieldProvenance, Invoice
from app.modules.identity.models import User


def _register_and_login(client: TestClient, email: str, name: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": name, "password": "Strong-Test-Password-2026!"},
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Strong-Test-Password-2026!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def document_context(monkeypatch) -> Iterator[dict]:
    from app.modules.documents import storage

    storage_root = Path(__file__).resolve().parents[1] / "storage" / f"ingestion-{uuid4().hex}"
    monkeypatch.setattr(storage, "get_storage_root", lambda: storage_root)
    client = TestClient(app)
    prefix = f"ingest-{uuid4().hex}"
    owner_headers = _register_and_login(client, f"{prefix}-owner@example.com", "Owner")
    outsider_headers = _register_and_login(client, f"{prefix}-outsider@example.com", "Outsider")
    owner_business = client.post(
        "/api/v1/businesses", headers=owner_headers, json={"name": "Upload tenant"}
    )
    outsider_business = client.post(
        "/api/v1/businesses", headers=outsider_headers, json={"name": "Other tenant"}
    )
    assert owner_business.status_code == outsider_business.status_code == 201
    data = {
        "client": client,
        "prefix": prefix,
        "headers": owner_headers,
        "outsider_headers": outsider_headers,
        "business_id": owner_business.json()["id"],
        "outsider_business_id": outsider_business.json()["id"],
    }
    yield data

    with Session(get_engine()) as db:
        users = list(db.scalars(select(User).where(User.email.like(f"{prefix}%"))).all())
        user_ids = [user.id for user in users]
        if user_ids:
            business_ids = list(
                db.scalars(
                    select(Business.id).where(Business.created_by_user_id.in_(user_ids))
                ).all()
            )
            if business_ids:
                db.execute(
                    delete(FieldProvenance).where(FieldProvenance.business_id.in_(business_ids))
                )
                db.execute(delete(Invoice).where(Invoice.business_id.in_(business_ids)))
                db.execute(
                    delete(BankTransaction).where(BankTransaction.business_id.in_(business_ids))
                )
                db.execute(delete(Document).where(Document.business_id.in_(business_ids)))
                db.execute(
                    delete(BusinessMembership).where(
                        BusinessMembership.business_id.in_(business_ids)
                    )
                )
                db.execute(delete(Business).where(Business.id.in_(business_ids)))
            db.execute(delete(BusinessMembership).where(BusinessMembership.user_id.in_(user_ids)))
            db.execute(delete(User).where(User.id.in_(user_ids)))
            db.commit()
    shutil.rmtree(storage_root, ignore_errors=True)


def _upload_csv(context: dict, content: bytes, filename: str = "statement.csv"):
    return context["client"].post(
        f"/api/v1/businesses/{context['business_id']}/documents",
        headers=context["headers"],
        data={"document_type": "bank_csv"},
        files={"file": (filename, content, "text/csv")},
    )


def _make_invoice_pdf() -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Acme Office Supply")
    page.insert_text((72, 100), "Invoice Number: AC-2048")
    page.insert_text((72, 125), "Invoice Date: 2026-10-03")
    page.insert_text((72, 150), "Due Date: 2026-10-20")
    page.insert_text((72, 175), "Currency: USD")
    page.insert_text((72, 200), "Total Due: $1,250.50")
    data = pdf.tobytes()
    pdf.close()
    return data


def test_csv_hash_idempotency_provenance_verification_and_tenant_scope(document_context) -> None:
    csv_content = (
        (
            "Date,Description,Amount,Currency,Reference\n"
            "2026-10-01,Coffee Shop,-12.34,USD,TX-001\n"
            "2026-10-02,Acme Office,1,250.50,USD,TX-002\n"
        )
        .replace("1,250.50", '"1,250.50"')
        .encode()
    )
    uploaded = _upload_csv(document_context, csv_content)
    assert uploaded.status_code == 201, uploaded.text
    first = uploaded.json()
    document_id = first["document"]["id"]
    assert first["document"]["status"] == "review_required"
    assert first["duplicate"] is False

    repeated = _upload_csv(document_context, csv_content, "same-content.csv")
    assert repeated.status_code == 200
    assert repeated.json()["duplicate"] is True
    assert repeated.json()["document"]["id"] == document_id

    client = document_context["client"]
    business_id = document_context["business_id"]
    detail_url = f"/api/v1/businesses/{business_id}/documents/{document_id}"
    detail_response = client.get(detail_url, headers=document_context["headers"])
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert len(detail["transactions"]) == 2
    assert Decimal(detail["transactions"][0]["amount"]) == Decimal("-12.34")
    assert Decimal(detail["transactions"][1]["amount"]) == Decimal("1250.50")
    first_transaction_id = detail["transactions"][0]["id"]
    source = next(
        item
        for item in detail["provenance"]
        if item["field_name"] == "amount" and item["entity_id"] == first_transaction_id
    )
    assert source["source_document_id"] == document_id
    assert source["source_location"] == "CSV row 2"
    assert source["value_origin"] == "extracted"

    outsider_url = (
        f"/api/v1/businesses/{document_context['outsider_business_id']}/documents/{document_id}"
    )
    assert client.get(outsider_url, headers=document_context["outsider_headers"]).status_code == 404
    assert client.get(detail_url, headers=document_context["outsider_headers"]).status_code == 404
    assert (
        client.get(f"{detail_url}/file", headers=document_context["headers"]).content == csv_content
    )

    records = detail["transactions"]
    for transaction, description, amount in zip(
        records, ["Coffee Shop", "Acme Office"], ["-12.34", "1250.50"], strict=True
    ):
        verified = client.patch(
            f"{detail_url}/transactions/{transaction['id']}",
            headers=document_context["headers"],
            json={
                "transaction_date": transaction["transaction_date"],
                "description": description,
                "amount": amount,
                "currency": "USD",
            },
        )
        assert verified.status_code == 200, verified.text
    assert verified.json()["document"]["status"] == "processed"
    assert all(
        item["value_origin"] == "user_verified"
        for item in verified.json()["provenance"]
        if item["field_name"] in {"transaction_date", "description", "amount", "currency"}
    )

    retried = client.post(f"{detail_url}/process", headers=document_context["headers"])
    assert retried.status_code == 200
    assert retried.json()["status"] == "processed"
    after_retry = client.get(detail_url, headers=document_context["headers"]).json()
    assert len(after_retry["transactions"]) == 2
    assert (
        len(
            client.get(
                f"/api/v1/businesses/{business_id}/documents", headers=document_context["headers"]
            ).json()
        )
        == 1
    )


def test_pdf_invoice_extraction_review_provenance_and_scanned_pdf_warning(document_context) -> None:
    client = document_context["client"]
    business_id = document_context["business_id"]
    uploaded = client.post(
        f"/api/v1/businesses/{business_id}/documents",
        headers=document_context["headers"],
        data={"document_type": "invoice_pdf"},
        files={"file": ("acme-invoice.pdf", _make_invoice_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["document"]["id"]
    assert uploaded.json()["document"]["status"] == "review_required"
    detail_url = f"/api/v1/businesses/{business_id}/documents/{document_id}"
    detail = client.get(detail_url, headers=document_context["headers"]).json()
    assert len(detail["invoices"]) == 1
    invoice = detail["invoices"][0]
    assert invoice["invoice_number"] == "AC-2048"
    assert Decimal(invoice["total_amount"]) == Decimal("1250.50")
    assert invoice["currency"] == "USD"
    invoice_number_source = next(
        item for item in detail["provenance"] if item["field_name"] == "invoice_number"
    )
    assert invoice_number_source["source_location"].startswith("PDF page")
    assert invoice_number_source["value_origin"] == "extracted"

    verified = client.patch(
        f"{detail_url}/invoices/{invoice['id']}",
        headers=document_context["headers"],
        json={
            "invoice_number": invoice["invoice_number"],
            "vendor_name": invoice["vendor_name"],
            "invoice_date": invoice["invoice_date"],
            "total_amount": invoice["total_amount"],
            "currency": invoice["currency"],
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["document"]["status"] == "processed"

    scanned = pymupdf.open()
    scanned.new_page()
    scanned_content = scanned.tobytes()
    scanned.close()
    scanned_upload = client.post(
        f"/api/v1/businesses/{business_id}/documents",
        headers=document_context["headers"],
        data={"document_type": "invoice_pdf"},
        files={"file": ("scan.pdf", scanned_content, "application/pdf")},
    )
    assert scanned_upload.status_code == 201
    scan_id = scanned_upload.json()["document"]["id"]
    scan_detail = client.get(
        f"/api/v1/businesses/{business_id}/documents/{scan_id}",
        headers=document_context["headers"],
    ).json()
    assert scan_detail["document"]["status"] == "review_required"
    assert any(
        error["code"] == "no_embedded_text"
        for error in scan_detail["invoices"][0]["validation_errors"]
    )


def test_file_validation_size_limit_and_processing_error_status(
    document_context, monkeypatch
) -> None:
    from types import SimpleNamespace

    import app.modules.documents.router as documents_router
    import app.modules.documents.service as documents_service

    client = document_context["client"]
    business_id = document_context["business_id"]
    url = f"/api/v1/businesses/{business_id}/documents"
    headers = document_context["headers"]

    wrong_extension = client.post(
        url,
        headers=headers,
        data={"document_type": "bank_csv"},
        files={"file": ("statement.txt", b"Date,Amount", "text/plain")},
    )
    assert wrong_extension.status_code == 415

    small_limit = SimpleNamespace(max_document_upload_mb=1)
    monkeypatch.setattr(documents_router, "get_settings", lambda: small_limit)
    monkeypatch.setattr(documents_service, "get_settings", lambda: small_limit)
    too_large = client.post(
        url,
        headers=headers,
        data={"document_type": "bank_csv"},
        files={"file": ("large.csv", b"x" * (1024 * 1024 + 1), "text/csv")},
    )
    assert too_large.status_code == 413

    malformed_pdf = client.post(
        url,
        headers=headers,
        data={"document_type": "invoice_pdf"},
        files={"file": ("broken.pdf", b"%PDF-invalid-content", "application/pdf")},
    )
    assert malformed_pdf.status_code == 201
    failed = malformed_pdf.json()["document"]
    assert failed["status"] == "failed"
    assert failed["validation_errors"][0]["code"] == "processing_failed"
    retried = client.post(f"{url}/{failed['id']}/process", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["status"] == "failed"
