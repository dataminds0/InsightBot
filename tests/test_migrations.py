import mongomock
import pytest

from insightbot.infra.migrations import (
    IndexCollisionError,
    apply_migrations,
    plan_migrations,
)


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["test_insightbot_migrations"]


def test_migration_plan_empty_db(mock_db):
    plan = plan_migrations(mock_db)
    assert len(plan["to_create"]) > 0
    assert len(plan["already_exists"]) == 0
    assert len(plan["collisions"]) == 0


def test_migration_dry_run(mock_db):
    report = apply_migrations(mock_db, dry_run=True)
    assert report["status"] == "dry_run"
    assert report["planned_creations"] > 0
    # No collections created during dry run
    assert len(mock_db.list_collection_names()) == 0


def test_migration_apply_creates_indexes(mock_db):
    report = apply_migrations(mock_db, dry_run=False)
    assert report["status"] == "applied"
    assert report["created_count"] > 0

    # Running migrations a second time should recognize they already exist
    second_report = apply_migrations(mock_db, dry_run=False)
    assert second_report["created_count"] == 0
    assert second_report["already_present_count"] > 0


def test_migration_halts_on_duplicate_collision(mock_db):
    # Pre-populate articles collection with 2 colliding records with the same source_id and canonical_url
    articles = mock_db["articles"]
    duplicate_url = "https://example.com/duplicate-story"
    articles.insert_many(
        [
            {
                "article_id": "art-1",
                "source_id": "test_source",
                "canonical_url": duplicate_url,
                "title": "Article 1",
            },
            {
                "article_id": "art-2",
                "source_id": "test_source",
                "canonical_url": duplicate_url,
                "title": "Article 2 (Duplicate)",
            },
        ]
    )

    # Attempting migration must halt and raise IndexCollisionError
    with pytest.raises(IndexCollisionError) as exc_info:
        apply_migrations(mock_db, dry_run=False)

    err = exc_info.value
    assert err.collection == "articles"
    assert "source_id" in err.keys
    assert "canonical_url" in err.keys
    assert err.colliding_count >= 1
    assert "Unique constraints cannot be weakened" in str(err)
