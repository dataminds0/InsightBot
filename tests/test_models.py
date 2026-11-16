from datetime import datetime, timezone

from insightbot.models.article import Article, ArticleRevision, compute_content_hash
from insightbot.models.source import Source
from insightbot.models.user import Role, Session, User, UserStatus


def test_article_model_with_unknown_date():
    article = Article(
        source_id="aljazeera",
        canonical_url="https://aljazeera.net/news/123",
        original_url="https://aljazeera.net/news/123?utm_source=twitter",
        resolved_url="https://aljazeera.net/news/123",
        title="عنوان الخبر باللغة العربية",
        body_text="نص الخبر بالتفصيل بدون حذف.",
        content_hash=compute_content_hash("نص الخبر بالتفصيل بدون حذف."),
        published_at=None,
        publication_date_unknown_reason="missing_in_source_metadata",
    )
    assert article.published_at is None
    assert article.publication_date_unknown_reason == "missing_in_source_metadata"
    assert article.current_version == 1
    assert article.fencing_token == 1


def test_content_hash_normalization():
    h1 = compute_content_hash("  نص   خبر   مهم  \n")
    h2 = compute_content_hash("نص خبر مهم")
    assert h1 == h2


def test_article_revision_immutable():
    rev = ArticleRevision(
        article_id="art-123",
        version=1,
        title="العنوان الأول",
        body_text="النص الأول",
        content_hash=compute_content_hash("النص الأول"),
        operation="initial_fetch",
    )
    assert rev.version == 1
    assert rev.operation == "initial_fetch"


def test_user_and_session_roles():
    user = User(
        username="analyst_user",
        password_hash="argon2id_hash_placeholder",
        role=Role.ANALYST,
        status=UserStatus.ACTIVE,
    )
    assert user.role == Role.ANALYST
    assert user.status == UserStatus.ACTIVE

    session = Session(
        user_id=user.user_id,
        session_token="token_xyz",
        role=user.role,
        expires_at=datetime.now(timezone.utc),
    )
    assert session.role == Role.ANALYST


def test_source_policy_defaults():
    src = Source(
        source_id="bbc_arabic",
        name="BBC Arabic",
        url="https://www.bbc.com/arabic",
        feed_urls=["https://www.bbc.com/arabic/index.xml"],
        enabled=False,
    )
    assert src.enabled is False
    assert src.policy.retention_days == 90
    assert src.policy.allow_raw_storage is True
