"""Deterministic detection algorithms for exact hashes, syndication, and near-duplicates."""

import re

from insightbot.models.article import Article
from insightbot.models.duplicate import (
    DuplicateEvidence,
    DuplicateRelationship,
    DuplicateStatus,
    DuplicateType,
)

# Common wire agencies across Arabic, English, and Russian
WIRE_AGENCIES: dict[str, list[str]] = {
    "Reuters": ["رويترز", "reuters", "рейтер"],
    "AFP": ["أ ف ب", "فرانس برس", "afp", "афп"],
    "AP": ["أسوشيتد برس", "اسوشيتد برس", "associated press", "ap", "ассошиэйтед пресс"],
    "Sputnik": ["سبوتنيك", "sputnik", "спутник"],
    "TASS": ["تاس", "tass", "тасс"],
    "Bloomberg": ["بلومبرغ", "bloomberg", "блумберг"],
    "Anadolu": ["الأناضول", "الاناضول", "anadolu"],
    "Interfax": ["إنترفاكس", "интерфакс", "interfax"],
}

# Arabic normalization regexes
ARABIC_DIACRITICS = re.compile(r"[\u064B-\u0652\u0670\u0640]")  # Tashkeel & Tatweel
EASTERN_TO_WESTERN_NUMS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_text_for_dedup(text: str) -> str:
    """Normalize text across Arabic, English, and Russian for shingling and similarity."""
    if not text:
        return ""

    # Translate eastern Arabic numerals to standard western digits
    t = text.translate(EASTERN_TO_WESTERN_NUMS)

    # Remove Arabic diacritics & tatweel
    t = ARABIC_DIACRITICS.sub("", t)

    # Normalize Arabic alef forms and teh marbuta
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ة\b", "ه", t)
    t = re.sub(r"ى\b", "ي", t)

    # Lowercase Latin and Cyrillic
    t = t.lower()

    # Collapse non-alphanumeric whitespace
    words = re.findall(r"\w+", t, re.UNICODE)
    return " ".join(words)


def extract_numbers(text: str) -> set[str]:
    """Extract all numerical quantities from text with normalized digits."""
    if not text:
        return set()
    normalized = text.translate(EASTERN_TO_WESTERN_NUMS)
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", normalized))


def detect_wire_agency(text: str) -> str | None:
    """Detect if text contains wire service attribution or dateline."""
    if not text:
        return None
    lower_text = text.lower()
    for agency_name, patterns in WIRE_AGENCIES.items():
        for pat in patterns:
            # Match boundary or parenthesized wire attribution (e.g. "(رويترز)", "رويترز -")
            if pat in lower_text:
                return agency_name
    return None


def compute_shingle_jaccard(text_a: str, text_b: str, k: int = 3) -> float:
    """
    Compute token-level k-shingle Jaccard similarity between two texts.
    Returns value between 0.0 (no overlap) and 1.0 (identical shingle distribution).
    """
    words_a = text_a.split()
    words_b = text_b.split()

    if len(words_a) < k or len(words_b) < k:
        # Fallback to word-level Jaccard if text is very short
        set_a = set(words_a)
        set_b = set(words_b)
        if not set_a and not set_b:
            return 1.0
        return len(set_a & set_b) / len(set_a | set_b)

    shingles_a = set(tuple(words_a[i : i + k]) for i in range(len(words_a) - k + 1))
    shingles_b = set(tuple(words_b[i : i + k]) for i in range(len(words_b) - k + 1))

    if not shingles_a and not shingles_b:
        return 1.0
    intersection = len(shingles_a & shingles_b)
    union = len(shingles_a | shingles_b)
    return intersection / union if union > 0 else 0.0


def compute_headline_similarity(h1: str, h2: str) -> float:
    """Calculate normalized word overlap between two article headlines."""
    norm1 = set(normalize_text_for_dedup(h1).split())
    norm2 = set(normalize_text_for_dedup(h2).split())
    if not norm1 and not norm2:
        return 1.0
    if not norm1 or not norm2:
        return 0.0
    return len(norm1 & norm2) / len(norm1 | norm2)


class DeduplicationEngine:
    """
    Core engine for detecting exact duplicates, wire syndication, and near-duplicates
    while rigorously protecting distinct reports with conflicting numbers or facts.
    """

    def __init__(
        self,
        near_duplicate_threshold: float = 0.85,
        temporal_window_hours: float = 72.0,
    ):
        self.near_duplicate_threshold = near_duplicate_threshold
        self.temporal_window_hours = temporal_window_hours

    def check_number_conflict(
        self,
        headline_a: str,
        headline_b: str,
        body_a: str,
        body_b: str,
        headline_sim: float,
    ) -> list[str]:
        """
        DEFECT DEFENSE: Similar headlines / different numbers.
        If headlines are similar (e.g. > 0.60 word overlap) but numerical figures differ
        (e.g. '10 dead' vs '50 dead'), this flags a critical factual conflict!
        """
        nums_head_a = extract_numbers(headline_a)
        nums_head_b = extract_numbers(headline_b)

        conflicts: list[str] = []
        if nums_head_a and nums_head_b and nums_head_a != nums_head_b and headline_sim >= 0.50:
            diff_a = nums_head_a - nums_head_b
            diff_b = nums_head_b - nums_head_a
            for da in diff_a:
                for db in diff_b:
                    conflicts.append(f"headline: {da} vs {db}")

        return conflicts

    def compare(
        self,
        article_a: Article,
        article_b: Article,
    ) -> DuplicateRelationship | None:
        """
        Compare two articles and determine if a duplicate relationship exists.
        Returns DuplicateRelationship if duplicate/syndication detected, else None.
        """
        if article_a.article_id == article_b.article_id:
            return None

        # Determine canonical ordering: earlier publication/fetch is canonical
        time_a = article_a.published_at or article_a.fetched_at
        time_b = article_b.published_at or article_b.fetched_at

        # Temporal delta in hours
        delta_seconds = abs((time_a - time_b).total_seconds())
        delta_hours = round(delta_seconds / 3600.0, 2)

        if time_a <= time_b:
            canonical_art = article_a
            duplicate_art = article_b
        else:
            canonical_art = article_b
            duplicate_art = article_a

        norm_body_a = normalize_text_for_dedup(article_a.body_text)
        norm_body_b = normalize_text_for_dedup(article_b.body_text)

        headline_sim = compute_headline_similarity(article_a.title, article_b.title)

        # Wire Agency Detection
        agency_a = detect_wire_agency(article_a.body_text) or detect_wire_agency(article_a.title)
        agency_b = detect_wire_agency(article_b.body_text) or detect_wire_agency(article_b.title)
        shared_agency = agency_a if (agency_a and agency_a == agency_b) else (agency_a or agency_b)

        # 1. Exact Content Hash Check
        if article_a.content_hash == article_b.content_hash:
            dup_type = DuplicateType.SYNDICATION if shared_agency else DuplicateType.EXACT_HASH
            reason = (
                f"Identical body content hash ({article_a.content_hash[:10]}...)"
                + (f" with wire agency attribution: {shared_agency}" if shared_agency else "")
            )
            evidence = DuplicateEvidence(
                content_hash_match=True,
                jaccard_similarity=1.0,
                headline_similarity=round(headline_sim, 3),
                shared_wire_agency=shared_agency,
                temporal_delta_hours=delta_hours,
                reason=reason,
            )
            return DuplicateRelationship(
                canonical_article_id=canonical_art.article_id,
                duplicate_article_id=duplicate_art.article_id,
                duplicate_type=dup_type,
                status=DuplicateStatus.CONFIRMED,
                similarity_score=1.0,
                evidence=evidence,
            )

        # 2. Number Conflict Guard: similar headlines with differing statistics
        conflicts = self.check_number_conflict(
            article_a.title,
            article_b.title,
            norm_body_a,
            norm_body_b,
            headline_sim,
        )
        if conflicts:
            # Must NOT collapse distinct reports with conflicting numbers!
            return None

        # 3. Temporal Window Guard for Near-Duplicates
        if delta_hours > self.temporal_window_hours:
            return None

        # 4. Near-Duplicate & Syndication Evaluation via Shingle Jaccard
        jaccard_sim = compute_shingle_jaccard(norm_body_a, norm_body_b, k=3)

        if jaccard_sim >= self.near_duplicate_threshold:
            dup_type = DuplicateType.SYNDICATION if shared_agency else DuplicateType.NEAR_DUPLICATE
            reason = (
                f"High n-gram Jaccard similarity ({jaccard_sim:.3f} >= {self.near_duplicate_threshold})"
                + (f" syndicated from wire agency: {shared_agency}" if shared_agency else "")
            )
            evidence = DuplicateEvidence(
                content_hash_match=False,
                jaccard_similarity=round(jaccard_sim, 3),
                headline_similarity=round(headline_sim, 3),
                shared_wire_agency=shared_agency,
                temporal_delta_hours=delta_hours,
                reason=reason,
            )
            return DuplicateRelationship(
                canonical_article_id=canonical_art.article_id,
                duplicate_article_id=duplicate_art.article_id,
                duplicate_type=dup_type,
                status=DuplicateStatus.CONFIRMED,
                similarity_score=round(jaccard_sim, 3),
                evidence=evidence,
            )

        return None
