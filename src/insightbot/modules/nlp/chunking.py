"""Deterministic text chunking and processing hash generation for NLP models."""

import hashlib
import re
from typing import Any

from pydantic import BaseModel


class TextChunk(BaseModel):
    """Deterministic chunk of an article with offset preservation."""

    chunk_id: str
    article_id: str
    version: int
    chunk_index: int
    text: str
    token_count: int
    char_start: int
    char_end: int
    prefix: str = ""
    formatted_text: str = ""


def estimate_multilingual_tokens(text: str) -> int:
    """
    Estimate token count for multilingual text (ar, en, ru).
    Uses whitespace and punctuation segmentation, with Arabic/Russian subword factor (~1.3x words).
    """
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    # Multilingual tokenizers (XLM-RoBERTa, SentencePiece) split Arabic/Russian morphology
    return max(1, int(len(words) * 1.25))


def chunk_article_text(
    article_id: str,
    version: int,
    title: str,
    body_text: str,
    target_tokens_min: int = 350,
    target_tokens_max: int = 450,
    overlap_tokens: int = 50,
    prefix: str = "passage: ",
) -> list[TextChunk]:
    """
    Deterministically split article text into indexed chunks preserving character offsets.
    Includes title context in each passage chunk as recommended by retrieval models.
    """
    if not body_text.strip():
        return []

    # Segment by paragraphs first to preserve discourse coherence
    raw_paras = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    if not raw_paras:
        raw_paras = [body_text.strip()]

    chunks: list[TextChunk] = []
    current_text_parts: list[str] = []
    current_tokens = 0
    chunk_index = 0

    # Prefix formatting includes title for retrieval grounding
    title_context = f"{title.strip()}\n" if title.strip() else ""
    title_tokens = estimate_multilingual_tokens(title_context)

    # Track position in original text
    cursor_pos = 0

    for para in raw_paras:
        para_tokens = estimate_multilingual_tokens(para)

        # If adding this paragraph exceeds target_tokens_max and we have at least target_tokens_min
        if (
            current_tokens + para_tokens > target_tokens_max
            and current_tokens >= target_tokens_min
            and current_text_parts
        ):
            combined_text = "\n\n".join(current_text_parts)
            char_start = body_text.find(combined_text, cursor_pos)
            if char_start == -1:
                char_start = cursor_pos
            char_end = char_start + len(combined_text)

            chunk_content = f"{title_context}{combined_text}" if title_context else combined_text
            formatted = f"{prefix}{chunk_content}" if prefix else chunk_content

            chunks.append(
                TextChunk(
                    chunk_id=f"{article_id}:v{version}:c{chunk_index}",
                    article_id=article_id,
                    version=version,
                    chunk_index=chunk_index,
                    text=combined_text,
                    token_count=title_tokens + current_tokens,
                    char_start=char_start,
                    char_end=char_end,
                    prefix=prefix,
                    formatted_text=formatted,
                )
            )
            chunk_index += 1
            cursor_pos = max(0, char_end - (overlap_tokens * 4))  # Approximate char overlap

            # Retain overlap if requested
            if overlap_tokens > 0 and len(current_text_parts) > 1:
                current_text_parts = [current_text_parts[-1], para]
                current_tokens = estimate_multilingual_tokens("\n\n".join(current_text_parts))
            else:
                current_text_parts = [para]
                current_tokens = para_tokens
        else:
            current_text_parts.append(para)
            current_tokens += para_tokens

    # Flush remaining text
    if current_text_parts:
        combined_text = "\n\n".join(current_text_parts)
        char_start = body_text.find(combined_text, cursor_pos)
        if char_start == -1:
            char_start = cursor_pos
        char_end = char_start + len(combined_text)

        chunk_content = f"{title_context}{combined_text}" if title_context else combined_text
        formatted = f"{prefix}{chunk_content}" if prefix else chunk_content

        chunks.append(
            TextChunk(
                chunk_id=f"{article_id}:v{version}:c{chunk_index}",
                article_id=article_id,
                version=version,
                chunk_index=chunk_index,
                text=combined_text,
                token_count=title_tokens + current_tokens,
                char_start=char_start,
                char_end=char_end,
                prefix=prefix,
                formatted_text=formatted,
            )
        )

    return chunks


def compute_processing_hash(
    article_id: str,
    version: int,
    model_id: str,
    revision: str,
    purpose: str,
    content_hash: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> str:
    """
    Compute deterministic SHA-256 hash identifying an exact model analysis run.
    Ensures cached predictions are invalidated whenever model revision, taxonomy, or parameters change.
    """
    params_str = ""
    if extra_params:
        sorted_items = sorted((str(k), str(v)) for k, v in extra_params.items())
        params_str = ";".join(f"{k}={v}" for k, v in sorted_items)

    c_hash = content_hash or ""
    raw_signature = f"{article_id}:{version}:{c_hash}:{model_id}:{revision}:{purpose}:{params_str}"
    return hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
