"""End-to-end portable SQLite checks using only synthetic financial records."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import app


@pytest.fixture
def sqlite_demo(monkeypatch):
    data_root = Path(__file__).resolve().parents[1] / "storage" / f"test-{uuid4().hex}"
    database = data_root / "demo.sqlite3"
    uploads = data_root / "private-uploads"
    monkeypatch.setenv("DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(database))
    monkeypatch.setenv("JWT_SECRET_KEY", "sqlite-test-secret-key-which-is-at-least-32-chars")
    monkeypatch.setenv("DOCUMENT_STORAGE_ROOT", str(uploads))
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    client = TestClient(app)
    yield client, database
    get_session_factory.cache_clear()
    engine = get_engine()
    engine.dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()
    import shutil

    shutil.rmtree(data_root, ignore_errors=True)


def _invoice_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Northwind Office Supply")
    page.insert_text((72, 100), "Invoice Number: NW-1001")
    page.insert_text((72, 125), "Invoice Date: 2026-10-01")
    page.insert_text((72, 150), "Currency: USD")
    page.insert_text((72, 175), "Total Due: $125.50")
    result = document.tobytes()
    document.close()
    return result


def test_sqlite_schema_precision_and_complete_core_workflow(sqlite_demo):
    client, database = sqlite_demo
    with get_engine().connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert (
            connection.execute(text("SELECT version FROM ledgerpilot_schema_info")).scalar_one()
            == "20261101_0006"
        )
        assert database.exists()

    email = "sqlite-demo-test@example.com"
    password = "Strong-SQLite-Demo-Password-2026!"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "SQLite Demo", "password": password},
    )
    assert registered.status_code == 201, registered.text
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert token.status_code == 200, token.text
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    business = client.post("/api/v1/businesses", headers=headers, json={"name": "Demo Ledger"})
    assert business.status_code == 201, business.text
    business_id = business.json()["id"]
    prefix = f"/api/v1/businesses/{business_id}"

    bank_csv = (
        b"Date,Description,Amount,Currency,Reference\n"
        b"2026-10-02,Northwind Supply,-125.50,USD,NW-1001\n"
        b"2026-10-03,Unknown Merchant,-12.34,USD,UNMATCHED-1\n"
    )
    bank = client.post(
        prefix + "/documents",
        headers=headers,
        data={"document_type": "bank_csv"},
        files={
            "file": (
                "synthetic.csv",
                bank_csv,
                "text/csv",
            )
        },
    )
    assert bank.status_code == 201, bank.text
    repeated = client.post(
        prefix + "/documents",
        headers=headers,
        data={"document_type": "bank_csv"},
        files={"file": ("repeat.csv", bank_csv, "text/csv")},
    )
    assert repeated.status_code == 200 and repeated.json()["duplicate"] is True
    bank_id = bank.json()["document"]["id"]
    bank_detail = client.get(prefix + f"/documents/{bank_id}", headers=headers).json()
    assert [Decimal(row["amount"]) for row in bank_detail["transactions"]] == [
        Decimal("-125.50"),
        Decimal("-12.34"),
    ]
    for transaction in bank_detail["transactions"]:
        assert (
            client.patch(
                prefix + f"/documents/{bank_id}/transactions/{transaction['id']}",
                headers=headers,
                json={
                    "transaction_date": transaction["transaction_date"],
                    "description": transaction["description"],
                    "amount": transaction["amount"],
                    "currency": "USD",
                },
            ).status_code
            == 200
        )

    invoice_upload = client.post(
        prefix + "/documents",
        headers=headers,
        data={"document_type": "invoice_pdf"},
        files={"file": ("synthetic.pdf", _invoice_pdf(), "application/pdf")},
    )
    assert invoice_upload.status_code == 201, invoice_upload.text
    invoice_id = invoice_upload.json()["document"]["id"]
    invoice_detail = client.get(prefix + f"/documents/{invoice_id}", headers=headers).json()
    invoice = invoice_detail["invoices"][0]
    verified = client.patch(
        prefix + f"/documents/{invoice_id}/invoices/{invoice['id']}",
        headers=headers,
        json={
            "invoice_number": invoice["invoice_number"],
            "vendor_name": invoice["vendor_name"],
            "invoice_date": invoice["invoice_date"],
            "total_amount": "125.50",
            "currency": "USD",
        },
    )
    assert verified.status_code == 200, verified.text

    run = client.post(prefix + "/reconciliation/runs", headers=headers, json={})
    assert run.status_code == 201, run.text
    candidates = client.get(
        prefix + f"/reconciliation/runs/{run.json()['id']}/candidates", headers=headers
    ).json()
    exact = next(row for row in candidates if row["matching_method"] == "exact_amount")
    decision = client.post(
        prefix + f"/reconciliation/candidates/{exact['id']}/decision",
        headers=headers,
        json={"decision": "approve", "reason": "Synthetic demo review"},
    )
    assert decision.status_code == 200, decision.text
    balances = client.get(prefix + "/reconciliation/invoice-balances", headers=headers)
    assert balances.status_code == 200
    assert Decimal(balances.json()[0]["paid_amount"]) == Decimal("125.50")
    assert Decimal(balances.json()[0]["outstanding_amount"]) == Decimal("0")

    exceptions = client.get(
        prefix + f"/reconciliation/runs/{run.json()['id']}/exceptions", headers=headers
    ).json()
    unmatched = next(
        item for item in exceptions if item["exception_type"] == "unmatched_transaction"
    )
    investigation = client.post(
        prefix + f"/reconciliation/exceptions/{unmatched['id']}/investigations", headers=headers
    )
    assert investigation.status_code == 201, investigation.text
    assert investigation.json()["status"] == "unavailable"
    assert investigation.json()["report"] is None

    assert client.get("/api/v1/businesses").status_code == 401
    assert client.get(prefix + "/reconciliation/audit", headers=headers).json()

    get_session_factory.cache_clear()
    get_engine().dispose()
    get_engine.cache_clear()
    with get_engine().connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code
        == 200
    )


def test_sqlite_rejects_legacy_or_unrecognized_database(monkeypatch):
    from sqlalchemy import create_engine

    path = Path(__file__).resolve().parents[1] / "storage" / f"legacy-{uuid4().hex}.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = create_engine(f"sqlite:///{path}")
    with legacy.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))
    legacy.dispose()
    monkeypatch.setenv("DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(path))
    monkeypatch.setenv("JWT_SECRET_KEY", "sqlite-test-secret-key-which-is-at-least-32-chars")
    get_settings.cache_clear()
    get_engine.cache_clear()
    with pytest.raises(RuntimeError, match="unrecognized schema"):
        get_engine()
    get_engine.cache_clear()
    get_settings.cache_clear()
    path.unlink(missing_ok=True)


def test_synthetic_demo_seed_is_idempotent(monkeypatch):
    import shutil

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.demo_seed import DEMO_EMAIL, seed_demo
    from app.main import app
    from app.modules.businesses.models import Business
    from app.modules.documents.models import Document
    from app.modules.financial_records.models import Invoice
    from app.modules.identity.models import User
    from app.modules.reconciliation.models import ReconciliationRun

    root = Path(__file__).resolve().parents[1] / "storage" / f"seed-test-{uuid4().hex}"
    monkeypatch.setenv("DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(root / "demo.sqlite3"))
    monkeypatch.setenv("DOCUMENT_STORAGE_ROOT", str(root / "private-documents"))
    monkeypatch.setenv("JWT_SECRET_KEY", "sqlite-test-secret-key-which-is-at-least-32-chars")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    try:
        assert seed_demo() is True
        assert seed_demo() is False
        login = TestClient(app).post(
            "/api/v1/auth/login",
            json={"email": DEMO_EMAIL, "password": "LedgerPilot-Demo-2026!"},
        )
        assert login.status_code == 200, login.text
        with Session(get_engine()) as db:
            assert (
                db.scalar(select(func.count()).select_from(User).where(User.email == DEMO_EMAIL))
                == 1
            )
            assert db.scalar(select(func.count()).select_from(Business)) == 1
            assert db.scalar(select(func.count()).select_from(Document)) == 4
            assert db.scalar(select(func.count()).select_from(Invoice)) == 3
            assert db.scalar(select(func.count()).select_from(ReconciliationRun)) == 1
    finally:
        engine = get_engine()
        engine.dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        get_settings.cache_clear()
        shutil.rmtree(root, ignore_errors=True)
