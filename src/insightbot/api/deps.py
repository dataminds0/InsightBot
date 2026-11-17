"""FastAPI dependency injection providers for database and authentication."""

from typing import Any, Callable, Generator

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from pymongo.database import Database

from insightbot.config import Settings, get_settings
from insightbot.infra.mongo import get_mongo_client
from insightbot.models.user import Role, User
from insightbot.modules.deduplication.service import DeduplicationService
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.audit_repository import AuditRepository
from insightbot.repositories.duplicate_repository import DuplicateRepository
from insightbot.repositories.job_repository import JobRepository
from insightbot.repositories.source_repository import SourceRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.repositories.workspace_repository import WorkspaceRepository
from insightbot.services.auth_service import AuthenticationError, AuthService


def get_db(
    settings: Settings = Depends(get_settings),
) -> Generator[Database[dict[str, Any]], None, None]:
    """Dependency yielding MongoDB database instance."""
    client = get_mongo_client(settings)
    try:
        yield client[settings.mongo_db]
    finally:
        client.close()


def get_user_repository(db: Database[dict[str, Any]] = Depends(get_db)) -> UserRepository:
    """Dependency providing UserRepository."""
    return UserRepository(db)


def get_auth_service(user_repo: UserRepository = Depends(get_user_repository)) -> AuthService:
    """Dependency providing AuthService."""
    return AuthService(user_repo)


def get_article_repository(
    db: Database[dict[str, Any]] = Depends(get_db),
) -> ArticleRepository:
    """Dependency providing ArticleRepository."""
    return ArticleRepository(db)


def get_source_repository(
    db: Database[dict[str, Any]] = Depends(get_db),
) -> SourceRepository:
    """Dependency providing SourceRepository."""
    return SourceRepository(db)


def get_job_repository(
    db: Database[dict[str, Any]] = Depends(get_db),
) -> JobRepository:
    """Dependency providing JobRepository."""
    return JobRepository(db)


def get_audit_repository(
    db: Database[dict[str, Any]] = Depends(get_db),
) -> AuditRepository:
    """Dependency providing AuditRepository."""
    return AuditRepository(db)


def get_workspace_repository(
    db: Database[dict[str, Any]] = Depends(get_db),
) -> WorkspaceRepository:
    """Dependency providing WorkspaceRepository."""
    return WorkspaceRepository(db)


def get_duplicate_repository(
    db: Database[dict[str, Any]] = Depends(get_db),
) -> DuplicateRepository:
    """Dependency providing DuplicateRepository."""
    return DuplicateRepository(db)


def get_deduplication_service(
    db: Database[dict[str, Any]] = Depends(get_db),
) -> DeduplicationService:
    """Dependency providing DeduplicationService."""
    return DeduplicationService(db)


def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
    insightbot_session: str | None = Cookie(None),
    x_background_poll: str | None = Header(None, alias="X-Background-Poll"),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """
    Extract and validate authenticated user from Authorization header or cookie.
    If X-Background-Poll is set, session idle timeout is NOT extended.
    """
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif insightbot_session:
        token = insightbot_session.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Do not extend session idle lifetime during background polling
    extend_idle = x_background_poll != "1"

    try:
        user, _ = auth_service.validate_session(token, extend_idle=extend_idle)
        return user
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(allowed_roles: set[Role]) -> Callable[[User], User]:
    """Factory creating endpoint dependencies enforcing user role capabilities."""

    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires one of roles: {[r.value for r in allowed_roles]}.",
            )
        return user

    return role_checker


require_viewer = require_role({Role.VIEWER, Role.ANALYST, Role.ADMIN})
require_analyst = require_role({Role.ANALYST, Role.ADMIN})
require_admin = require_role({Role.ADMIN})
