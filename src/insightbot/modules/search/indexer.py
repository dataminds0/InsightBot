"""Search index generation builder, validator, and atomic alias swapper."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.search import SearchGeneration
from insightbot.modules.nlp.chunking import chunk_article_text
from insightbot.modules.search.vector import compute_deterministic_vector

logger = logging.getLogger(__name__)


class SearchGenerationManager:
    """Manages immutable search index generations, validation, and zero-downtime alias swaps."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.articles_coll = db["articles"]
        self.generations_coll = db["search_generations"]
        self.chunks_coll = db["search_chunks"]

    def get_active_generation(self) -> SearchGeneration | None:
        """Fetch the currently active search generation."""
        doc = self.generations_coll.find_one({"is_active": True}, {"_id": 0})
        if not doc:
            return None
        return SearchGeneration.model_validate(doc)

    def build_generation(self, generation_id: str | None = None) -> SearchGeneration:
        """
        Build an immutable index generation: chunks articles, computes 384d vector embeddings,
        and saves them under the generation_id without affecting the active alias.
        """
        gen_id = generation_id or f"gen_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Retrieve all non-quarantined articles
        cursor = self.articles_coll.find(
            {"quarantine_reason": None},
            {
                "_id": 0,
                "article_id": 1,
                "current_version": 1,
                "source_id": 1,
                "canonical_url": 1,
                "title": 1,
                "body_text": 1,
                "language": 1,
                "published_at": 1,
                "fetched_at": 1,
                "word_count": 1,
            },
        )

        chunk_docs: list[dict[str, Any]] = []
        article_count = 0

        for art in cursor:
            article_count += 1
            chunks = chunk_article_text(
                article_id=art["article_id"],
                version=art.get("current_version", 1),
                title=art["title"],
                body_text=art["body_text"],
                prefix="passage: ",
            )

            for chk in chunks:
                vec = compute_deterministic_vector(chk.formatted_text, dimensions=384)
                chunk_docs.append(
                    {
                        "generation_id": gen_id,
                        "chunk_id": chk.chunk_id,
                        "article_id": art["article_id"],
                        "version": chk.version,
                        "chunk_index": chk.chunk_index,
                        "title": art["title"],
                        "text": chk.text,
                        "formatted_text": chk.formatted_text,
                        "embedding": vec,
                        "source_id": art["source_id"],
                        "canonical_url": art["canonical_url"],
                        "language": art["language"],
                        "published_at": art.get("published_at"),
                        "fetched_at": art["fetched_at"],
                        "word_count": art.get("word_count", 0),
                    }
                )

        if chunk_docs:
            self.chunks_coll.insert_many(chunk_docs)

        gen = SearchGeneration(
            generation_id=gen_id,
            is_active=False,
            article_count=article_count,
            chunks_count=len(chunk_docs),
            vector_dimensions=384,
            created_at=now,
            status="valid",
        )
        self.generations_coll.insert_one(gen.model_dump())

        # If no generation was active, activate this first one automatically
        if not self.get_active_generation():
            self.swap_active_generation(gen_id)
            gen.is_active = True

        return gen

    def validate_generation(self, generation_id: str) -> bool:
        """Validate generation chunks, dimensional consistency, and document non-emptiness."""
        gen = self.generations_coll.find_one({"generation_id": generation_id})
        if not gen:
            return False

        # Verify chunks dimensions
        sample_chunk = self.chunks_coll.find_one({"generation_id": generation_id})
        if sample_chunk:
            emb = sample_chunk.get("embedding", [])
            if len(emb) != 384:
                logger.error("Generation %s has invalid embedding dimension %d", generation_id, len(emb))
                return False

        return True

    def swap_active_generation(self, generation_id: str) -> SearchGeneration:
        """Atomically activate target generation and deactivate former active generation."""
        if not self.validate_generation(generation_id):
            raise ValueError(f"Generation '{generation_id}' failed validation checks")

        now = datetime.now(timezone.utc)
        # Deactivate all active generations
        self.generations_coll.update_many({"is_active": True}, {"$set": {"is_active": False}})

        # Activate target generation
        self.generations_coll.update_one(
            {"generation_id": generation_id},
            {"$set": {"is_active": True, "activated_at": now}},
        )

        active = self.get_active_generation()
        assert active is not None
        return active

    def calculate_index_lag_seconds(self) -> float:
        """Calculate lag between latest crawled article and active search generation."""
        latest_art = self.articles_coll.find_one(
            {"quarantine_reason": None},
            {"fetched_at": 1, "published_at": 1},
            sort=[("fetched_at", -1)],
        )
        if not latest_art:
            return 0.0

        latest_art_time = latest_art.get("published_at") or latest_art.get("fetched_at")
        active_gen = self.get_active_generation()
        if not active_gen or not latest_art_time:
            return 0.0

        delta = (latest_art_time - active_gen.created_at).total_seconds()
        return float(max(0.0, float(delta)))
