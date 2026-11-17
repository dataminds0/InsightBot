"""Deduplication and syndication detection module."""

from insightbot.modules.deduplication.detector import (
    DeduplicationEngine,
    compute_headline_similarity,
    compute_shingle_jaccard,
    detect_wire_agency,
    extract_numbers,
    normalize_text_for_dedup,
)
from insightbot.modules.deduplication.service import DeduplicationService

__all__ = [
    "DeduplicationEngine",
    "DeduplicationService",
    "compute_headline_similarity",
    "compute_shingle_jaccard",
    "detect_wire_agency",
    "extract_numbers",
    "normalize_text_for_dedup",
]
