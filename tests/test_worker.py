import mongomock
import pytest

from insightbot.config import Settings
from insightbot.flows.worker import WorkerService
from insightbot.models.article import ArticleRevision, compute_content_hash
from insightbot.models.job import JobStatus
from insightbot.models.source import Source


@pytest.fixture
def mock_worker_env(tmp_path):
    client = mongomock.MongoClient()
    db = client["test_worker_db"]
    settings = Settings(
        raw_storage_path=tmp_path / "raw",
        export_storage_path=tmp_path / "exports",
    )
    worker = WorkerService(db=db, settings=settings, worker_id="test_worker_1")
    return db, worker, settings


def test_worker_skips_disabled_source(mock_worker_env):
    db, worker, _ = mock_worker_env

    # Register disabled source
    disabled_source = Source(
        source_id="aljazeera_ar",
        name="Al Jazeera Arabic",
        url="https://aljazeera.net",
        feed_urls=["https://aljazeera.net/rss.xml"],
        enabled=False,
    )
    worker.source_repo.upsert_source(disabled_source)

    # Queue ingestion job
    job = worker.job_repo.create_job(kind="ingest_source", target_id="aljazeera_ar")

    # Worker executes job
    processed_job = worker.process_one_job()
    assert processed_job is not None
    assert processed_job.job_id == job.job_id
    # Must be marked SKIPPED_DISABLED
    assert processed_job.status == JobStatus.SKIPPED_DISABLED
    assert "disabled by policy" in processed_job.result_data["reason"]


def test_worker_reconciles_article(mock_worker_env):
    db, worker, _ = mock_worker_env

    # Create article in repo
    article, _ = worker.article_repo.save_article_with_version(
        source_id="bbc_en",
        canonical_url="https://bbc.com/news/article1",
        original_url="https://bbc.com/news/article1",
        resolved_url="https://bbc.com/news/article1",
        title="Initial Title",
        body_text="Initial Body Content",
    )
    assert article.current_version == 1

    # Simulate a crash where version 2 was inserted into article_versions but pointer stalled
    rev2 = ArticleRevision(
        article_id=article.article_id,
        version=2,
        title="Updated Title V2",
        body_text="Updated Body V2",
        content_hash=compute_content_hash("Updated Body V2"),
        operation="update",
    )
    worker.article_repo.versions.insert_one(rev2.model_dump())

    # Queue reconciliation job
    worker.job_repo.create_job(kind="reconcile_article", target_id=article.article_id)

    # Worker processes reconciliation job
    processed_job = worker.process_one_job()
    assert processed_job is not None
    assert processed_job.status == JobStatus.COMPLETED

    # Verify article pointer advanced to version 2
    reconciled_art = worker.article_repo.get_by_id(article.article_id)
    assert reconciled_art.current_version == 2
    assert reconciled_art.title == "Updated Title V2"


def test_worker_run_bounded(mock_worker_env):
    db, worker, _ = mock_worker_env

    # Queue 3 jobs
    for i in range(3):
        src = Source(
            source_id=f"src_{i}",
            name=f"Source {i}",
            url=f"https://src{i}.com",
            enabled=False,
        )
        worker.source_repo.upsert_source(src)
        worker.job_repo.create_job(kind="ingest_source", target_id=f"src_{i}")

    # Process bounded up to 2
    count = worker.run_bounded(max_jobs=2)
    assert count == 2

    # Exactly 1 job remains pending
    remaining_pending = worker.job_repo.jobs.count_documents({"status": JobStatus.PENDING.value})
    assert remaining_pending == 1
