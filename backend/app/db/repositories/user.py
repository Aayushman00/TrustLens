"""User repository — create / read by id or email."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import UserRole
from app.db.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.RESEARCHER,
    ) -> User:
        user = User(email=email, password_hash=password_hash, role=role)
        self._session.add(user)
        self._session.flush()
        return user

    def get_by_id(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self._session.scalars(stmt).first()
