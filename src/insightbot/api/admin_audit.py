"""Administrator audit log inspection endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from insightbot.api.deps import get_audit_repository, require_admin
from insightbot.models.audit import AuditLog
from insightbot.models.user import User
from insightbot.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/api/admin/audit-logs", tags=["Admin Audit"])


@router.get("", response_model=list[AuditLog])
def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action name"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> list[AuditLog]:
    """Retrieve chronological audit trail of administrative actions (Admin only)."""
    return audit_repo.list_logs(skip=skip, limit=limit, action=action, entity_type=entity_type)
