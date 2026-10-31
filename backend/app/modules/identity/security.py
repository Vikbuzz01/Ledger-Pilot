"""Password hashing and short-lived signed access tokens."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hasher = PasswordHash.recommended()
_DUMMY_HASH = password_hasher.hash("ledgerpilot-invalid-user-password")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    return password_hasher.verify(password, password_hash or _DUMMY_HASH)


def create_access_token(user_id: UUID) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.access_token_minutes * 60
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
            "iss": "ledgerpilot",
            "aud": "ledgerpilot-web",
            "type": "access",
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_in


def decode_access_token(token: str) -> UUID:
    settings = get_settings()
    claims = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=["HS256"],
        issuer="ledgerpilot",
        audience="ledgerpilot-web",
        options={"require": ["sub", "exp", "iat", "iss", "aud", "type"]},
    )
    if claims["type"] != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return UUID(claims["sub"])
