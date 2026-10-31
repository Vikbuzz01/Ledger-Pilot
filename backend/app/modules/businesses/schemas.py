"""Validated business and membership request/response schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BusinessRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class BusinessUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_by_user_id: UUID
    created_at: datetime
    role: BusinessRole


class MembershipCreate(BaseModel):
    email: EmailStr
    role: BusinessRole = BusinessRole.MEMBER


class MembershipUpdate(BaseModel):
    role: BusinessRole


class MembershipRead(BaseModel):
    business_id: UUID
    user_id: UUID
    email: EmailStr
    full_name: str
    role: BusinessRole
    created_at: datetime
