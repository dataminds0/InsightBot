"""Authentication and authorization business service."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from insightbot.infra.security import (
    generate_session_token,
    hash_password,
    verify_and_upgrade_password,
)
from insightbot.models.user import Role, Session, User, UserStatus
from insightbot.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

SESSION_IDLE_TIMEOUT = timedelta(minutes=60)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


class AuthenticationError(Exception):
    """Raised on authentication failures (invalid credentials, pending approval, etc.)."""

    pass


class AuthorizationError(Exception):
    """Raised on unauthorized actions or security guard violations."""

    pass


class AuthService:
    """Authentication, authorization, and session lifecycle coordinator."""

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def register(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        role: Role = Role.VIEWER,
        status: UserStatus = UserStatus.PENDING,
    ) -> User:
        """Register a new user account."""
        clean_username = username.strip()
        if not clean_username or len(clean_username) < 3:
            raise AuthenticationError("Username must be at least 3 characters long.")

        if not password or len(password) < 8:
            raise AuthenticationError("Password must be at least 8 characters long.")

        if self.user_repo.get_by_username(clean_username):
            raise AuthenticationError(f"Username '{clean_username}' is already registered.")

        clean_email = email.strip().lower() if email else None
        if clean_email and self.user_repo.get_by_email(clean_email):
            raise AuthenticationError(f"Email '{clean_email}' is already registered.")

        pw_hash = hash_password(password)
        user = User(
            username=clean_username,
            email=clean_email,
            password_hash=pw_hash,
            role=role,
            status=status,
        )
        return self.user_repo.create_user(user)

    def login(self, username: str, password: str) -> tuple[User, Session]:
        """Authenticate user credentials and initiate session."""
        user = self.user_repo.get_by_username(username.strip())
        if not user:
            raise AuthenticationError("Invalid username or password.")

        is_valid, upgraded_hash = verify_and_upgrade_password(password, user.password_hash)
        if not is_valid:
            raise AuthenticationError("Invalid username or password.")

        # If password hash was upgraded from legacy bcrypt to Argon2id, persist it
        if upgraded_hash:
            logger.info("Upgrading password hash to Argon2id for user '%s'", user.username)
            self.user_repo.update_password_hash(user.user_id, upgraded_hash)

        # Enforce account status guards
        if user.status == UserStatus.PENDING:
            raise AuthenticationError("Account registration is pending administrator approval.")
        if user.status == UserStatus.DISABLED:
            raise AuthenticationError("Account is disabled. Contact system administrator.")

        # Create session
        now = _ensure_utc(datetime.now(timezone.utc))
        session = Session(
            user_id=user.user_id,
            session_token=generate_session_token(),
            role=user.role,
            created_at=now,
            expires_at=now + SESSION_IDLE_TIMEOUT,
            last_activity_at=now,
        )
        self.user_repo.create_session(session)
        self.user_repo.update_last_login(user.user_id)

        return user, session

    def logout(self, session_token: str) -> bool:
        """Terminate active session."""
        return self.user_repo.delete_session(session_token)

    def validate_session(
        self, session_token: str, extend_idle: bool = True
    ) -> tuple[User, Session]:
        """
        Validate active session.
        If extend_idle is False (e.g. background polling), idle expiration is NOT extended.
        """
        session = self.user_repo.get_session(session_token)
        if not session:
            raise AuthenticationError("Invalid or expired session.")

        now = _ensure_utc(datetime.now(timezone.utc))
        if _ensure_utc(session.expires_at) < now:
            self.user_repo.delete_session(session_token)
            raise AuthenticationError("Session expired.")

        # Ensure user is still active in database
        user = self.user_repo.get_by_id(session.user_id)
        if not user or user.status != UserStatus.ACTIVE:
            self.user_repo.delete_session(session_token)
            raise AuthenticationError("User account is inactive or disabled.")

        # If role changed in DB, immediately reflect on session or revoke
        if session.role != user.role:
            self.user_repo.delete_session(session_token)
            raise AuthenticationError("User permissions modified. Please sign in again.")

        if extend_idle:
            new_expires = now + SESSION_IDLE_TIMEOUT
            self.user_repo.touch_session(session_token, new_expires)
            session.expires_at = new_expires
            session.last_activity_at = now

        return user, session

    def change_user_role(self, admin_user: User, target_user_id: str, new_role: Role) -> User:
        """Promote or demote user role with last-admin guard and immediate session revocation."""
        if admin_user.role != Role.ADMIN:
            raise AuthorizationError("Only administrators can modify roles.")

        target = self.user_repo.get_by_id(target_user_id)
        if not target:
            raise AuthorizationError(f"Target user '{target_user_id}' not found.")

        # Last-admin guard
        if target.role == Role.ADMIN and new_role != Role.ADMIN:
            if self.user_repo.count_active_admins() <= 1:
                raise AuthorizationError("Cannot demote the last remaining active administrator.")

        self.user_repo.update_role(target_user_id, new_role)
        # Immediate revocation: drop all active sessions for this user so privileges take effect immediately
        revoked_count = self.user_repo.delete_user_sessions(target_user_id)
        logger.info(
            "Admin '%s' changed role for '%s' to '%s'; revoked %d active session(s).",
            admin_user.username,
            target.username,
            new_role.value,
            revoked_count,
        )

        target.role = new_role
        return target

    def change_user_status(
        self, admin_user: User, target_user_id: str, new_status: UserStatus
    ) -> User:
        """Activate, approve, or disable user account with last-admin guard and immediate session revocation."""
        if admin_user.role != Role.ADMIN:
            raise AuthorizationError("Only administrators can modify account status.")

        target = self.user_repo.get_by_id(target_user_id)
        if not target:
            raise AuthorizationError(f"Target user '{target_user_id}' not found.")

        # Last-admin guard
        if target.role == Role.ADMIN and new_status != UserStatus.ACTIVE:
            if self.user_repo.count_active_admins() <= 1:
                raise AuthorizationError("Cannot disable the last remaining active administrator.")

        self.user_repo.update_status(target_user_id, new_status)
        if new_status != UserStatus.ACTIVE:
            revoked_count = self.user_repo.delete_user_sessions(target_user_id)
            logger.info(
                "Admin '%s' set status '%s' for '%s'; revoked %d active session(s).",
                admin_user.username,
                new_status.value,
                target.username,
                revoked_count,
            )

        target.status = new_status
        return target
