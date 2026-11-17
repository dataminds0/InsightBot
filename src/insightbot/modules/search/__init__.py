"""Search module with Lexical, Vector, and Reciprocal Rank Fusion Hybrid Search."""

from insightbot.modules.search.indexer import SearchGenerationManager
from insightbot.modules.search.lexical import compute_lexical_score, extract_search_tokens
from insightbot.modules.search.service import SearchService
from insightbot.modules.search.vector import (
    compute_deterministic_vector,
    cosine_similarity,
)

__all__ = [
    "SearchGenerationManager",
    "SearchService",
    "compute_deterministic_vector",
    "compute_lexical_score",
    "cosine_similarity",
    "extract_search_tokens",
]
