"""Tenant and membership operations; callers must authorize before entry."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.businesses.models import Business, BusinessMembership
from app.modules.businesses.schemas import (
    BusinessCreate,
    BusinessRole,
    BusinessUpdate,
    MembershipCreate,
    MembershipRead,
)
from app.modules.identity.models import User
from app.modules.identity.service import normalize_email


def list_businesses(db: Session, user_id: UUID) -> list[tuple[Business, str]]:
    rows = db.execute(
        select(Business, BusinessMembership.role)
        .join(BusinessMembership, BusinessMembership.business_id == Business.id)
        .where(BusinessMembership.user_id == user_id)
        .order_by(Business.name)
    )
    return list(rows.tuples())


def create_business(db: Session, user: User, data: BusinessCreate) -> BusinessMembership:
    business = Business(name=data.name.strip(), created_by_user_id=user.id)
    db.add(business)
    db.flush()
    membership = BusinessMembership(
        business_id=business.id,
        user_id=user.id,
        role=BusinessRole.OWNER.value,
    )
    db.add(membership)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(business)
    return membership


def update_business(db: Session, business: Business, data: BusinessUpdate) -> Business:
    business.name = data.name.strip()
    db.commit()
    db.refresh(business)
    return business


def list_members(db: Session, business_id: UUID) -> list[MembershipRead]:
    rows = db.execute(
        select(BusinessMembership, User)
        .join(User, User.id == BusinessMembership.user_id)
        .where(BusinessMembership.business_id == business_id)
        .order_by(BusinessMembership.created_at)
    )
    return [
        MembershipRead(
            business_id=membership.business_id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


def add_member(db: Session, business_id: UUID, data: MembershipCreate) -> MembershipRead:
    email = normalize_email(str(data.email))
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=404, detail="An active registered user with this email was not found"
        )
    membership = BusinessMembership(business_id=business_id, user_id=user.id, role=data.role.value)
    db.add(membership)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="User is already a member of this business"
        ) from None
    db.refresh(membership)
    return MembershipRead(
        business_id=business_id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )


def get_membership(db: Session, business_id: UUID, user_id: UUID) -> BusinessMembership:
    membership = db.get(BusinessMembership, (business_id, user_id))
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    return membership


def update_member_role(
    db: Session, membership: BusinessMembership, role: BusinessRole
) -> BusinessMembership:
    if membership.role == BusinessRole.OWNER.value or role == BusinessRole.OWNER:
        raise HTTPException(
            status_code=409, detail="Business ownership cannot be changed through this endpoint"
        )
    membership.role = role.value
    db.commit()
    db.refresh(membership)
    return membership


def remove_member(db: Session, membership: BusinessMembership) -> None:
    if membership.role == BusinessRole.OWNER.value:
        raise HTTPException(status_code=409, detail="The business owner cannot be removed")
    db.delete(membership)
    db.commit()
