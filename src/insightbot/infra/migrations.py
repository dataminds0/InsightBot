"""Database index specifications, collision detection, and migration engine."""

import logging
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)


class IndexCollisionError(Exception):
    """Raised when duplicate documents prevent creation of a unique index."""

    def __init__(
        self, collection: str, keys: list[str], colliding_count: int, samples: list[dict[str, Any]]
    ):
        self.collection = collection
        self.keys = keys
        self.colliding_count = colliding_count
        self.samples = samples
        msg = (
            f"Index collision on collection '{collection}' for keys {keys}: "
            f"found {colliding_count} duplicate groups. Migration halted. "
            f"Unique constraints cannot be weakened. Sample collisions: {samples[:3]}"
        )
        super().__init__(msg)


INDEX_SPECS: dict[str, list[dict[str, Any]]] = {
    "articles": [
        {
            "keys": [("source_id", ASCENDING), ("canonical_url", ASCENDING)],
            "name": "idx_articles_source_canonical_unique",
            "unique": True,
        },
        {
            "keys": [("published_at", DESCENDING), ("article_id", ASCENDING)],
            "name": "idx_articles_published_pagination",
        },
        {
            "keys": [("content_hash", ASCENDING)],
            "name": "idx_articles_content_hash",
        },
        {
            "keys": [("fetched_at", DESCENDING)],
            "name": "idx_articles_fetched_at",
        },
    ],
    "article_versions": [
        {
            "keys": [("article_id", ASCENDING), ("version", ASCENDING)],
            "name": "idx_versions_article_version_unique",
            "unique": True,
        },
        {
            "keys": [("article_id", ASCENDING), ("content_hash", ASCENDING)],
            "name": "idx_versions_article_hash",
        },
    ],
    "sources": [
        {
            "keys": [("source_id", ASCENDING)],
            "name": "idx_sources_source_id_unique",
            "unique": True,
        },
    ],
    "fetches": [
        {
            "keys": [("source_id", ASCENDING), ("fetched_at", DESCENDING)],
            "name": "idx_fetches_source_fetched",
        },
        {
            "keys": [("url", ASCENDING)],
            "name": "idx_fetches_url",
        },
    ],
    "users": [
        {
            "keys": [("username", ASCENDING)],
            "name": "idx_users_username_unique",
            "unique": True,
        },
        {
            "keys": [("email", ASCENDING)],
            "name": "idx_users_email_partial_unique",
            "unique": True,
            "partialFilterExpression": {"email": {"$type": "string"}},
        },
    ],
    "sessions": [
        {
            "keys": [("session_token", ASCENDING)],
            "name": "idx_sessions_token_unique",
            "unique": True,
        },
        {
            "keys": [("expires_at", ASCENDING)],
            "name": "idx_sessions_ttl",
            "expireAfterSeconds": 0,
        },
    ],
    "audit_logs": [
        {
            "keys": [
                ("entity_type", ASCENDING),
                ("entity_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            "name": "idx_audit_logs_entity",
        },
    ],
    "jobs": [
        {
            "keys": [("job_id", ASCENDING)],
            "name": "idx_jobs_id_unique",
            "unique": True,
        },
        {
            "keys": [
                ("status", ASCENDING),
                ("lease_expires_at", ASCENDING),
                ("kind", ASCENDING),
            ],
            "name": "idx_jobs_claim_candidates",
        },
        {
            "keys": [("target_id", ASCENDING), ("kind", ASCENDING)],
            "name": "idx_jobs_target_kind",
        },
    ],
    "bookmarks": [
        {
            "keys": [("user_id", ASCENDING), ("article_id", ASCENDING)],
            "name": "idx_bookmarks_user_article_unique",
            "unique": True,
        },
        {
            "keys": [("user_id", ASCENDING), ("created_at", DESCENDING)],
            "name": "idx_bookmarks_user_created",
        },
    ],
    "saved_queries": [
        {
            "keys": [("query_id", ASCENDING)],
            "name": "idx_saved_queries_id_unique",
            "unique": True,
        },
        {
            "keys": [("user_id", ASCENDING), ("created_at", DESCENDING)],
            "name": "idx_saved_queries_user_created",
        },
    ],
    "private_notes": [
        {
            "keys": [("user_id", ASCENDING), ("article_id", ASCENDING)],
            "name": "idx_notes_user_article_unique",
            "unique": True,
        },
        {
            "keys": [("user_id", ASCENDING), ("updated_at", DESCENDING)],
            "name": "idx_notes_user_updated",
        },
    ],
    "duplicate_relationships": [
        {
            "keys": [
                ("canonical_article_id", ASCENDING),
                ("duplicate_article_id", ASCENDING),
            ],
            "name": "idx_dup_rel_canonical_duplicate_unique",
            "unique": True,
        },
        {
            "keys": [("duplicate_article_id", ASCENDING)],
            "name": "idx_dup_rel_duplicate",
        },
        {
            "keys": [("canonical_article_id", ASCENDING)],
            "name": "idx_dup_rel_canonical",
        },
        {
            "keys": [("duplicate_type", ASCENDING)],
            "name": "idx_dup_rel_type",
        },
        {
            "keys": [("detected_at", DESCENDING)],
            "name": "idx_dup_rel_detected_at",
        },
    ],
}


def find_unique_index_collisions(
    db: Database[dict[str, Any]], collection_name: str, keys: list[tuple[str, int]]
) -> list[dict[str, Any]]:
    """Check for duplicate records that would violate a unique index before creation."""
    coll = db[collection_name]
    group_id: dict[str, str] = {k: f"${k}" for k, _ in keys}

    pipeline: list[dict[str, Any]] = [
        {"$group": {"_id": group_id, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 10},
    ]

    try:
        results = list(coll.aggregate(pipeline))
        return results
    except OperationFailure:
        # If collection does not exist yet, no collisions can exist
        return []


def plan_migrations(db: Database[dict[str, Any]]) -> dict[str, Any]:
    """Inspect current database indexes and plan additions/modifications."""
    existing_collections = db.list_collection_names()
    plan: dict[str, Any] = {
        "to_create": [],
        "already_exists": [],
        "collisions": [],
    }

    for coll_name, specs in INDEX_SPECS.items():
        existing_index_names: set[str] = set()
        if coll_name in existing_collections:
            for idx_info in db[coll_name].list_indexes():
                existing_index_names.add(idx_info["name"])

        for spec in specs:
            idx_name = spec["name"]
            is_unique = spec.get("unique", False)
            keys = spec["keys"]

            if idx_name in existing_index_names:
                plan["already_exists"].append({"collection": coll_name, "index": idx_name})
                continue

            # Check collision if unique
            if is_unique and coll_name in existing_collections:
                collisions = find_unique_index_collisions(db, coll_name, keys)
                if collisions:
                    plan["collisions"].append(
                        {
                            "collection": coll_name,
                            "index": idx_name,
                            "keys": [k for k, _ in keys],
                            "sample_duplicates": collisions,
                        }
                    )

            plan["to_create"].append(
                {
                    "collection": coll_name,
                    "index": idx_name,
                    "keys": keys,
                    "unique": is_unique,
                    "options": {k: v for k, v in spec.items() if k not in ("keys", "name")},
                }
            )

    return plan


def apply_migrations(db: Database[dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    """Apply planned indexes to database, halting on any collision."""
    plan = plan_migrations(db)

    if plan["collisions"]:
        first = plan["collisions"][0]
        raise IndexCollisionError(
            collection=first["collection"],
            keys=first["keys"],
            colliding_count=len(first["sample_duplicates"]),
            samples=first["sample_duplicates"],
        )

    if dry_run:
        return {
            "status": "dry_run",
            "planned_creations": len(plan["to_create"]),
            "already_present": len(plan["already_exists"]),
            "details": plan["to_create"],
        }

    applied: list[str] = []
    for item in plan["to_create"]:
        coll = db[item["collection"]]
        options = dict(item["options"])
        coll.create_index(
            item["keys"],
            name=item["index"],
            **options,
        )
        applied.append(f"{item['collection']}.{item['index']}")

    return {
        "status": "applied",
        "created_count": len(applied),
        "created_indexes": applied,
        "already_present_count": len(plan["already_exists"]),
    }
