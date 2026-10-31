"""SQL Server-backed identity and tenant-isolation API tests."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import app
from app.modules.businesses.models import Business, BusinessMembership
from app.modules.identity.models import User


@pytest.fixture
def api_context() -> Iterator[tuple[TestClient, str]]:
    email_prefix = f"phase2-{uuid4().hex}"
    client = TestClient(app)
    yield client, email_prefix
    with Session(get_engine()) as db:
        users = list(db.scalars(select(User).where(User.email.like(f"{email_prefix}%"))).all())
        user_ids = [user.id for user in users]
        if user_ids:
            business_ids = list(
                db.scalars(
                    select(Business.id).where(Business.created_by_user_id.in_(user_ids))
                ).all()
            )
            db.execute(
                delete(BusinessMembership).where(
                    BusinessMembership.user_id.in_(user_ids)
                    | BusinessMembership.business_id.in_(business_ids)
                )
            )
            if business_ids:
                db.execute(delete(Business).where(Business.id.in_(business_ids)))
            db.execute(delete(User).where(User.id.in_(user_ids)))
            db.commit()


def register_and_login(client: TestClient, email: str, name: str) -> str:
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": name, "password": "Strong-Test-Password-2026!"},
    )
    assert registered.status_code == 201, registered.text
    assert "password_hash" not in registered.json()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Strong-Test-Password-2026!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_registration_login_profile_password_change_and_duplicate_email(api_context) -> None:
    client, prefix = api_context
    email = f"{prefix}-user@example.com"

    assert client.get("/api/v1/users/me").status_code == 401
    token = register_and_login(client, email, "Test User")
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.get("/api/v1/users/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["email"] == email
    assert (
        client.patch(
            "/api/v1/users/me", headers=headers, json={"full_name": "Updated Name"}
        ).json()["full_name"]
        == "Updated Name"
    )

    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "email": email.upper(),
            "full_name": "Duplicate",
            "password": "Strong-Test-Password-2026!",
        },
    )
    assert duplicate.status_code == 409

    changed = client.put(
        "/api/v1/users/me/password",
        headers=headers,
        json={
            "current_password": "Strong-Test-Password-2026!",
            "new_password": "Another-Strong-Password-2026!",
        },
    )
    assert changed.status_code == 204
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "Strong-Test-Password-2026!"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "Another-Strong-Password-2026!"}
        ).status_code
        == 200
    )


def test_business_membership_scopes_access_and_roles(api_context) -> None:
    client, prefix = api_context
    owner_email = f"{prefix}-owner@example.com"
    outsider_email = f"{prefix}-outsider@example.com"
    owner_token = register_and_login(client, owner_email, "Owner")
    outsider_token = register_and_login(client, outsider_email, "Outsider")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

    business_a = client.post("/api/v1/businesses", headers=owner_headers, json={"name": "Tenant A"})
    business_b = client.post(
        "/api/v1/businesses", headers=outsider_headers, json={"name": "Tenant B"}
    )
    assert business_a.status_code == business_b.status_code == 201
    id_a = business_a.json()["id"]
    id_b = business_b.json()["id"]
    assert business_a.json()["role"] == "owner"

    assert client.get(f"/api/v1/businesses/{id_a}", headers=owner_headers).status_code == 200
    assert client.get(f"/api/v1/businesses/{id_b}", headers=owner_headers).status_code == 404
    assert (
        client.get(f"/api/v1/businesses/{id_b}/members", headers=owner_headers).status_code == 404
    )
    assert (
        client.patch(
            f"/api/v1/businesses/{id_b}", headers=owner_headers, json={"name": "Tampered"}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/businesses").status_code == 401

    added = client.post(
        f"/api/v1/businesses/{id_a}/members",
        headers=owner_headers,
        json={"email": outsider_email, "role": "member"},
    )
    assert added.status_code == 201
    assert client.get(f"/api/v1/businesses/{id_a}", headers=outsider_headers).status_code == 200
    assert (
        client.patch(
            f"/api/v1/businesses/{id_a}",
            headers=outsider_headers,
            json={"name": "Member cannot edit"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/businesses/{id_a}/members",
            headers=outsider_headers,
            json={"email": owner_email, "role": "admin"},
        ).status_code
        == 403
    )

    assert (
        client.delete(
            f"/api/v1/businesses/{id_a}/members/{business_a.json()['created_by_user_id']}",
            headers=owner_headers,
        ).status_code
        == 409
    )
