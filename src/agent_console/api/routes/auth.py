"""Registration, login, logout, and the current-user probe."""

from fastapi import APIRouter, HTTPException, Response, status

from agent_console.api.dependencies import (
    CurrentUserDep,
    PasswordHasherDep,
    SessionTokenDep,
    SettingsDep,
    UserRepositoryDep,
    clear_session_cookie,
    set_session_cookie,
)
from agent_console.repositories.users import EmailTakenError
from agent_console.schemas.auth import LoginRequest, RegisterRequest, UserResponse

__all__ = ["router"]

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    users: UserRepositoryDep,
    hasher: PasswordHasherDep,
    tokens: SessionTokenDep,
    settings: SettingsDep,
) -> UserResponse:
    # The first account becomes admin, otherwise a fresh install has no way in.
    first = settings.first_user_is_admin and await users.count() == 0

    try:
        user = await users.create(
            email=payload.email,
            display_name=payload.display_name,
            password_hash=hasher.hash(payload.password),
            is_admin=first,
        )
    except EmailTakenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    set_session_cookie(response, tokens.issue(str(user.id)), settings)
    return UserResponse.model_validate(user)


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    users: UserRepositoryDep,
    hasher: PasswordHasherDep,
    tokens: SessionTokenDep,
    settings: SettingsDep,
) -> UserResponse:
    user = await users.by_email(payload.email)

    # Same message and same work either way: a distinct "no such account"
    # response would let anyone enumerate who has signed up.
    if user is None or not hasher.verify(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this account is disabled")

    if hasher.needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(payload.password)

    set_session_cookie(response, tokens.issue(str(user.id)), settings)
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    # Must mutate the injected response; returning a fresh one would throw away
    # the Set-Cookie header that actually clears the session.
    clear_session_cookie(response)


@router.get("/me")
async def me(user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(user)
