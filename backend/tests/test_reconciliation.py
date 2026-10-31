"""Synthetic SQL Server reconciliation, approval, isolation, and investigation coverage."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import app
from app.modules.businesses.models import Business, BusinessMembership
from app.modules.documents.models import Document
from app.modules.financial_records.models import BankTransaction, FieldProvenance, Invoice
from app.modules.identity.models import User
from app.modules.reconciliation.investigation.schemas import Finding, InvestigationReport
from app.modules.reconciliation.models import (
    ApprovalDecision,
    AuditEvent,
    Investigation,
    InvestigationToolExecution,
    MatchCandidate,
    PaymentAllocation,
    ReconciliationException,
    ReconciliationRun,
    VendorAliasCandidate,
)


def _account(client: TestClient, email: str) -> str:
    payload = {
        "email": email,
        "full_name": "Synthetic Tester",
        "password": "Strong-Test-Password-2026!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": payload["password"]}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def recon_context() -> Iterator[dict]:
    client = TestClient(app)
    tag = uuid4().hex
    token = _account(client, f"recon-{tag}@example.com")
    other_token = _account(client, f"outsider-{tag}@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}
    business = client.post(
        "/api/v1/businesses", headers=headers, json={"name": f"Synthetic reconciliation {tag}"}
    ).json()
    other_business = client.post(
        "/api/v1/businesses", headers=other_headers, json={"name": f"Other synthetic {tag}"}
    ).json()
    context = {
        "client": client,
        "tag": tag,
        "headers": headers,
        "other_headers": other_headers,
        "business_id": business["id"],
        "other_business_id": other_business["id"],
    }
    _seed(context)
    yield context
    with Session(get_engine()) as db:
        business_ids = list(
            db.scalars(
                select(Business.id).where(
                    Business.name.in_([f"Synthetic reconciliation {tag}", f"Other synthetic {tag}"])
                )
            ).all()
        )
        user_ids = list(
            db.scalars(select(User.id).where(User.email.like(f"%{tag}@example.com"))).all()
        )
        for model in (
            AuditEvent,
            ApprovalDecision,
            InvestigationToolExecution,
            Investigation,
            PaymentAllocation,
            ReconciliationException,
            MatchCandidate,
            VendorAliasCandidate,
            ReconciliationRun,
        ):
            db.execute(delete(model).where(model.business_id.in_(business_ids)))
        db.execute(delete(FieldProvenance).where(FieldProvenance.business_id.in_(business_ids)))
        db.execute(delete(Invoice).where(Invoice.business_id.in_(business_ids)))
        db.execute(delete(BankTransaction).where(BankTransaction.business_id.in_(business_ids)))
        db.execute(delete(Document).where(Document.business_id.in_(business_ids)))
        db.execute(
            delete(BusinessMembership).where(BusinessMembership.business_id.in_(business_ids))
        )
        db.execute(delete(Business).where(Business.id.in_(business_ids)))
        db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()


def _seed(context: dict) -> None:
    with Session(get_engine()) as db:
        business_id = UUID(context["business_id"])
        owner_id = db.scalar(
            select(User.id).where(User.email == f"recon-{context['tag']}@example.com")
        )
        tx_specs = [
            ("Exact Vendor", "100", "EX-1", date(2026, 10, 1)),
            ("Partial Vendor", "40", "PA-1", date(2026, 10, 2)),
            ("Partial Vendor", "50", "PA-2", date(2026, 10, 3)),
            ("Partial Vendor", "20", "PA-3", date(2026, 10, 4)),
            ("Partial Vendor", "70", "PA-4", date(2026, 10, 5)),
            ("Duplicate Vendor", "60", "DU-1", date(2026, 10, 4)),
            ("Duplicate Vendor", "60", "DU-1", date(2026, 10, 4)),
            ("Northstar Hardware", "23", "UN-1", date(2026, 10, 5)),
            ("Rapid Garage", "77", "CF-1", date(2026, 10, 6)),
            ("Date Vendor", "35", "DT-1", date(2026, 10, 9)),
            ("Mismatch Vendor", "130", "MM-1", date(2026, 10, 8)),
            ("Acme Office", "22", "AL-1", date(2026, 10, 10)),
            ("Currency Vendor", "15", "CU-1", date(2026, 10, 11)),
        ]
        inv_specs = [
            ("EV-001", "Exact Vendor Inc.", "100", "USD", date(2026, 10, 1)),
            ("PA-001", "Partial Vendor LLC", "90", "USD", date(2026, 10, 2)),
            ("DU-001", "Duplicate Vendor", "60", "USD", date(2026, 10, 4)),
            ("DU-001A", "Duplicate Vendor Ltd", "60", "USD", date(2026, 10, 4)),
            ("CF-001", "Catering Depot", "77", "USD", date(2026, 10, 6)),
            ("DT-001", "Date Vendor", "35", "USD", date(2026, 9, 1)),
            ("MM-001", "Mismatch Vendor", "100", "USD", date(2026, 10, 8)),
            ("MISSING-1", "Orchid Catering", "45", "USD", date(2026, 10, 7)),
            ("AL-001", "Acme Office Supply", "22", "USD", date(2026, 10, 10)),
            ("CU-001", "Currency Vendor Inc", "15", "USD", date(2026, 10, 11)),
        ]
        for idx, (desc, amount, reference, day) in enumerate(tx_specs):
            source_id = uuid4()
            db.add(
                Document(
                    id=source_id,
                    business_id=business_id,
                    uploaded_by_user_id=owner_id,
                    document_type="bank_csv",
                    original_filename=f"synthetic-{idx}.csv",
                    storage_key=f"synthetic/{source_id}.csv",
                    sha256=uuid4().hex * 2,
                    content_type="text/csv",
                    size_bytes=1,
                    status="processed",
                    validation_errors=[],
                )
            )
            tx_id = uuid4()
            db.add(
                BankTransaction(
                    id=tx_id,
                    business_id=business_id,
                    source_document_id=source_id,
                    source_row_number=idx + 2,
                    transaction_date=day,
                    description=desc,
                    amount=Decimal(amount),
                    currency="EUR" if desc == "Currency Vendor" else "USD",
                    external_reference=reference,
                    raw_data={},
                    validation_errors=[],
                )
            )
        for idx, (number, vendor, amount, currency, day) in enumerate(inv_specs):
            source_id = uuid4()
            db.add(
                Document(
                    id=source_id,
                    business_id=business_id,
                    uploaded_by_user_id=owner_id,
                    document_type="invoice_pdf",
                    original_filename=f"synthetic-{idx}.pdf",
                    storage_key=f"synthetic/{source_id}.pdf",
                    sha256=uuid4().hex * 2,
                    content_type="application/pdf",
                    size_bytes=1,
                    status="processed",
                    validation_errors=[],
                )
            )
            db.add(
                Invoice(
                    business_id=business_id,
                    source_document_id=source_id,
                    invoice_number=number,
                    vendor_name=vendor,
                    invoice_date=day,
                    total_amount=Decimal(amount),
                    currency=currency,
                    validation_errors=[],
                )
            )
        db.commit()


def test_reconciliation_candidates_exceptions_and_idempotency(recon_context):
    client = recon_context["client"]
    prefix = f"/api/v1/businesses/{recon_context['business_id']}/reconciliation"
    run = client.post(
        prefix + "/runs",
        headers=recon_context["headers"],
        json={"idempotency_key": "synthetic-suite-1"},
    )
    assert run.status_code == 201, run.text
    repeated = client.post(
        prefix + "/runs",
        headers=recon_context["headers"],
        json={"idempotency_key": "synthetic-suite-1"},
    )
    assert repeated.json()["id"] == run.json()["id"]
    candidates = client.get(
        prefix + f"/runs/{run.json()['id']}/candidates", headers=recon_context["headers"]
    ).json()
    methods = {candidate["matching_method"] for candidate in candidates}
    assert {"exact_amount", "partial_payment", "split_payment", "amount_mismatch"} <= methods
    assert all("transaction_ids" in candidate["evidence"] for candidate in candidates)
    assert sum(candidate["matching_method"] == "split_payment" for candidate in candidates) >= 2
    exceptions = client.get(
        prefix + f"/runs/{run.json()['id']}/exceptions", headers=recon_context["headers"]
    ).json()
    types = {item["exception_type"] for item in exceptions}
    assert {
        "partial_payment",
        "split_payment",
        "duplicate_invoice",
        "duplicate_transaction",
        "unmatched_transaction",
        "missing_invoice",
        "conflicting_counterparty",
        "date_discrepancy",
        "amount_mismatch",
        "currency_mismatch",
    } <= types


def test_approval_allocates_split_once_and_blocks_overallocation(recon_context):
    client = recon_context["client"]
    prefix = f"/api/v1/businesses/{recon_context['business_id']}/reconciliation"
    run = client.post(prefix + "/runs", headers=recon_context["headers"], json={}).json()
    candidates = client.get(
        prefix + f"/runs/{run['id']}/candidates", headers=recon_context["headers"]
    ).json()
    split = next(item for item in candidates if item["matching_method"] == "split_payment")
    approval = client.post(
        prefix + f"/candidates/{split['id']}/decision",
        headers=recon_context["headers"],
        json={"decision": "approve", "reason": "Reviewed synthetic split evidence"},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved"
    balances = client.get(prefix + "/invoice-balances", headers=recon_context["headers"]).json()
    settled_balance = next(item for item in balances if item["invoice_id"] == split["invoice_id"])
    assert settled_balance["paid_amount"] == "90.0000"
    assert settled_balance["outstanding_amount"] == "0.0000"
    assert (
        client.post(
            prefix + f"/candidates/{split['id']}/decision",
            headers=recon_context["headers"],
            json={"decision": "approve"},
        ).status_code
        == 409
    )
    split_tx_ids = set(split["evidence"]["transaction_ids"])
    partial = next(
        item
        for item in candidates
        if item["matching_method"] == "partial_payment"
        and split_tx_ids.intersection(item["evidence"]["transaction_ids"])
    )
    assert (
        client.post(
            prefix + f"/candidates/{partial['id']}/decision",
            headers=recon_context["headers"],
            json={"decision": "approve"},
        ).status_code
        == 409
    )
    audit = client.get(prefix + "/audit", headers=recon_context["headers"]).json()
    assert any(item["action"] == "approve" and item["entity_id"] == split["id"] for item in audit)


def test_partial_allocation_preserves_outstanding_balance(recon_context):
    client = recon_context["client"]
    prefix = f"/api/v1/businesses/{recon_context['business_id']}/reconciliation"
    run = client.post(prefix + "/runs", headers=recon_context["headers"], json={}).json()
    candidates = client.get(
        prefix + f"/runs/{run['id']}/candidates", headers=recon_context["headers"]
    ).json()
    invoice_partial = next(
        item
        for item in candidates
        if item["matching_method"] == "partial_payment"
        and item["amounts_compared"]["invoice"] == "90.0000"
        and "Partial Vendor" in item["evidence"]["transaction_descriptions"]
    )
    response = client.post(
        prefix + f"/candidates/{invoice_partial['id']}/decision",
        headers=recon_context["headers"],
        json={"decision": "approve"},
    )
    assert response.status_code == 200, response.text
    balances = client.get(prefix + "/invoice-balances", headers=recon_context["headers"]).json()
    balance = next(item for item in balances if item["invoice_id"] == invoice_partial["invoice_id"])
    assert Decimal(balance["paid_amount"]) in {
        Decimal("20"),
        Decimal("40"),
        Decimal("50"),
        Decimal("70"),
    }
    assert Decimal(balance["outstanding_amount"]) in {
        Decimal("70"),
        Decimal("50"),
        Decimal("40"),
        Decimal("20"),
    }


def test_reject_proposal_is_audited_and_cannot_be_repeated(recon_context):
    client = recon_context["client"]
    prefix = f"/api/v1/businesses/{recon_context['business_id']}/reconciliation"
    run = client.post(prefix + "/runs", headers=recon_context["headers"], json={}).json()
    candidates = client.get(
        prefix + f"/runs/{run['id']}/candidates", headers=recon_context["headers"]
    ).json()
    candidate = next(item for item in candidates if item["status"] == "proposed")
    decision = client.post(
        prefix + f"/candidates/{candidate['id']}/decision",
        headers=recon_context["headers"],
        json={"decision": "reject", "reason": "Conflicting reference"},
    )
    assert decision.status_code == 200 and decision.json()["status"] == "rejected"
    repeat = client.post(
        prefix + f"/candidates/{candidate['id']}/decision",
        headers=recon_context["headers"],
        json={"decision": "reject"},
    )
    assert repeat.status_code == 409


def test_tenant_access_and_provider_unavailable_are_explicit(recon_context):
    client = recon_context["client"]
    prefix = f"/api/v1/businesses/{recon_context['business_id']}/reconciliation"
    other = f"/api/v1/businesses/{recon_context['other_business_id']}/reconciliation"
    assert (
        client.post(other + "/runs", headers=recon_context["headers"], json={}).status_code == 404
    )
    run = client.post(prefix + "/runs", headers=recon_context["headers"], json={}).json()
    exc = client.get(
        prefix + f"/runs/{run['id']}/exceptions", headers=recon_context["headers"]
    ).json()[0]
    assert (
        client.post(
            prefix + f"/exceptions/{exc['id']}/investigations",
            headers=recon_context["other_headers"],
        ).status_code
        == 404
    )
    investigation = client.post(
        prefix + f"/exceptions/{exc['id']}/investigations", headers=recon_context["headers"]
    )
    assert investigation.status_code == 201, investigation.text
    assert investigation.json()["status"] == "unavailable"
    assert investigation.json()["report"] is None


def test_alias_candidates_are_untrusted_until_admin_verifies(recon_context):
    client = recon_context["client"]
    prefix = f"/api/v1/businesses/{recon_context['business_id']}/reconciliation"
    client.post(prefix + "/runs", headers=recon_context["headers"], json={})
    alias_rows = client.get(prefix + "/aliases", headers=recon_context["headers"]).json()
    alias = next(item for item in alias_rows if item["candidate_name"] == "Acme Office")
    assert alias["verified"] is False
    response = client.post(
        prefix + f"/aliases/{alias['id']}/verify", headers=recon_context["headers"]
    )
    assert response.status_code == 200 and response.json()["verified"] is True
    next_run = client.post(
        prefix + "/runs",
        headers=recon_context["headers"],
        json={"idempotency_key": "after-alias-verification"},
    ).json()
    candidates = client.get(
        prefix + f"/runs/{next_run['id']}/candidates", headers=recon_context["headers"]
    ).json()
    assert any(item["scoring_factors"].get("verified_alias") is True for item in candidates)


def test_mocked_investigation_records_tool_history_and_requires_human_review(
    recon_context, monkeypatch
):
    from app.modules.reconciliation.investigation import workflow

    class MockProvider:
        def investigate(self, context):
            ref = context["available_record_ids"][0]
            return InvestigationReport(
                summary="Synthetic evidence gathered; human review remains necessary.",
                verified_facts=[
                    Finding(
                        statement="Source record exists in the business ledger.",
                        source_record_ids=[ref],
                    )
                ],
                supporting_evidence=[],
                hypotheses=[],
                contradicting_evidence=[
                    Finding(
                        statement="A second source leaves the payment reference uncertain.",
                        source_record_ids=[ref],
                    )
                ],
                missing_information=[],
                confidence="medium",
                recommended_resolution="Review the source documents.",
                human_review_required=False,
            )

    monkeypatch.setattr(workflow, "configured_provider", lambda: MockProvider())
    client = recon_context["client"]
    prefix = f"/api/v1/businesses/{recon_context['business_id']}/reconciliation"
    run = client.post(prefix + "/runs", headers=recon_context["headers"], json={}).json()
    exc = client.get(
        prefix + f"/runs/{run['id']}/exceptions", headers=recon_context["headers"]
    ).json()[0]
    investigation = client.post(
        prefix + f"/exceptions/{exc['id']}/investigations", headers=recon_context["headers"]
    ).json()
    assert investigation["status"] == "completed"
    assert investigation["report"]["human_review_required"] is True
    assert investigation["report"]["contradicting_evidence"]
    history = client.get(
        prefix + f"/investigations/{investigation['id']}/tools", headers=recon_context["headers"]
    )
    assert history.status_code == 200 and len(history.json()) >= 3
    decision = client.post(
        prefix + f"/investigations/{investigation['id']}/decision",
        headers=recon_context["headers"],
        json={"decision": "approve", "reason": "Reviewed report"},
    )
    assert decision.status_code == 200, decision.text
    assert (
        client.post(
            prefix + f"/investigations/{investigation['id']}/decision",
            headers=recon_context["headers"],
            json={"decision": "approve"},
        ).status_code
        == 409
    )
    audit = client.get(prefix + "/audit", headers=recon_context["headers"]).json()
    assert any(item["action"] == "investigation_completed" for item in audit)
    assert any(item["action"] == "ai_recommendation_approve" for item in audit)
    balances = client.get(prefix + "/invoice-balances", headers=recon_context["headers"]).json()
    assert all(Decimal(item["paid_amount"]) == Decimal("0") for item in balances)


def test_investigation_schema_accepts_insufficient_evidence_and_rejects_uncited_facts():
    report = InvestigationReport(
        summary="The available records do not resolve the conflict.",
        verified_facts=[],
        supporting_evidence=[],
        hypotheses=[],
        contradicting_evidence=[],
        missing_information=["A verified remittance reference is missing."],
        confidence="insufficient_evidence",
        recommended_resolution="Request the remittance advice.",
        human_review_required=True,
    )
    assert report.confidence == "insufficient_evidence"
    with pytest.raises(ValidationError):
        InvestigationReport(
            summary="Unsupported conclusion.",
            verified_facts=[Finding(statement="Payment is settled.", source_record_ids=[])],
            supporting_evidence=[],
            hypotheses=[],
            contradicting_evidence=[],
            missing_information=[],
            confidence="high",
            recommended_resolution="Close the exception.",
            human_review_required=True,
        )


def test_investigation_evaluator_rejects_unknown_source_references():
    from app.modules.reconciliation.investigation.evaluators import evaluate_report

    report = InvestigationReport(
        summary="A payment appears settled.",
        verified_facts=[Finding(statement="Transaction exists.", source_record_ids=["forged-id"])],
        supporting_evidence=[],
        hypotheses=[],
        contradicting_evidence=[],
        missing_information=[],
        confidence="high",
        recommended_resolution="Review the source transaction.",
        human_review_required=False,
    )
    with pytest.raises(ValueError, match="outside its authorized evidence"):
        evaluate_report(report, {"available_record_ids": ["known-id"]})
