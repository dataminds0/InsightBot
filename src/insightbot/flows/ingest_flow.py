"""Ingestion orchestration flow replacing legacy shell and notebook subprocesses."""

import logging
from typing import Any, Optional

from pymongo.database import Database

from insightbot.config import Settings
from insightbot.models.source import Source
from insightbot.modules.ingestion.service import IngestionService, IngestRunReport
from insightbot.repositories.source_repository import SourceRepository

logger = logging.getLogger(__name__)


def run_source_ingestion_task(
    db: Database[dict[str, Any]],
    settings: Settings,
    source: Source,
    limit: int = 10,
    ignore_disabled: bool = False,
) -> IngestRunReport:
    """
    Execute bounded, idempotent ingestion for an approved source.
    Safely respects disabled-by-default status.
    """
    service = IngestionService(db=db, settings=settings)
    report = service.ingest_source(source=source, limit=limit, ignore_disabled=ignore_disabled)
    return report


def run_ingestion_pipeline(
    db: Database[dict[str, Any]],
    settings: Settings,
    source_ids: Optional[list[str]] = None,
    limit_per_source: int = 10,
) -> list[IngestRunReport]:
    """
    Run ingestion across configured sources.
    Replaces the legacy Prefect subprocess/notebook execution pattern with native Python service calls.
    """
    source_repo = SourceRepository(db)
    all_sources = source_repo.list_sources(enabled_only=False)

    if source_ids:
        sources_to_run = [s for s in all_sources if s.source_id in source_ids]
    else:
        sources_to_run = all_sources

    reports: list[IngestRunReport] = []
    for source in sources_to_run:
        report = run_source_ingestion_task(
            db=db,
            settings=settings,
            source=source,
            limit=limit_per_source,
        )
        reports.append(report)

    return reports
