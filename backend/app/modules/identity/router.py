"""Registration, login, and user self-service endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.modules.identity.dependencies import CurrentUser, DbSession
from app.modules.identity.schemas import (
    PasswordUpdate,
    TokenRead,
    UserCreate,
    UserLogin,
    UserRead,
    UserUpdate,
)
from app.modules.identity.security import create_access_token
from app.modules.identity.service import (
    authenticate_user,
    register_user,
    update_password,
    update_user,
)

router = APIRouter(prefix="/api/v1", tags=["identity"])


@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: DbSession) -> UserRead:
    return register_user(db, data)


@router.post("/auth/login", response_model=TokenRead)
def login(data: UserLogin, db: DbSession) -> TokenRead:
    user = authenticate_user(db, str(data.email), data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(user.id)
    return TokenRead(access_token=token, expires_in=expires_in)


@router.get("/users/me", response_model=UserRead)
def read_profile(user: CurrentUser) -> UserRead:
    return user


@router.patch("/users/me", response_model=UserRead)
def patch_profile(data: UserUpdate, db: DbSession, user: CurrentUser) -> UserRead:
    if data.email is None and data.full_name is None:
        raise HTTPException(status_code=422, detail="Provide email or full_name to update")
    return update_user(db, user, data)


@router.put("/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(data: PasswordUpdate, db: DbSession, user: CurrentUser) -> None:
    update_password(db, user, data)
