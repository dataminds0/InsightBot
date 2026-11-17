"""Source expansion batches management with reversibility guarantees."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from pymongo.database import Database

from insightbot.repositories.audit_repository import AuditRepository
from insightbot.repositories.source_repository import SourceRepository


class SourceBatchStatus(str, Enum):
    """Lifecycle statuses for source expansion batches."""

    DRAFT = "draft"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    PAUSED = "paused"


class SourceBatch(BaseModel):
    """Source expansion batch definition with audit metadata."""

    batch_id: str
    name: str
    description: str = ""
    source_ids: list[str] = Field(default_factory=list)
    status: SourceBatchStatus = SourceBatchStatus.DRAFT
    review_signoff_by: str = "editorial_team"
    review_notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: Optional[datetime] = None
    rolled_back_at: Optional[datetime] = None
    rollback_reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceBatchManager:
    """
    Manages reviewed batches of sources with reversible rollout and rollback controls.
    Ensures that newly onboarded source groups can be deployed and completely rolled back
    without affecting baseline sources or risking system destabilization.
    """

    def __init__(self, db: Database[dict[str, Any]], audit_repo: Optional[AuditRepository] = None):
        self.db = db
        self.collection = db["source_batches"]
        self.source_repo = SourceRepository(db)
        self.audit_repo = audit_repo or AuditRepository(db)

    def register_batch(self, batch: SourceBatch) -> SourceBatch:
        """Register or update a source expansion batch."""
        data = batch.model_dump()
        self.collection.update_one(
            {"batch_id": batch.batch_id},
            {"$set": data},
            upsert=True,
        )
        # Tag associated sources with this batch_id if they exist
        for sid in batch.source_ids:
            self.db["sources"].update_one(
                {"source_id": sid},
                {"$set": {"batch_id": batch.batch_id, "review_status": "reviewed"}},
            )
        return batch

    def get_batch(self, batch_id: str) -> Optional[SourceBatch]:
        """Fetch a batch by its unique ID."""
        doc = self.collection.find_one({"batch_id": batch_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return SourceBatch.model_validate(doc)

    def list_batches(self) -> list[SourceBatch]:
        """List all source expansion batches."""
        cursor = self.collection.find({}).sort("created_at", -1)
        batches: list[SourceBatch] = []
        for doc in cursor:
            doc.pop("_id", None)
            batches.append(SourceBatch.model_validate(doc))
        return batches

    def activate_batch(self, batch_id: str, operator_username: str) -> int:
        """
        Activate all sources in a reviewed batch.
        Guarantees that all sources in the batch become enabled atomically.
        """
        batch = self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Source expansion batch '{batch_id}' not found.")

        now = datetime.now(timezone.utc)
        # Enable all sources belonging to this batch
        count = self.source_repo.set_batch_enabled(batch_id, True)

        # Update batch status
        self.collection.update_one(
            {"batch_id": batch_id},
            {
                "$set": {
                    "status": SourceBatchStatus.ACTIVE.value,
                    "activated_at": now,
                    "rollback_reason": None,
                }
            },
        )

        self.audit_repo.record(
            actor_id=operator_username,
            action="source_batch_activated",
            entity_type="source_batch",
            entity_id=batch_id,
            details={"activated_sources_count": count, "source_ids": batch.source_ids},
        )
        return count

    def rollback_batch(self, batch_id: str, operator_username: str, reason: str) -> int:
        """
        Reversible safety action: atomically deactivate all sources in the batch.
        If an expanded batch causes increased errors, rate-limiting, or memory pressure,
        this operation instantly halts collection for all batch sources without collateral impact.
        """
        batch = self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Source expansion batch '{batch_id}' not found.")

        now = datetime.now(timezone.utc)
        count = self.source_repo.set_batch_enabled(batch_id, False)

        self.collection.update_one(
            {"batch_id": batch_id},
            {
                "$set": {
                    "status": SourceBatchStatus.ROLLED_BACK.value,
                    "rolled_back_at": now,
                    "rollback_reason": reason,
                }
            },
        )

        self.audit_repo.record(
            actor_id=operator_username,
            action="source_batch_rolled_back",
            entity_type="source_batch",
            entity_id=batch_id,
            details={
                "deactivated_sources_count": count,
                "reason": reason,
                "source_ids": batch.source_ids,
            },
        )
        return count
