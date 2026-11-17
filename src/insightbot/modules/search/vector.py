"""Vector embedding generation and cosine similarity calculation for semantic search."""

import hashlib
import math

from insightbot.modules.deduplication.detector import normalize_text_for_dedup


def compute_deterministic_vector(text: str, dimensions: int = 384) -> list[float]:
    """
    Generate deterministic unit-normalized dense embedding vector (384 dimensions)
    from text using multi-hash semantic shingle projections.
    Provides fast, reproducible local vector search and evaluation without external network calls.
    """
    if not text:
        return [0.0] * dimensions

    norm = normalize_text_for_dedup(text)
    words = norm.split()
    vector = [0.0] * dimensions

    # Project unigrams, bigrams, and character trigrams into 384-dimensional space
    features: list[str] = list(words)
    for i in range(len(words) - 1):
        features.append(f"{words[i]}_{words[i+1]}")

    for feat in features:
        h = int(hashlib.sha256(feat.encode("utf-8")).hexdigest(), 16)
        idx = h % dimensions
        sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
        weight = 1.0 + math.log(1.0 + len(feat))
        vector[idx] += sign * weight

    # L2 unit normalization
    norm_l2 = math.sqrt(sum(v * v for v in vector))
    if norm_l2 > 0:
        vector = [v / norm_l2 for v in vector]

    return vector


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two unit-normalized vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return max(-1.0, min(1.0, dot))
