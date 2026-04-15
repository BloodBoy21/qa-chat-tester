import hashlib
import os
from typing import Optional

from sqlalchemy import select

from lib.sql_db import get_session
from db.models.user import User


class UserRepository:
    """
    Repository for admin users stored in SQL (MySQL or SQLite).
    Backend is selected automatically via DATABASE_URL in lib/sql_db.
    All users are admins — no role restrictions.
    """

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.getenv("PASSWORD_SALT", "qa_chat_tester_salt_v1")
        return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()

    def create(
        self,
        email: str,
        password: str,
        account_id: str,
        name: str = None,
    ) -> int:
        with get_session() as session:
            user = User(
                email=email,
                password_hash=self._hash_password(password),
                account_id=account_id,
                name=name,
            )
            session.add(user)
            session.flush()  # populate user_id before commit
            return user.user_id

    def get_by_email(self, email: str) -> Optional[dict]:
        with get_session() as session:
            user = session.execute(
                select(User).where(User.email == email, User.is_active.is_(True))
            ).scalar_one_or_none()
            return user.to_dict() if user else None

    def get_by_id(self, user_id: int) -> Optional[dict]:
        with get_session() as session:
            user = session.execute(
                select(User).where(User.user_id == user_id, User.is_active.is_(True))
            ).scalar_one_or_none()
            return user.to_dict() if user else None

    def get_by_account(self, account_id: str) -> list[dict]:
        with get_session() as session:
            users = session.execute(
                select(User).where(
                    User.account_id == account_id, User.is_active.is_(True)
                )
            ).scalars().all()
            return [u.to_dict() for u in users]

    def validate_login(self, email: str, password: str) -> Optional[dict]:
        """Return the user dict if credentials are valid, else None."""
        user = self.get_by_email(email)
        if not user:
            return None
        if user["password_hash"] == self._hash_password(password):
            return user
        return None

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
                user.password_hash = self._hash_password(new_password)

    def deactivate(self, user_id: int) -> None:
        """Soft-delete: set is_active = False."""
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.is_active = False
