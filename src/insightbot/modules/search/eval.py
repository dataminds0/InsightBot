"""Evaluation of Lexical vs Hybrid Search quality (Recall@10, nDCG@10) across multilingual queries."""

import json
import math
from pathlib import Path
from typing import Any

from insightbot.models.search import SearchMode
from insightbot.modules.search.service import SearchService


def dcg_at_k(relevances: list[float], k: int = 10) -> float:
    """Calculate Discounted Cumulative Gain at rank k."""
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        # Rank is 1-indexed (i + 1)
        rank = i + 1
        dcg += (2.0**rel - 1.0) / math.log2(rank + 1.0)
    return dcg


def ndcg_at_k(relevances: list[float], k: int = 10) -> float:
    """Calculate Normalized Discounted Cumulative Gain at rank k."""
    actual_dcg = dcg_at_k(relevances, k)
    ideal_relevances = sorted(relevances, reverse=True)
    ideal_dcg = dcg_at_k(ideal_relevances, k)
    if ideal_dcg <= 0.0:
        return 1.0 if actual_dcg > 0 else 0.0
    return actual_dcg / ideal_dcg


class SearchEvaluator:
    """Evaluates search retrieval quality across 60+ judged queries."""

    def __init__(self, benchmark_path: Path | str | None = None):
        if benchmark_path:
            self.benchmark_path = Path(benchmark_path)
        else:
            p1 = Path("data/eval/search_benchmark.json")
            if p1.exists():
                self.benchmark_path = p1
            else:
                self.benchmark_path = (
                    Path(__file__).resolve().parents[4] / "data" / "eval" / "search_benchmark.json"
                )
        with open(self.benchmark_path, "r", encoding="utf-8") as f:
            self.queries: list[dict[str, Any]] = json.load(f)

    def evaluate(self, service: SearchService, mode: SearchMode = SearchMode.HYBRID) -> dict[str, Any]:
        """
        Evaluate Recall@10 and nDCG@10 across all judged benchmark queries.
        """
        total_queries = len(self.queries)
        recalls: list[float] = []
        ndcgs: list[float] = []
        per_lang: dict[str, dict[str, list[float]]] = {
            "ar": {"recall": [], "ndcg": []},
            "en": {"recall": [], "ndcg": []},
            "ru": {"recall": [], "ndcg": []},
        }

        for item in self.queries:
            q_text = item["query"]
            lang = item["language"]
            keywords = [k.lower() for k in item.get("relevant_keywords", [])]

            res = service.search(query=q_text, mode=mode, limit=10)
            items = res.items

            relevances: list[float] = []
            for itm in items:
                text_to_check = (itm.title + " " + itm.snippet).lower()
                # If item matches any target keywords, mark relevant
                matched = any(kw in text_to_check for kw in keywords)
                relevances.append(1.0 if matched else 0.0)

            # Pad relevances up to 10 if fewer results
            while len(relevances) < 10:
                relevances.append(0.0)

            # Recall@10: at least one relevant item in top 10
            r_at_10 = 1.0 if any(r > 0 for r in relevances[:10]) else 0.0
            score_ndcg = ndcg_at_k(relevances, k=10)

            recalls.append(r_at_10)
            ndcgs.append(score_ndcg)

            if lang in per_lang:
                per_lang[lang]["recall"].append(r_at_10)
                per_lang[lang]["ndcg"].append(score_ndcg)

        mean_recall = sum(recalls) / max(len(recalls), 1)
        mean_ndcg = sum(ndcgs) / max(len(ndcgs), 1)

        lang_summaries = {}
        for l_code, stats in per_lang.items():
            r_list = stats["recall"]
            n_list = stats["ndcg"]
            lang_summaries[l_code] = {
                "recall_at_10": sum(r_list) / max(len(r_list), 1),
                "ndcg_at_10": sum(n_list) / max(len(n_list), 1),
                "query_count": len(r_list),
            }

        return {
            "mode": mode.value,
            "total_queries": total_queries,
            "mean_recall_at_10": round(mean_recall, 4),
            "mean_ndcg_at_10": round(mean_ndcg, 4),
            "languages": lang_summaries,
        }
