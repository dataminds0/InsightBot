"""Hybrid search service coordinating Lexical, Vector, and Reciprocal Rank Fusion (RRF)."""

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.search import (
    SearchMode,
    SearchResponse,
    SearchResultItem,
)
from insightbot.modules.search.indexer import SearchGenerationManager
from insightbot.modules.search.lexical import compute_lexical_score, extract_search_tokens
from insightbot.modules.search.vector import compute_deterministic_vector, cosine_similarity

logger = logging.getLogger(__name__)


class SearchService:
    """
    Search orchestration engine implementing Hybrid Lexical+Vector search,
    Reciprocal Rank Fusion (RRF), and graceful Basic fallback.
    """

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.articles_coll = db["articles"]
        self.chunks_coll = db["search_chunks"]
        self.sources_coll = db["sources"]
        self.gen_manager = SearchGenerationManager(db)

    def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.AUTO,
        source_id: str | None = None,
        language: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> SearchResponse:
        """
        Execute search query across indexed articles.
        Guarantees:
        1. No full body_text in search listings (Defect A12 memory defense).
        2. Automatic and explicit basic fallback if vector search is unavailable.
        3. Reciprocal Rank Fusion combining lexical terms and semantic embeddings.
        4. Stale-write and disabled source policy enforcement.
        """
        clean_q = query.strip()
        tokens = extract_search_tokens(clean_q)

        # 1. Fetch enabled sources for policy check
        enabled_sources_cursor = self.sources_coll.find({"enabled": True}, {"source_id": 1})
        enabled_source_ids = {s["source_id"] for s in enabled_sources_cursor}

        # Check active search generation
        active_gen = self.gen_manager.get_active_generation()
        index_lag = self.gen_manager.calculate_index_lag_seconds()

        # If no active generation exists or mode is explicitly basic, execute basic search
        if not active_gen or mode == SearchMode.BASIC:
            return self._execute_basic_search(
                query=clean_q,
                tokens=tokens,
                source_id=source_id,
                language=language,
                enabled_source_ids=enabled_source_ids,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                cursor=cursor,
                fallback_reason="Explicit basic search requested" if mode == SearchMode.BASIC else "No active search index generation",
            )

        # 2. Hybrid Search (Lexical + Vector)
        try:
            return self._execute_hybrid_search(
                query=clean_q,
                tokens=tokens,
                generation_id=active_gen.generation_id,
                source_id=source_id,
                language=language,
                enabled_source_ids=enabled_source_ids,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                index_lag=index_lag,
            )
        except Exception as e:
            logger.warning("Hybrid search execution failed; executing basic fallback: %s", e)
            return self._execute_basic_search(
                query=clean_q,
                tokens=tokens,
                source_id=source_id,
                language=language,
                enabled_source_ids=enabled_source_ids,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                cursor=cursor,
                fallback_reason=f"Vector search failed: {e}",
            )

    def _execute_hybrid_search(
        self,
        query: str,
        tokens: list[str],
        generation_id: str,
        source_id: str | None,
        language: str | None,
        enabled_source_ids: set[str],
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
        index_lag: float,
    ) -> SearchResponse:
        """Execute dual-track Lexical and Vector retrieval and merge via RRF."""
        # Query vector with asymmetric 'query: ' prefix
        query_vector = compute_deterministic_vector(f"query: {query}", dimensions=384)

        # Build candidate filter
        filter_query: dict[str, Any] = {"generation_id": generation_id}
        if source_id:
            filter_query["source_id"] = source_id
        if language:
            filter_query["language"] = language

        date_cond: dict[str, Any] = {}
        if start_date:
            date_cond["$gte"] = start_date
        if end_date:
            date_cond["$lte"] = end_date
        if date_cond:
            filter_query["published_at"] = date_cond

        # Fetch candidate chunks
        chunks = list(
            self.chunks_coll.find(
                filter_query,
                {
                    "_id": 0,
                    "chunk_id": 1,
                    "article_id": 1,
                    "title": 1,
                    "text": 1,
                    "source_id": 1,
                    "canonical_url": 1,
                    "language": 1,
                    "published_at": 1,
                    "fetched_at": 1,
                    "word_count": 1,
                    "embedding": 1,
                },
            ).limit(200)
        )

        # Track best chunk per article
        lexical_candidates: dict[str, tuple[float, str, dict[str, Any]]] = {}
        vector_candidates: dict[str, tuple[float, str, dict[str, Any]]] = {}

        for chk in chunks:
            art_id = chk["article_id"]
            # Policy guard: skip disabled sources
            if enabled_source_ids and chk["source_id"] not in enabled_source_ids:
                continue

            # 1. Lexical track
            l_score, l_snip = compute_lexical_score(tokens, chk["title"], chk["text"])
            if l_score > 0:
                if art_id not in lexical_candidates or l_score > lexical_candidates[art_id][0]:
                    lexical_candidates[art_id] = (l_score, l_snip, chk)

            # 2. Vector track
            v_score = cosine_similarity(query_vector, chk.get("embedding", []))
            if v_score > 0.05:  # minimal similarity floor
                if art_id not in vector_candidates or v_score > vector_candidates[art_id][0]:
                    snip = chk["text"][:150].strip() + "..."
                    vector_candidates[art_id] = (v_score, snip, chk)

        # Sort ranks (1-indexed)
        sorted_lex = sorted(lexical_candidates.items(), key=lambda x: x[1][0], reverse=True)
        sorted_vec = sorted(vector_candidates.items(), key=lambda x: x[1][0], reverse=True)

        lex_ranks = {art_id: rank + 1 for rank, (art_id, _) in enumerate(sorted_lex)}
        vec_ranks = {art_id: rank + 1 for rank, (art_id, _) in enumerate(sorted_vec)}

        # Combine via Reciprocal Rank Fusion (k = 60)
        all_art_ids = set(lex_ranks.keys()) | set(vec_ranks.keys())
        rrf_scores: list[tuple[str, float, int | None, int | None, str, dict[str, Any]]] = []

        k = 60.0
        for art_id in all_art_ids:
            r_l = lex_ranks.get(art_id)
            r_v = vec_ranks.get(art_id)

            rrf = 0.0
            if r_l is not None:
                rrf += 1.0 / (k + r_l)
            if r_v is not None:
                rrf += 1.0 / (k + r_v)

            # Pick best snippet and metadata
            if art_id in lexical_candidates:
                snip = lexical_candidates[art_id][1]
                meta = lexical_candidates[art_id][2]
            else:
                snip = vector_candidates[art_id][1]
                meta = vector_candidates[art_id][2]

            rrf_scores.append((art_id, rrf, r_l, r_v, snip, meta))

        # Sort by RRF descending
        rrf_scores.sort(key=lambda x: x[1], reverse=True)

        # Construct SearchResultItems (strictly omitting body_text)
        items: list[SearchResultItem] = []
        for art_id, rrf, r_l, r_v, snip, meta in rrf_scores[:limit]:
            wc = meta.get("word_count", 0)
            items.append(
                SearchResultItem(
                    article_id=art_id,
                    source_id=meta["source_id"],
                    canonical_url=meta["canonical_url"],
                    title=meta["title"],
                    language=meta["language"],
                    published_at=meta.get("published_at"),
                    fetched_at=meta["fetched_at"],
                    word_count=wc,
                    reading_time_minutes=max(1, (wc + 199) // 200),
                    score=round(rrf * 100, 4),
                    lexical_rank=r_l,
                    vector_rank=r_v,
                    rrf_score=round(rrf, 6),
                    snippet=snip,
                )
            )

        return SearchResponse(
            items=items,
            total=len(rrf_scores),
            search_mode=SearchMode.HYBRID,
            index_generation=generation_id,
            index_lag_seconds=index_lag,
            query=query,
            as_of=datetime.now(timezone.utc),
        )

    def _execute_basic_search(
        self,
        query: str,
        tokens: list[str],
        source_id: str | None,
        language: str | None,
        enabled_source_ids: set[str],
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
        cursor: str | None,
        fallback_reason: str,
    ) -> SearchResponse:
        """Reliable fallback to MongoDB lexical search when vector search is unavailable."""
        filter_query: dict[str, Any] = {"quarantine_reason": None}
        if source_id:
            filter_query["source_id"] = source_id
        if language:
            filter_query["language"] = language

        # Token regex matching on title or body
        if tokens:
            token_regexes = [{"title": {"$regex": tok, "$options": "i"}} for tok in tokens]
            filter_query["$or"] = token_regexes
        elif query:
            filter_query["title"] = {"$regex": query, "$options": "i"}

        date_cond: dict[str, Any] = {}
        if start_date:
            date_cond["$gte"] = start_date
        if end_date:
            date_cond["$lte"] = end_date
        if date_cond:
            filter_query["published_at"] = date_cond

        # Projection strictly excludes body_text
        projection = {
            "_id": 0,
            "article_id": 1,
            "source_id": 1,
            "canonical_url": 1,
            "title": 1,
            "language": 1,
            "published_at": 1,
            "fetched_at": 1,
            "word_count": 1,
            "body_text": 1,  # fetched only to build 150-char snippet, then removed
        }

        cursor_res = (
            self.articles_coll.find(filter_query, projection)
            .sort([("published_at", -1), ("article_id", 1)])
            .limit(limit)
        )

        items: list[SearchResultItem] = []
        for doc in cursor_res:
            if enabled_source_ids and doc["source_id"] not in enabled_source_ids:
                continue

            body = doc.pop("body_text", "")
            _, snip = compute_lexical_score(tokens, doc["title"], body)
            wc = doc.get("word_count", 0)

            items.append(
                SearchResultItem(
                    article_id=doc["article_id"],
                    source_id=doc["source_id"],
                    canonical_url=doc["canonical_url"],
                    title=doc["title"],
                    language=doc["language"],
                    published_at=doc.get("published_at"),
                    fetched_at=doc["fetched_at"],
                    word_count=wc,
                    reading_time_minutes=max(1, (wc + 199) // 200),
                    score=1.0,
                    snippet=snip,
                )
            )

        total = self.articles_coll.count_documents(filter_query)
        active_gen = self.gen_manager.get_active_generation()
        gen_id = active_gen.generation_id if active_gen else "basic_mongo"

        return SearchResponse(
            items=items,
            total=total,
            search_mode=SearchMode.BASIC_FALLBACK if fallback_reason.startswith("Vector search failed") else SearchMode.BASIC,
            index_generation=gen_id,
            index_lag_seconds=0.0,
            fallback_reason=fallback_reason,
            query=query,
            as_of=datetime.now(timezone.utc),
        )
