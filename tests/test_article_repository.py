from datetime import datetime, timezone

import mongomock
import pytest

from insightbot.models.article import ArticleRevision, compute_content_hash
from insightbot.repositories.article_repository import ArticleRepository


@pytest.fixture
def repo():
    client = mongomock.MongoClient()
    db = client["test_insightbot"]
    return ArticleRepository(db)


def test_save_new_article(repo):
    article, is_new = repo.save_article_with_version(
        source_id="aljazeera",
        canonical_url="https://aljazeera.net/article/1",
        original_url="https://aljazeera.net/article/1",
        resolved_url="https://aljazeera.net/article/1",
        title="تقرير أولي",
        body_text="محتوى التقرير الأول بالتفصيل.",
        language="ar",
        published_at=datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),
    )
    assert is_new is True
    assert article.current_version == 1
    assert article.fencing_token == 1
    assert article.title == "تقرير أولي"

    # Verify immutable revision was saved
    versions = repo.get_versions(article.article_id)
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].title == "تقرير أولي"


def test_save_identical_content_is_idempotent(repo):
    # Initial save
    art1, is_new1 = repo.save_article_with_version(
        source_id="aljazeera",
        canonical_url="https://aljazeera.net/article/1",
        original_url="https://aljazeera.net/article/1",
        resolved_url="https://aljazeera.net/article/1",
        title="تقرير أولي",
        body_text="محتوى التقرير الأول.",
    )
    assert is_new1 is True
    assert art1.current_version == 1

    # Second save with identical content
    art2, is_new2 = repo.save_article_with_version(
        source_id="aljazeera",
        canonical_url="https://aljazeera.net/article/1",
        original_url="https://aljazeera.net/article/1",
        resolved_url="https://aljazeera.net/article/1",
        title="تقرير أولي",
        body_text="محتوى التقرير الأول.",
    )
    assert is_new2 is False
    assert art2.current_version == 1

    # Only 1 revision in database
    versions = repo.get_versions(art1.article_id)
    assert len(versions) == 1


def test_save_modified_content_creates_new_version(repo):
    # Initial save
    art1, _ = repo.save_article_with_version(
        source_id="aljazeera",
        canonical_url="https://aljazeera.net/article/1",
        original_url="https://aljazeera.net/article/1",
        resolved_url="https://aljazeera.net/article/1",
        title="تقرير أولي",
        body_text="محتوى مسودة أولي.",
    )

    # Save revised text from publisher
    art2, is_new2 = repo.save_article_with_version(
        source_id="aljazeera",
        canonical_url="https://aljazeera.net/article/1",
        original_url="https://aljazeera.net/article/1",
        resolved_url="https://aljazeera.net/article/1",
        title="تقرير محدث ومصحح",
        body_text="محتوى التقرير بعد التحديث والتدقيق.",
        operation="correction",
    )
    assert is_new2 is True
    assert art2.current_version == 2
    assert art2.fencing_token == 2
    assert art2.title == "تقرير محدث ومصحح"

    # Both immutable revisions exist
    versions = repo.get_versions(art1.article_id)
    assert len(versions) == 2
    assert versions[0].version == 1
    assert versions[0].title == "تقرير أولي"
    assert versions[1].version == 2
    assert versions[1].title == "تقرير محدث ومصحح"
    assert versions[1].operation == "correction"


def test_reconciliation_advances_crashed_pointer(repo):
    # Simulate a crash where version 2 was committed in article_versions
    # but the pointer update in articles did not execute.
    art, _ = repo.save_article_with_version(
        source_id="reuters",
        canonical_url="https://reuters.com/article/99",
        original_url="https://reuters.com/article/99",
        resolved_url="https://reuters.com/article/99",
        title="Headline V1",
        body_text="Body content V1",
    )
    assert art.current_version == 1

    # Directly insert revision 2 without updating article pointer
    rev2 = ArticleRevision(
        article_id=art.article_id,
        version=2,
        title="Headline V2 Updated",
        body_text="Body content V2 Updated",
        content_hash=compute_content_hash("Body content V2 Updated"),
        operation="update",
    )
    repo.versions.insert_one(rev2.model_dump())

    # Before reconciliation, article pointer still says version 1
    stale_art = repo.get_by_id(art.article_id)
    assert stale_art.current_version == 1

    # Run reconciliation
    reconciled = repo.reconcile_article_version(art.article_id)
    assert reconciled is not None
    assert reconciled.current_version == 2
    assert reconciled.title == "Headline V2 Updated"
    assert reconciled.body_text == "Body content V2 Updated"
