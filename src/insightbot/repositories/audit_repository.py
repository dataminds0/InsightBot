"""Repository for recording and querying immutable audit trail logs."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.database import Database

from insightbot.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditRepository:
    """Repository handling audit events and compliance tracking."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.collection = db["audit_logs"]

    def record(
        self,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """Create and store an immutable audit log entry."""
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            created_at=datetime.now(timezone.utc),
        )
        self.collection.insert_one(entry.model_dump())
        logger.info(
            "Audit event: actor='%s', action='%s', entity='%s:%s'",
            actor_id,
            action,
            entity_type,
            entity_id,
        )
        return entry

    def list_logs(
        self,
        skip: int = 0,
        limit: int = 50,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> list[AuditLog]:
        """Query audit log entries ordered by creation timestamp descending."""
        query: dict[str, Any] = {}
        if action:
            query["action"] = action
        if entity_type:
            query["entity_type"] = entity_type

        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        results: list[AuditLog] = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(AuditLog.model_validate(doc))
        return results

    def count_logs(self, action: Optional[str] = None, entity_type: Optional[str] = None) -> int:
        """Count matching audit entries."""
        query: dict[str, Any] = {}
        if action:
            query["action"] = action
        if entity_type:
            query["entity_type"] = entity_type
        return self.collection.count_documents(query)
