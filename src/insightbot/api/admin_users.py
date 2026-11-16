"""Administrator user management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from insightbot.api.auth import UserResponse
from insightbot.api.deps import get_auth_service, get_user_repository, require_admin
from insightbot.models.user import Role, User, UserStatus
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthorizationError, AuthService

router = APIRouter(prefix="/api/admin/users", tags=["Admin Users"])


class UpdateRoleRequest(BaseModel):
    role: Role


class UpdateStatusRequest(BaseModel):
    status: UserStatus


@router.get("", response_model=list[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    admin: User = Depends(require_admin),
    user_repo: UserRepository = Depends(get_user_repository),
) -> list[UserResponse]:
    """List all registered users (Admin only)."""
    users = user_repo.list_users(skip=skip, limit=limit)
    return [
        UserResponse(
            user_id=u.user_id,
            username=u.username,
            email=u.email,
            role=u.role.value,
            status=u.status.value,
        )
        for u in users
    ]


@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: str,
    req: UpdateRoleRequest,
    admin: User = Depends(require_admin),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Change user role with last-admin guard and immediate session revocation (Admin only)."""
    try:
        updated = auth_service.change_user_role(
            admin_user=admin,
            target_user_id=user_id,
            new_role=req.role,
        )
        return UserResponse(
            user_id=updated.user_id,
            username=updated.username,
            email=updated.email,
            role=updated.role.value,
            status=updated.status.value,
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: str,
    req: UpdateStatusRequest,
    admin: User = Depends(require_admin),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Approve, activate, or disable user account with last-admin guard (Admin only)."""
    try:
        updated = auth_service.change_user_status(
            admin_user=admin,
            target_user_id=user_id,
            new_status=req.status,
        )
        return UserResponse(
            user_id=updated.user_id,
            username=updated.username,
            email=updated.email,
            role=updated.role.value,
            status=updated.status.value,
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
