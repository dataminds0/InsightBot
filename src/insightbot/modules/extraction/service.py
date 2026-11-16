"""Extraction coordinator service."""

import logging
from typing import Any, Optional

from pymongo.database import Database

from insightbot.models.article import Article
from insightbot.modules.extraction.extractor import ArticleExtractor
from insightbot.modules.extraction.models import ExtractedArticle
from insightbot.repositories.article_repository import ArticleRepository

logger = logging.getLogger(__name__)


class ExtractionService:
    """Orchestrates content extraction from raw HTML and article version persistence."""

    def __init__(self, db: Database[dict[str, Any]], extractor: Optional[ArticleExtractor] = None):
        self.db = db
        self.article_repo = ArticleRepository(db)
        self.extractor = extractor or ArticleExtractor()

    def process_raw_html(
        self,
        html_content: str,
        source_id: str,
        canonical_url: str,
        original_url: str,
        resolved_url: str,
        fallback_title: Optional[str] = None,
        fallback_date: Optional[Any] = None,
        language: str = "ar",
        raw_storage_key: Optional[str] = None,
    ) -> tuple[Article, ExtractedArticle]:
        """
        Extract article from raw HTML and persist it and its immutable revision in ArticleRepository.
        Ensures full body text is preserved and colons in titles are not truncated.
        """
        extracted = self.extractor.extract_from_html(
            html_content=html_content,
            url=canonical_url,
            fallback_title=fallback_title,
            fallback_date=fallback_date,
            language=language,
        )

        article, _ = self.article_repo.save_article_with_version(
            source_id=source_id,
            canonical_url=canonical_url,
            original_url=original_url,
            resolved_url=resolved_url,
            title=extracted.title,
            body_text=extracted.body_text,
            language=extracted.language,
            published_at=extracted.published_at,
            publication_date_unknown_reason=extracted.publication_date_unknown_reason,
            operation="initial_extraction",
            raw_storage_key=raw_storage_key,
        )

        # Update extraction stage status and quarantine reason if any
        if extracted.quarantine_reason:
            self.article_repo.articles.update_one(
                {"article_id": article.article_id},
                {
                    "$set": {
                        "quarantine_reason": extracted.quarantine_reason,
                        "stage_states.extraction": "quarantined",
                    }
                },
            )
            article.quarantine_reason = extracted.quarantine_reason
            article.stage_states["extraction"] = "quarantined"
        else:
            self.article_repo.articles.update_one(
                {"article_id": article.article_id},
                {"$set": {"stage_states.extraction": "completed"}},
            )
            article.stage_states["extraction"] = "completed"

        return article, extracted
