"""Business management and membership authorization endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.modules.businesses.models import Business, BusinessMembership
from app.modules.businesses.schemas import (
    BusinessCreate,
    BusinessRead,
    BusinessRole,
    BusinessUpdate,
    MembershipCreate,
    MembershipRead,
    MembershipUpdate,
)
from app.modules.businesses.service import (
    add_member,
    create_business,
    get_membership,
    list_businesses,
    list_members,
    remove_member,
    update_business,
    update_member_role,
)
from app.modules.identity.dependencies import CurrentUser, DbSession, require_business_membership

router = APIRouter(prefix="/api/v1/businesses", tags=["businesses"])
MANAGERS = {BusinessRole.OWNER.value, BusinessRole.ADMIN.value}


def _business_read(business: Business, role: str) -> BusinessRead:
    return BusinessRead(
        id=business.id,
        name=business.name,
        created_by_user_id=business.created_by_user_id,
        created_at=business.created_at,
        role=role,
    )


@router.get("", response_model=list[BusinessRead])
def businesses(db: DbSession, user: CurrentUser) -> list[BusinessRead]:
    return [_business_read(business, role) for business, role in list_businesses(db, user.id)]


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
def create(data: BusinessCreate, db: DbSession, user: CurrentUser) -> BusinessRead:
    membership = create_business(db, user, data)
    business = db.get(Business, membership.business_id)
    assert business is not None
    return _business_read(business, membership.role)


@router.get("/{business_id}", response_model=BusinessRead)
def get_business(business_id: UUID, db: DbSession, user: CurrentUser) -> BusinessRead:
    membership = require_business_membership(business_id, db, user)
    business = db.get(Business, business_id)
    assert business is not None
    return _business_read(business, membership.role)


@router.patch("/{business_id}", response_model=BusinessRead)
def patch_business(
    business_id: UUID, data: BusinessUpdate, db: DbSession, user: CurrentUser
) -> BusinessRead:
    require_business_membership(business_id, db, user, MANAGERS)
    business = db.get(Business, business_id)
    assert business is not None
    updated = update_business(db, business, data)
    membership = db.get(BusinessMembership, (business_id, user.id))
    assert membership is not None
    return _business_read(updated, membership.role)


@router.get("/{business_id}/members", response_model=list[MembershipRead])
def members(business_id: UUID, db: DbSession, user: CurrentUser) -> list[MembershipRead]:
    require_business_membership(business_id, db, user)
    return list_members(db, business_id)


@router.post(
    "/{business_id}/members", response_model=MembershipRead, status_code=status.HTTP_201_CREATED
)
def add_business_member(
    business_id: UUID, data: MembershipCreate, db: DbSession, user: CurrentUser
) -> MembershipRead:
    actor = require_business_membership(business_id, db, user, MANAGERS)
    if actor.role == BusinessRole.ADMIN.value and data.role in {
        BusinessRole.ADMIN,
        BusinessRole.OWNER,
    }:
        raise HTTPException(status_code=403, detail="Only the owner can grant admin permissions")
    if data.role == BusinessRole.OWNER:
        raise HTTPException(status_code=409, detail="Business ownership cannot be assigned here")
    return add_member(db, business_id, data)


@router.patch("/{business_id}/members/{user_id}", response_model=MembershipRead)
def patch_member(
    business_id: UUID,
    user_id: UUID,
    data: MembershipUpdate,
    db: DbSession,
    user: CurrentUser,
) -> MembershipRead:
    actor = require_business_membership(business_id, db, user, MANAGERS)
    target = get_membership(db, business_id, user_id)
    if actor.role == BusinessRole.ADMIN.value and (
        target.role in {BusinessRole.OWNER.value, BusinessRole.ADMIN.value}
        or data.role in {BusinessRole.OWNER, BusinessRole.ADMIN}
    ):
        raise HTTPException(status_code=403, detail="Only the owner can manage admin permissions")
    updated = update_member_role(db, target, data.role)
    roster = {member.user_id: member for member in list_members(db, business_id)}
    return roster[updated.user_id]


@router.delete("/{business_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(business_id: UUID, user_id: UUID, db: DbSession, user: CurrentUser) -> None:
    actor = require_business_membership(business_id, db, user)
    target = get_membership(db, business_id, user_id)
    if user.id != user_id:
        if actor.role not in MANAGERS:
            raise HTTPException(status_code=403, detail="Insufficient business role")
        if actor.role == BusinessRole.ADMIN.value and target.role in {
            BusinessRole.OWNER.value,
            BusinessRole.ADMIN.value,
        }:
            raise HTTPException(status_code=403, detail="Only the owner can remove admins")
    remove_member(db, target)
