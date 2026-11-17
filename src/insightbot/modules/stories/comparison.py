"""Comparison Engine for analyzing event perspectives, timelines, and attributed divergences."""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.comparison import (
    AnalystReview,
    AttributedDifference,
    DivergenceCategory,
    EventComparisonReport,
    ReviewStoryRequest,
    SourcePerspective,
    TimelineMilestone,
    VersionedEvidence,
)
from insightbot.models.story import (
    EntityCategory,
    StoryAudit,
    StoryAuditAction,
    StorySnapshot,
    StoryStatus,
)
from insightbot.modules.stories.clustering import (
    extract_entities_from_text,
    extract_keywords_from_text,
)

logger = logging.getLogger(__name__)

# Numerical extraction regexes for Arabic, English, and Russian
NUMERICAL_REGEX_AR = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(شخص(?:[اًا])?|قتيل(?:[اًا])?|قتلى|شهيد(?:[اًا])?|شهداء|ضحية|ضحايا|مصاب(?:[اًاين]+)?|جريح(?:[اًا])?|جرحى|مليون|مليار|ألف|دولار|غارة|غارات|صاروخ|صواريخ|معتقل(?:[اًاين]+)?|نازح(?:[اًاين]+)?)\b",
    re.IGNORECASE,
)
NUMERICAL_REGEX_EN = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(killed|dead|injured|wounded|casualties|deaths|million|billion|thousand|dollars|strikes|missiles|displaced|people)\b",
    re.IGNORECASE,
)
NUMERICAL_REGEX_RU = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(погибших|погиб|раненых|ранен|жертв|человек|миллионов|тысяч|долларов|ракет)\b",
    re.IGNORECASE,
)

METRIC_CATEGORIES = {
    "casualties": {
        "شخص",
        "قتيل",
        "قتلى",
        "شهيد",
        "شهداء",
        "ضحية",
        "ضحايا",
        "مصاب",
        "جريح",
        "جرحى",
        "killed",
        "dead",
        "injured",
        "wounded",
        "casualties",
        "deaths",
        "people",
        "погиб",
        "ранен",
        "жертв",
        "человек",
    },
    "military": {
        "غارة",
        "غارات",
        "صاروخ",
        "صواريخ",
        "طائرة",
        "طائرات",
        "strike",
        "strikes",
        "missile",
        "missiles",
        "rocket",
        "rockets",
        "ракет",
    },
    "monetary": {
        "دولار",
        "مليون",
        "مليار",
        "ألف",
        "dollar",
        "dollars",
        "million",
        "billion",
        "thousand",
        "долларов",
    },
}


def get_metric_category(claim: str) -> str | None:
    """Determine the semantic domain/metric category of a numerical claim."""
    claim_lower = claim.lower()
    for cat_name, terms in METRIC_CATEGORIES.items():
        if any(term in claim_lower for term in terms):
            return cat_name
    return None

# Contrast framing indicators
FRAMING_CATEGORIES = {
    "aggressive": {"عدوان", "اعتداء", "مجزرة", "هجوم غادر", "massacre", "aggression", "atrocity"},
    "neutral_action": {"عملية", "ضربة", "استهداف", "قصف", "strike", "operation", "targeting", "атака"},
    "incident": {"حادث", "انفجار", "اشتباك", "incident", "blast", "explosion", "clash", "инцидент"},
}


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def extract_numerical_claims(text: str) -> list[str]:
    """Extract concrete numerical statements (e.g. '12 قتيل', '45 casualties')."""
    claims: list[str] = []
    for match in NUMERICAL_REGEX_AR.finditer(text):
        claims.append(f"{match.group(1)} {match.group(2)}")
    for match in NUMERICAL_REGEX_EN.finditer(text):
        claims.append(f"{match.group(1)} {match.group(2)}")
    for match in NUMERICAL_REGEX_RU.finditer(text):
        claims.append(f"{match.group(1)} {match.group(2)}")
    return claims


def parse_number_value(claim: str) -> float | None:
    """Parse numeric portion of a claim for comparison."""
    m = re.search(r"(\d+(?:[.,]\d+)?)", claim)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


class EventComparisonService:
    """Analyzes and compares multi-source coverage of real-world events."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.stories_coll = db["stories"]
        self.articles_coll = db["articles"]
        self.reviews_coll = db["story_reviews"]
        self.audits_coll = db["story_audits"]
        self.snapshots_coll = db["story_snapshots"]

    def generate_comparison_report(self, story_id: str) -> EventComparisonReport:
        """
        Builds a comprehensive multi-source comparison report for a story cluster.
        Includes comparative timeline, source perspectives, attributed divergences,
        and versioned citations (Defects A05/A06/A12/A13 safe).
        """
        story_doc = self.stories_coll.find_one({"story_id": story_id})
        if not story_doc:
            raise ValueError(f"Story '{story_id}' not found")

        article_ids = story_doc.get("article_ids", [])
        if not article_ids:
            raise ValueError(f"Story '{story_id}' contains no member articles")

        # Fetch member articles (safe projection omitting unbounded data)
        articles_cursor = self.articles_coll.find(
            {"article_id": {"$in": article_ids}},
            {
                "_id": 0,
                "article_id": 1,
                "source_id": 1,
                "canonical_url": 1,
                "title": 1,
                "body_text": 1,
                "language": 1,
                "published_at": 1,
                "publication_date_unknown_reason": 1,
                "fetched_at": 1,
                "current_version": 1,
                "word_count": 1,
                "reading_time_minutes": 1,
            },
        )
        articles = list(articles_cursor)
        if not articles:
            raise ValueError(f"Articles for story '{story_id}' could not be loaded")

        # 1. Build Chronological Timeline Milestones
        milestones: list[TimelineMilestone] = []
        lead_art_id = story_doc.get("lead_article_id")

        for art in articles:
            pub_at = art.get("published_at")
            fetch_at = art.get("fetched_at")

            # Defect A13 defense: Disambiguate unknown publication date from fetch time
            if pub_at is not None:
                ts = pub_at
                ts_basis = "published_at"
            else:
                ts = fetch_at
                ts_basis = "unknown"

            # Defect A12 defense: Dynamic safe snippet <= 150 chars
            body = (art.get("body_text") or "").strip()
            snippet = body[:140] + ("..." if len(body) > 140 else "")

            milestones.append(
                TimelineMilestone(
                    timestamp=ts,
                    timestamp_basis=ts_basis,
                    source_id=art.get("source_id", "unknown"),
                    article_id=art.get("article_id", ""),
                    version=art.get("current_version", 1),
                    title=art.get("title", ""),
                    language=art.get("language", "ar"),
                    lead_quote=snippet,
                    is_lead_article=(art.get("article_id") == lead_art_id),
                )
            )

        # Sort milestones chronologically
        milestones.sort(
            key=lambda m: (
                m.timestamp.isoformat()
                if m.timestamp
                else "9999-12-31"
            )
        )

        # Calculate time span
        earliest_ts: datetime | None = None
        latest_ts: datetime | None = None
        for m in milestones:
            if m.timestamp:
                if earliest_ts is None or m.timestamp < earliest_ts:
                    earliest_ts = m.timestamp
                if latest_ts is None or m.timestamp > latest_ts:
                    latest_ts = m.timestamp

        reporting_span_hours = 0.0
        if earliest_ts and latest_ts:
            reporting_span_hours = round(
                (latest_ts - earliest_ts).total_seconds() / 3600.0, 2
            )

        first_source = milestones[0].source_id if milestones else None

        # 2. Build Source Perspectives
        source_groups: dict[str, list[dict[str, Any]]] = {}
        for art in articles:
            s_id = art.get("source_id", "unknown")
            source_groups.setdefault(s_id, []).append(art)

        perspectives: list[SourcePerspective] = []

        for s_id, s_arts in source_groups.items():
            # Sort this source's articles
            s_arts.sort(
                key=lambda a: (
                    a.get("published_at") or a.get("fetched_at") or datetime.max.replace(tzinfo=timezone.utc)
                )
            )
            first_art = s_arts[0]
            last_art = s_arts[-1]

            f_pub = first_art.get("published_at")
            f_fetch = first_art.get("fetched_at")
            first_rep_at = f_pub or f_fetch
            first_rep_basis = "published_at" if f_pub else "unknown"

            latency_min = 0
            if earliest_ts and first_rep_at:
                latency_min = max(0, int((first_rep_at - earliest_ts).total_seconds() / 60))

            # Numerical claims & Framing terms across source articles
            combined_text = " ".join((a.get("title", "") + " " + (a.get("body_text", "") or "")) for a in s_arts)
            num_claims = extract_numerical_claims(combined_text)

            # Extract entities
            all_mentions = extract_entities_from_text(
                first_art.get("article_id", ""), combined_text
            )
            key_entities = list(
                {
                    m.text
                    for m in all_mentions
                    if m.category in (EntityCategory.LOCATION, EntityCategory.ORGANIZATION)
                }
            )[:6]

            # Framing terms from headlines
            framing_terms = extract_keywords_from_text(
                " ".join(a.get("title", "") for a in s_arts), ""
            )[:5]

            total_words = sum(a.get("word_count", 0) for a in s_arts)
            read_time = max(1, sum(a.get("reading_time_minutes", 1) for a in s_arts))

            perspectives.append(
                SourcePerspective(
                    source_id=s_id,
                    article_count=len(s_arts),
                    first_reported_at=first_rep_at,
                    first_reported_basis=first_rep_basis,
                    latest_reported_at=last_art.get("published_at") or last_art.get("fetched_at"),
                    headline=first_art.get("title", ""),
                    lead_article_id=first_art.get("article_id", ""),
                    lead_article_version=first_art.get("current_version", 1),
                    key_entities=key_entities,
                    framing_terms=framing_terms,
                    numerical_claims=list(set(num_claims))[:8],
                    word_count=total_words,
                    reading_time_minutes=read_time,
                    latency_minutes_from_first=latency_min,
                )
            )

        # Sort perspectives by latency / reporting order
        perspectives.sort(key=lambda p: p.latency_minutes_from_first)

        # 3. Detect Attributed Differences (Divergences)
        divergent_points: list[AttributedDifference] = []

        # A. Numerical Divergences
        for i in range(len(perspectives)):
            for j in range(i + 1, len(perspectives)):
                p_a = perspectives[i]
                p_b = perspectives[j]

                for claim_a in p_a.numerical_claims:
                    val_a = parse_number_value(claim_a)
                    if val_a is None:
                        continue

                    # Look for comparable claims in p_b
                    for claim_b in p_b.numerical_claims:
                        val_b = parse_number_value(claim_b)
                        if val_b is None:
                            continue

                        # Check if claims share context keywords or belong to the same metric category
                        cat_a = get_metric_category(claim_a)
                        cat_b = get_metric_category(claim_b)
                        same_category = (cat_a is not None and cat_a == cat_b)
                        keywords_a = set(re.findall(r"\b\w{3,}\b", claim_a))
                        keywords_b = set(re.findall(r"\b\w{3,}\b", claim_b))
                        has_overlap = same_category or bool(keywords_a.intersection(keywords_b))

                        if has_overlap and abs(val_a - val_b) > 0.001:
                            ratio = max(val_a, val_b) / (min(val_a, val_b) + 0.0001)
                            severity = "high" if ratio >= 1.5 else "medium"

                            divergent_points.append(
                                AttributedDifference(
                                    category=DivergenceCategory.NUMERICAL_FACTS,
                                    description=(
                                        f"تباين في الإحصاءات المسجلة: أوردت {p_a.source_id} ({claim_a}) "
                                        f"بينما أوردت {p_b.source_id} ({claim_b})"
                                    ),
                                    source_a=p_a.source_id,
                                    source_a_claim=claim_a,
                                    source_a_citation=f"{p_a.lead_article_id}:v{p_a.lead_article_version}",
                                    source_b=p_b.source_id,
                                    source_b_claim=claim_b,
                                    source_b_citation=f"{p_b.lead_article_id}:v{p_b.lead_article_version}",
                                    severity=severity,
                                )
                            )

        # B. Timeline Latency Divergences (Reporting lag > 30 mins)
        if len(perspectives) >= 2:
            first_p = perspectives[0]
            for later_p in perspectives[1:]:
                if later_p.latency_minutes_from_first >= 30:
                    divergent_points.append(
                        AttributedDifference(
                            category=DivergenceCategory.TIMELINE_LATENCY,
                            description=(
                                f"فارق زمني في التغطية: انفردت {first_p.source_id} بالتقرير أولاً، "
                                f"بينما نشرت {later_p.source_id} بعد {later_p.latency_minutes_from_first} دقيقة"
                            ),
                            source_a=first_p.source_id,
                            source_a_claim=f"نشر أولي عند {first_p.first_reported_at}",
                            source_a_citation=f"{first_p.lead_article_id}:v{first_p.lead_article_version}",
                            source_b=later_p.source_id,
                            source_b_claim=f"نشر متأخر بفارق {later_p.latency_minutes_from_first} دقيقة",
                            source_b_citation=f"{later_p.lead_article_id}:v{later_p.lead_article_version}",
                            severity="low",
                        )
                    )

        # 4. Extract Versioned Evidence Items
        evidence_items: list[VersionedEvidence] = []
        for art in articles:
            body = (art.get("body_text") or "").strip()
            exact_quote = body[:180] if body else art.get("title", "")

            evidence_items.append(
                VersionedEvidence(
                    article_id=art.get("article_id", ""),
                    version=art.get("current_version", 1),
                    source_id=art.get("source_id", ""),
                    canonical_url=art.get("canonical_url", ""),
                    exact_quote=exact_quote,
                    published_at=art.get("published_at"),
                    context_title=art.get("title", ""),
                )
            )

        # 5. Fetch Latest Analyst Review
        latest_review: AnalystReview | None = None
        rev_doc = self.reviews_coll.find_one({"story_id": story_id}, sort=[("reviewed_at", -1)])
        if rev_doc:
            rev_doc.pop("_id", None)
            latest_review = AnalystReview.model_validate(rev_doc)

        return EventComparisonReport(
            story_id=story_id,
            story_title=story_doc.get("title", ""),
            story_status=StoryStatus(story_doc.get("status", StoryStatus.EMERGING.value)),
            created_at=story_doc.get("created_at") or utc_now(),
            sources_count=len(perspectives),
            articles_count=len(articles),
            timeline=milestones,
            perspectives=perspectives,
            divergent_points=divergent_points,
            evidence_items=evidence_items,
            latest_review=latest_review,
            first_reported_source=first_source,
            reporting_span_hours=reporting_span_hours,
        )

    def submit_analyst_review(
        self, story_id: str, reviewer_id: str, request: ReviewStoryRequest
    ) -> AnalystReview:
        """
        Submits an audited Analyst/Admin review of story coverage and membership.
        Optionally excludes specific articles if flagged as mismatched.
        """
        story_doc = self.stories_coll.find_one({"story_id": story_id})
        if not story_doc:
            raise ValueError(f"Story '{story_id}' not found")

        # Snapshot current story state before review
        snapshot = StorySnapshot(
            story_id=story_id,
            version=story_doc.get("version", 1),
            story_data=dict(story_doc),
        )
        snapshot_dict = snapshot.model_dump()
        self.snapshots_coll.insert_one(snapshot_dict)

        # Handle optional article exclusions
        if request.excluded_article_ids:
            current_articles = story_doc.get("article_ids", [])
            remaining_articles = [
                a for a in current_articles if a not in request.excluded_article_ids
            ]
            if not remaining_articles:
                raise ValueError("Cannot exclude all articles from a story.")

            # Update story membership
            self.stories_coll.update_one(
                {"story_id": story_id},
                {
                    "$set": {
                        "article_ids": remaining_articles,
                        "article_count": len(remaining_articles),
                        "updated_at": utc_now(),
                    },
                    "$inc": {"version": 1},
                },
            )

        # Create review record
        review = AnalystReview(
            story_id=story_id,
            reviewer_id=reviewer_id,
            status=request.status,
            notes=request.notes,
            excluded_article_ids=request.excluded_article_ids,
            reviewed_at=utc_now(),
        )
        review_dict = review.model_dump()
        self.reviews_coll.insert_one(review_dict)

        # Log audit entry
        audit = StoryAudit(
            story_id=story_id,
            action=StoryAuditAction.MANUAL_EDIT,
            actor_id=reviewer_id,
            reason=f"Analyst review ({request.status}): {request.notes}",
            details={
                "status": request.status,
                "notes": request.notes,
                "excluded_count": len(request.excluded_article_ids),
                "review_id": review.review_id,
            },
        )
        self.audits_coll.insert_one(audit.model_dump())

        return review
