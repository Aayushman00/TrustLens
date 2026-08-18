"""AuthService — login, refresh rotation, and access-token → user resolution."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.errors import UnauthorizedError
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.models import User
from app.db.repositories.user import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, session: Session) -> None:
        self._users = UserRepository(session)

    def _issue_token_pair(self, user: User) -> TokenResponse:
        settings = get_settings()
        return TokenResponse(
            access_token=create_access_token(user.id, user.role),
            refresh_token=create_refresh_token(user.id),
            token_type="bearer",
            expires_in=settings.jwt_access_expire_minutes * 60,
        )

    def login(self, email: str, password: str) -> TokenResponse:
        user = self._users.get_by_email(email)
        # Generic message on both "no such user" and "wrong password" — never
        # reveal whether an email is registered.
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")
        return self._issue_token_pair(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")
        user = self._load_user_from_sub(payload.get("sub"))
        if user is None:
            raise UnauthorizedError("Invalid refresh token")
        return self._issue_token_pair(user)

    def get_user_from_access_token(self, token: str) -> User:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid access token")
        user = self._load_user_from_sub(payload.get("sub"))
        if user is None:
            raise UnauthorizedError("Invalid access token")
        return user

    def _load_user_from_sub(self, sub: str | None) -> User | None:
        if not sub:
            return None
        try:
            user_id = int(sub)
        except ValueError:
            return None
        return self._users.get_by_id(user_id)
