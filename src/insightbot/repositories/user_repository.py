"""User, authentication, and session persistence repository."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.database import Database

from insightbot.models.user import Role, Session, User, UserStatus

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository managing user accounts and authenticated sessions."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.users = db["users"]
        self.sessions = db["sessions"]

    def create_user(self, user: User) -> User:
        """Insert a new user document."""
        data = user.model_dump()
        self.users.insert_one(data)
        return user

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Fetch user by unique user_id."""
        doc = self.users.find_one({"user_id": user_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return User.model_validate(doc)

    def get_by_username(self, username: str) -> Optional[User]:
        """Fetch user by unique username (case-insensitive search)."""
        doc = self.users.find_one({"username": {"$regex": f"^{username}$", "$options": "i"}})
        if not doc:
            return None
        doc.pop("_id", None)
        return User.model_validate(doc)

    def get_by_email(self, email: str) -> Optional[User]:
        """Fetch user by unique email."""
        if not email:
            return None
        doc = self.users.find_one({"email": email.strip().lower()})
        if not doc:
            return None
        doc.pop("_id", None)
        return User.model_validate(doc)

    def list_users(self, skip: int = 0, limit: int = 50) -> list[User]:
        """List user accounts with pagination."""
        cursor = self.users.find().sort("created_at", -1).skip(skip).limit(limit)
        users = []
        for doc in cursor:
            doc.pop("_id", None)
            users.append(User.model_validate(doc))
        return users

    def update_password_hash(self, user_id: str, new_hash: str) -> bool:
        """Update user password hash (used during password changes and transparent upgrades)."""
        res = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"password_hash": new_hash, "updated_at": datetime.now(timezone.utc)}},
        )
        return res.modified_count > 0

    def update_role(self, user_id: str, new_role: Role) -> bool:
        """Update role for a user."""
        res = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"role": new_role.value, "updated_at": datetime.now(timezone.utc)}},
        )
        return res.modified_count > 0

    def update_status(self, user_id: str, new_status: UserStatus) -> bool:
        """Update activation status for a user."""
        res = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"status": new_status.value, "updated_at": datetime.now(timezone.utc)}},
        )
        return res.modified_count > 0

    def update_last_login(self, user_id: str) -> None:
        """Record login timestamp."""
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_login_at": datetime.now(timezone.utc)}},
        )

    def count_active_admins(self) -> int:
        """Count active users with ADMIN role."""
        return self.users.count_documents(
            {"role": Role.ADMIN.value, "status": UserStatus.ACTIVE.value}
        )

    # --- Session Management ---

    def create_session(self, session: Session) -> Session:
        """Store a new authenticated user session."""
        data = session.model_dump()
        self.sessions.insert_one(data)
        return session

    def get_session(self, session_token: str) -> Optional[Session]:
        """Retrieve an active session by token."""
        doc = self.sessions.find_one({"session_token": session_token})
        if not doc:
            return None
        doc.pop("_id", None)
        return Session.model_validate(doc)

    def touch_session(self, session_token: str, new_expires_at: datetime) -> bool:
        """Extend session idle expiry and record activity."""
        res = self.sessions.update_one(
            {"session_token": session_token},
            {
                "$set": {
                    "expires_at": new_expires_at,
                    "last_activity_at": datetime.now(timezone.utc),
                }
            },
        )
        return res.modified_count > 0

    def delete_session(self, session_token: str) -> bool:
        """Invalidate a single session."""
        res = self.sessions.delete_one({"session_token": session_token})
        return res.deleted_count > 0

    def delete_user_sessions(self, user_id: str) -> int:
        """Invalidate all active sessions for a user (used upon role change or disable)."""
        res = self.sessions.delete_many({"user_id": user_id})
        return res.deleted_count
