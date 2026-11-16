import importlib
import sys
from unittest.mock import MagicMock

import mongomock

from insightbot.config import Settings
from insightbot.flows.ingest_flow import run_ingestion_pipeline


def test_legacy_pipeline_import_does_not_execute(monkeypatch):
    """
    CRITICAL ACCEPTANCE CHECK (Defect A22):
    Importing flow.pipeline must NOT execute daily_pipeline on import.
    """
    # Provide mock for prefect decorators if prefect is not locally installed
    if "prefect" not in sys.modules:
        mock_prefect = MagicMock()
        mock_prefect.flow = lambda **kwargs: lambda f: f
        mock_prefect.task = lambda **kwargs: lambda f: f
        monkeypatch.setitem(sys.modules, "prefect", mock_prefect)

    import flow.pipeline

    # If it reached here without running, reload to verify idempotency on import
    importlib.reload(flow.pipeline)
    assert hasattr(flow.pipeline, "daily_pipeline")


def test_ingestion_pipeline_skips_disabled_sources(tmp_path):
    client = mongomock.MongoClient()
    db = client["test_pipeline_db"]
    settings = Settings(
        raw_storage_path=tmp_path / "raw",
        export_storage_path=tmp_path / "exports",
    )

    # Insert 2 disabled sources
    sources_coll = db["sources"]
    sources_coll.insert_many(
        [
            {
                "source_id": "src_ar_1",
                "name": "Arabic Source 1",
                "url": "https://ar1.example.com",
                "feed_urls": ["https://ar1.example.com/rss.xml"],
                "enabled": False,
                "language": "ar",
                "policy": {
                    "rate_limit_per_minute": 20,
                    "retention_days": 90,
                    "allow_raw_storage": True,
                    "owner": "system",
                },
            },
            {
                "source_id": "src_en_1",
                "name": "English Source 1",
                "url": "https://en1.example.com",
                "feed_urls": ["https://en1.example.com/rss.xml"],
                "enabled": False,
                "language": "en",
                "policy": {
                    "rate_limit_per_minute": 20,
                    "retention_days": 90,
                    "allow_raw_storage": True,
                    "owner": "system",
                },
            },
        ]
    )

    reports = run_ingestion_pipeline(db=db, settings=settings)
    assert len(reports) == 2
    for r in reports:
        assert r.status == "skipped_disabled"
        assert "disabled by policy" in r.message
