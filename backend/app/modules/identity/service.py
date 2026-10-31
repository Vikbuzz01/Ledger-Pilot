"""Identity persistence and validation services."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.identity.models import User
from app.modules.identity.schemas import PasswordUpdate, UserCreate, UserUpdate
from app.modules.identity.security import hash_password, verify_password


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def register_user(db: Session, data: UserCreate) -> User:
    user = User(
        email=normalize_email(str(data.email)),
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not verify_password(password, user.password_hash if user else None):
        return None
    if user is None or not user.is_active:
        return None
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, data: UserUpdate) -> User:
    if data.email is not None:
        user.email = normalize_email(str(data.email))
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None
    db.refresh(user)
    return user


def update_password(db: Session, user: User, data: PasswordUpdate) -> None:
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    db.commit()
