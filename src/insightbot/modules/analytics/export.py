"""Export Service for generating bounded CSV, JSONL, and Markdown with formula injection defense."""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.export import (
    ExportFormat,
    ExportManifest,
    ExportTarget,
)

logger = logging.getLogger(__name__)

# Dangerous characters triggering formula execution in spreadsheet software
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "%")


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitizes cell contents against CSV Formula Injection (CWE-1236).
    If a string begins with dangerous formula triggers (=, +, -, @, \t, \r, %),
    it is safely neutralized by prepending a single quote (').
    """
    if value is None:
        return ""
    s = str(value)
    if s.startswith(FORMULA_PREFIXES):
        return f"'{s}"
    return s


class ExportService:
    """Handles bounded data exports in CSV, JSONL, and Markdown formats."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.articles_coll = db["articles"]
        self.stories_coll = db["stories"]
        self.manifests_coll = db["export_manifests"]

    def export_articles(
        self,
        export_format: ExportFormat,
        query: str | None = None,
        source_id: str | None = None,
        language: str | None = None,
        limit: int = 500,
    ) -> tuple[str, str, ExportManifest]:
        """
        Exports articles in requested format with CSV formula protection,
        strict memory bounding (max 1000 items), and source display policy compliance.
        Returns: (content_string, media_type, manifest)
        """
        safe_limit = max(1, min(limit, 1000))
        filter_query: dict[str, Any] = {}

        if source_id:
            filter_query["source_id"] = source_id
        if language:
            filter_query["language"] = language
        if query:
            filter_query["$text"] = {"$search": query}

        # Safe projection (omits unbounded body_text to prevent OOM & respect source policies)
        cursor = self.articles_coll.find(
            filter_query,
            {
                "_id": 0,
                "article_id": 1,
                "source_id": 1,
                "canonical_url": 1,
                "title": 1,
                "language": 1,
                "published_at": 1,
                "publication_date_unknown_reason": 1,
                "fetched_at": 1,
                "current_version": 1,
                "word_count": 1,
                "reading_time_minutes": 1,
            },
        ).sort("fetched_at", -1).limit(safe_limit)

        items = list(cursor)

        manifest = ExportManifest(
            target=ExportTarget.ARTICLES,
            format=export_format,
            total_exported=len(items),
            filters_applied={
                "query": query,
                "source_id": source_id,
                "language": language,
                "limit": safe_limit,
            },
            formula_protection_applied=True,
            source_policy_enforced=True,
        )
        self.manifests_coll.insert_one(manifest.model_dump())

        if export_format == ExportFormat.CSV:
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
            # Headers
            headers = [
                "article_id",
                "source_id",
                "title",
                "language",
                "published_at",
                "publication_date_unknown_reason",
                "fetched_at",
                "canonical_url",
                "word_count",
                "reading_time_minutes",
                "version",
            ]
            writer.writerow(headers)

            for art in items:
                pub_str = (
                    art["published_at"].isoformat()
                    if isinstance(art.get("published_at"), datetime)
                    else (art.get("published_at") or "")
                )
                fetch_str = (
                    art["fetched_at"].isoformat()
                    if isinstance(art.get("fetched_at"), datetime)
                    else (art.get("fetched_at") or "")
                )

                row = [
                    sanitize_csv_cell(art.get("article_id")),
                    sanitize_csv_cell(art.get("source_id")),
                    sanitize_csv_cell(art.get("title")),
                    sanitize_csv_cell(art.get("language")),
                    sanitize_csv_cell(pub_str),
                    sanitize_csv_cell(art.get("publication_date_unknown_reason")),
                    sanitize_csv_cell(fetch_str),
                    sanitize_csv_cell(art.get("canonical_url")),
                    sanitize_csv_cell(art.get("word_count")),
                    sanitize_csv_cell(art.get("reading_time_minutes")),
                    sanitize_csv_cell(art.get("current_version", 1)),
                ]
                writer.writerow(row)

            return output.getvalue(), "text/csv; charset=utf-8", manifest

        elif export_format == ExportFormat.JSONL:
            lines: list[str] = []
            for art in items:
                # Convert datetime to isoformat
                doc = dict(art)
                if isinstance(doc.get("published_at"), datetime):
                    doc["published_at"] = doc["published_at"].isoformat()
                if isinstance(doc.get("fetched_at"), datetime):
                    doc["fetched_at"] = doc["fetched_at"].isoformat()
                lines.append(json.dumps(doc, ensure_ascii=False))

            return "\n".join(lines), "application/x-ndjson; charset=utf-8", manifest

        else:  # MARKDOWN
            lines = [
                f"# تقرير تصدير مقالات InsightBot ({len(items)} مقال)",
                f"*تاريخ التوليد: {manifest.generated_at.strftime('%Y-%m-%d %H:%M UTC')}*",
                f"*معرف التصدير: `{manifest.export_id}`*",
                "",
                "| المعرف | المصدر | اللغة | تاريخ النشر | العنوان والتوثيق |",
                "|---|---|---|---|---|",
            ]
            for art in items:
                pub = (
                    art["published_at"].strftime("%Y-%m-%d %H:%M")
                    if isinstance(art.get("published_at"), datetime)
                    else "غير محدد"
                )
                title = (art.get("title") or "").replace("|", "-")
                url = art.get("canonical_url", "")
                link = f"[{title}]({url})" if url else title
                lines.append(
                    f"| `{art.get('article_id', '')}` | {art.get('source_id', '')} | {art.get('language', '')} | {pub} | {link} |"
                )

            return "\n".join(lines), "text/markdown; charset=utf-8", manifest

    def export_stories(
        self,
        export_format: ExportFormat,
        status: str | None = None,
        limit: int = 100,
    ) -> tuple[str, str, ExportManifest]:
        """
        Exports story event clusters in requested format.
        """
        safe_limit = max(1, min(limit, 500))
        filter_query: dict[str, Any] = {}
        if status:
            filter_query["status"] = status

        cursor = self.stories_coll.find(
            filter_query,
            {
                "_id": 0,
                "story_id": 1,
                "title": 1,
                "status": 1,
                "sources": 1,
                "article_count": 1,
                "sources_count": 1,
                "first_article_at": 1,
                "last_article_at": 1,
                "version": 1,
                "keywords": 1,
            },
        ).sort("last_article_at", -1).limit(safe_limit)

        items = list(cursor)

        manifest = ExportManifest(
            target=ExportTarget.STORIES,
            format=export_format,
            total_exported=len(items),
            filters_applied={"status": status, "limit": safe_limit},
        )
        self.manifests_coll.insert_one(manifest.model_dump())

        if export_format == ExportFormat.CSV:
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
            headers = [
                "story_id",
                "title",
                "status",
                "sources",
                "article_count",
                "sources_count",
                "first_article_at",
                "last_article_at",
                "version",
            ]
            writer.writerow(headers)

            for s in items:
                first_str = (
                    s["first_article_at"].isoformat()
                    if isinstance(s.get("first_article_at"), datetime)
                    else (s.get("first_article_at") or "")
                )
                last_str = (
                    s["last_article_at"].isoformat()
                    if isinstance(s.get("last_article_at"), datetime)
                    else (s.get("last_article_at") or "")
                )
                sources_str = ", ".join(s.get("sources", []))

                row = [
                    sanitize_csv_cell(s.get("story_id")),
                    sanitize_csv_cell(s.get("title")),
                    sanitize_csv_cell(s.get("status")),
                    sanitize_csv_cell(sources_str),
                    sanitize_csv_cell(s.get("article_count")),
                    sanitize_csv_cell(s.get("sources_count")),
                    sanitize_csv_cell(first_str),
                    sanitize_csv_cell(last_str),
                    sanitize_csv_cell(s.get("version", 1)),
                ]
                writer.writerow(row)

            return output.getvalue(), "text/csv; charset=utf-8", manifest

        elif export_format == ExportFormat.JSONL:
            lines: list[str] = []
            for s in items:
                doc = dict(s)
                if isinstance(doc.get("first_article_at"), datetime):
                    doc["first_article_at"] = doc["first_article_at"].isoformat()
                if isinstance(doc.get("last_article_at"), datetime):
                    doc["last_article_at"] = doc["last_article_at"].isoformat()
                lines.append(json.dumps(doc, ensure_ascii=False))
            return "\n".join(lines), "application/x-ndjson; charset=utf-8", manifest

        else:  # MARKDOWN
            lines = [
                f"# تقرير قصص وأحداث InsightBot ({len(items)} قصة)",
                f"*تاريخ التوليد: {manifest.generated_at.strftime('%Y-%m-%d %H:%M UTC')}*",
                f"*معرف التصدير: `{manifest.export_id}`*",
                "",
                "| المعرف | الحالة | المقالات | المصادر | العنوان |",
                "|---|---|---|---|---|",
            ]
            for s in items:
                title = (s.get("title") or "").replace("|", "-")
                srcs = ", ".join(s.get("sources", []))
                lines.append(
                    f"| `{s.get('story_id', '')}` | {s.get('status', '')} | {s.get('article_count', 0)} | {srcs} | {title} |"
                )
            return "\n".join(lines), "text/markdown; charset=utf-8", manifest
