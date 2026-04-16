import hashlib
import os
from typing import Optional

from sqlalchemy import select

from lib.sql_db import get_session
from db.models.user import User


class UserRepository:
    """
    Repository for admin users stored in SQL (MySQL or SQLite).
    All users are global admins — no role or account restrictions.
    """

    @staticmethod
    def _hash(password: str) -> str:
        salt = os.getenv("PASSWORD_SALT", "qa_chat_tester_salt_v1")
        return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, email: str, password: str, name: str = None) -> int:
        with get_session() as session:
            user = User(
                email=email,
                password=self._hash(password),
                name=name or email.split("@")[0],
                must_change_password=True,
            )
            session.add(user)
            session.flush()
            return user.user_id

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_by_email(self, email: str) -> Optional[dict]:
        with get_session() as session:
            user = session.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            return user.to_dict() if user else None

    def get_by_id(self, user_id: int) -> Optional[dict]:
        with get_session() as session:
            user = session.execute(
                select(User).where(User.user_id == user_id)
            ).scalar_one_or_none()
            return user.to_dict() if user else None

    def get_all(self) -> list[dict]:
        with get_session() as session:
            users = session.execute(
                select(User).order_by(User.created_at)
            ).scalars().all()
            return [u.to_dict() for u in users]

    # ── Validate ──────────────────────────────────────────────────────────────

    def validate_login(self, email: str, password: str) -> Optional[dict]:
        user = self.get_by_email(email)
        if not user:
            return None
        if user["password"] == self._hash(password):
            return user
        return None

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, user_id: int, **fields) -> None:
        allowed = {"name", "email"}
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                for key, val in to_update.items():
                    setattr(user, key, val)

    def change_password(self, user_id: int, new_password: str) -> None:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.password = self._hash(new_password)

    def clear_must_change_password(self, user_id: int) -> None:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.must_change_password = False

    def set_must_change_password(self, user_id: int) -> None:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.must_change_password = True

    # ── Delete ────────────────────────────────────────────────────────────────

    def deactivate(self, user_id: int) -> None:
        """Hard delete — removes the user from the database."""
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                session.delete(user)
