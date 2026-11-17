"""Analytics Service generating metric contracts, coverage stats, and publishing lag reports."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.analytics import (
    AnalyticsOverviewReport,
    LanguageDistributionMetric,
    SourceCoverageMetric,
    StoryStatusDistribution,
    TimelinePoint,
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class AnalyticsService:
    """Computes aggregated metrics and reports reconciling underlying articles and stories."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.articles_coll = db["articles"]
        self.sources_coll = db["sources"]
        self.stories_coll = db["stories"]

    def get_overview_report(self) -> AnalyticsOverviewReport:
        """
        Computes complete analytics overview reconciling articles, sources, and stories.
        Strictly observes Defect A13 (unknown date counts visible) and Defect A14.
        """
        total_articles = self.articles_coll.count_documents({})
        total_sources = self.sources_coll.count_documents({})
        total_stories = self.stories_coll.count_documents({})

        # Defect A13 visible metric: count of articles with unknown publication date
        unknown_pub_date_count = self.articles_coll.count_documents(
            {"published_at": None}
        )

        # Defect A05/A06 visible metric: quarantined extraction count
        quarantined_count = self.articles_coll.count_documents(
            {"quarantine_reason": {"$ne": None}}
        )

        # 1. Source Coverage & Freshness Aggregation
        source_name_map: dict[str, str] = {}
        for s_doc in self.sources_coll.find({}, {"source_id": 1, "name": 1}):
            source_name_map[s_doc["source_id"]] = s_doc.get("name", s_doc["source_id"])

        coverage_pipeline: list[dict[str, Any]] = [
            {
                "$group": {
                    "_id": "$source_id",
                    "article_count": {"$sum": 1},
                    "avg_word_count": {"$avg": "$word_count"},
                    "avg_reading_time": {"$avg": "$reading_time_minutes"},
                    "latest_article_at": {"$max": "$fetched_at"},
                }
            },
            {"$sort": {"article_count": -1}},
        ]

        coverage_metrics: list[SourceCoverageMetric] = []
        for doc in self.articles_coll.aggregate(coverage_pipeline):
            s_id = doc["_id"] or "unknown"
            cnt = doc.get("article_count", 0)
            pct = round((cnt / total_articles * 100.0), 1) if total_articles > 0 else 0.0

            # Calculate average publishing lag for this source (where published_at is known)
            lag_pipeline: list[dict[str, Any]] = [
                {
                    "$match": {
                        "source_id": s_id,
                        "published_at": {"$ne": None},
                        "fetched_at": {"$ne": None},
                    }
                },
                {
                    "$project": {
                        "lag_minutes": {
                            "$divide": [
                                {"$subtract": ["$fetched_at", "$published_at"]},
                                1000 * 60,
                            ]
                        }
                    }
                },
                {"$group": {"_id": None, "avg_lag": {"$avg": "$lag_minutes"}}},
            ]
            lag_res = list(self.articles_coll.aggregate(lag_pipeline))
            avg_lag = (
                round(float(lag_res[0]["avg_lag"]), 1)
                if lag_res and lag_res[0].get("avg_lag") is not None
                else None
            )

            coverage_metrics.append(
                SourceCoverageMetric(
                    source_id=s_id,
                    name=source_name_map.get(s_id, s_id),
                    article_count=cnt,
                    percentage=pct,
                    average_reading_time_minutes=round(doc.get("avg_reading_time") or 1.0, 1),
                    average_word_count=round(doc.get("avg_word_count") or 0.0, 1),
                    latest_article_at=doc.get("latest_article_at"),
                    publishing_lag_minutes=avg_lag,
                )
            )

        # 2. Language Distribution Aggregation
        lang_pipeline: list[dict[str, Any]] = [
            {"$group": {"_id": "$language", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        language_metrics: list[LanguageDistributionMetric] = []
        for doc in self.articles_coll.aggregate(lang_pipeline):
            l_code = (doc["_id"] or "unknown").lower()
            cnt = doc.get("count", 0)
            pct = round((cnt / total_articles * 100.0), 1) if total_articles > 0 else 0.0
            language_metrics.append(
                LanguageDistributionMetric(language=l_code, count=cnt, percentage=pct)
            )

        # 3. Timeline Trend (Past 30 days)
        cutoff_date = utc_now() - timedelta(days=30)
        timeline_pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "$or": [
                        {"published_at": {"$gte": cutoff_date}},
                        {"fetched_at": {"$gte": cutoff_date}},
                    ]
                }
            },
            {
                "$project": {
                    "source_id": 1,
                    "date_str": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": {"$ifNull": ["$published_at", "$fetched_at"]},
                        }
                    },
                }
            },
            {
                "$group": {
                    "_id": {"date": "$date_str", "source_id": "$source_id"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.date": 1}},
        ]

        # Reorganize timeline points
        trend_map: dict[str, dict[str, int]] = {}
        for doc in self.articles_coll.aggregate(timeline_pipeline):
            d_str = doc["_id"]["date"]
            s_id = doc["_id"]["source_id"] or "unknown"
            c = doc.get("count", 0)
            trend_map.setdefault(d_str, {})[s_id] = c

        timeline_points = [
            TimelinePoint(
                date=d_key,
                count=sum(src_counts.values()),
                sources_breakdown=src_counts,
            )
            for d_key, src_counts in sorted(trend_map.items())
        ]

        # 4. Story Status Distribution Aggregation
        story_pipeline: list[dict[str, Any]] = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        story_metrics: list[StoryStatusDistribution] = []
        for doc in self.stories_coll.aggregate(story_pipeline):
            st_name = doc["_id"] or "emerging"
            cnt = doc.get("count", 0)
            pct = round((cnt / total_stories * 100.0), 1) if total_stories > 0 else 0.0
            story_metrics.append(
                StoryStatusDistribution(status=st_name, count=cnt, percentage=pct)
            )

        return AnalyticsOverviewReport(
            total_articles=total_articles,
            total_sources=total_sources,
            total_stories=total_stories,
            unknown_publication_date_count=unknown_pub_date_count,
            quarantined_articles_count=quarantined_count,
            source_coverage=coverage_metrics,
            language_distribution=language_metrics,
            timeline_trend=timeline_points,
            story_status_distribution=story_metrics,
            as_of=utc_now(),
        )
