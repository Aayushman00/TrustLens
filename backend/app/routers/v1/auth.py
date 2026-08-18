"""Auth routes — login, refresh (public), and /me (Bearer). Phase 5."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserRead
from app.schemas.common import ErrorResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Exchange email + password for a JWT access + refresh token pair.",
    responses={401: {"model": ErrorResponse}},
)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return AuthService(db).login(body.email, body.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchange a refresh token for a new (rotated) access + refresh pair.",
    responses={401: {"model": ErrorResponse}},
)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return AuthService(db).refresh(body.refresh_token)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Current user",
    description="Return the authenticated user (never includes password_hash).",
    responses={401: {"model": ErrorResponse}},
)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
