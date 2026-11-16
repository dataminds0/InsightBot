"""NLP models, manifest validation, deterministic chunking, and multilingual evaluation."""

from insightbot.modules.nlp.chunking import (
    TextChunk,
    chunk_article_text,
    compute_processing_hash,
)
from insightbot.modules.nlp.evaluation import (
    EvalSample,
    EvaluationMetrics,
    EventTimeSplitter,
    LanguageEvaluationReport,
    MultilingualEvaluator,
    compute_metrics,
    load_gold_corpus,
)
from insightbot.modules.nlp.manifest import (
    ChunkingConfig,
    ModelManifest,
    ModelRole,
    ModelSpec,
    ModelStatus,
    load_model_manifest,
)
from insightbot.modules.nlp.service import NLPService, detect_language

__all__ = [
    "ChunkingConfig",
    "EvalSample",
    "EvaluationMetrics",
    "EventTimeSplitter",
    "LanguageEvaluationReport",
    "ModelManifest",
    "ModelRole",
    "ModelSpec",
    "ModelStatus",
    "MultilingualEvaluator",
    "NLPService",
    "TextChunk",
    "chunk_article_text",
    "compute_metrics",
    "compute_processing_hash",
    "detect_language",
    "load_gold_corpus",
    "load_model_manifest",
]
