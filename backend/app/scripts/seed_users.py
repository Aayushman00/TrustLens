"""Idempotent dev user seeding.

Usage (inside the api container or with DATABASE_URL set)::

    python -m app.scripts.seed_users

Seeds one user per role, skipping any email that already exists. Passwords
default to fixed dev-only values (see table below) and can be overridden via
environment variables — override them for anything beyond local development.
"""

from __future__ import annotations

import os
import sys

from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import hash_password
from app.db.enums import UserRole
from app.db.repositories.user import UserRepository

# (email, role, env var override, dev-only default password)
SEED_USERS: list[tuple[str, UserRole, str, str]] = [
    ("admin@trustlens.local", UserRole.ADMIN, "SEED_ADMIN_PASSWORD", "trustlens-admin-dev"),
    (
        "researcher@trustlens.local",
        UserRole.RESEARCHER,
        "SEED_RESEARCHER_PASSWORD",
        "trustlens-researcher-dev",
    ),
    (
        "reviewer@trustlens.local",
        UserRole.REVIEWER,
        "SEED_REVIEWER_PASSWORD",
        "trustlens-reviewer-dev",
    ),
]


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set — cannot seed users", file=sys.stderr)
        return 1

    with get_session(settings.database_url) as session:
        repo = UserRepository(session)
        for email, role, env_var, default_password in SEED_USERS:
            if repo.get_by_email(email) is not None:
                print(f"skip (already exists): {email}")
                continue
            password = os.environ.get(env_var, default_password)
            repo.create(email=email, password_hash=hash_password(password), role=role)
            print(f"created: {email} (role={role.value})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
