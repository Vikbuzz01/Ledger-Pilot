"""Request authentication and business membership authorization."""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.businesses.models import BusinessMembership
from app.modules.identity.models import User
from app.modules.identity.security import decode_access_token

DbSession = Annotated[Session, Depends(get_db_session)]
bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_business_membership(
    business_id: UUID,
    db: DbSession,
    user: CurrentUser,
    allowed_roles: set[str] | None = None,
) -> BusinessMembership:
    membership = db.scalar(
        select(BusinessMembership).where(
            BusinessMembership.business_id == business_id,
            BusinessMembership.user_id == user.id,
        )
    )
    # Conceal whether another business exists from nonmembers.
    if membership is None:
        raise HTTPException(status_code=404, detail="Business not found")
    if allowed_roles is not None and membership.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient business role")
    return membership
