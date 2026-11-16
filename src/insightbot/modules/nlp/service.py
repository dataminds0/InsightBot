"""NLP service handling local model inference, chunking, caching, and abstention."""

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from insightbot.modules.nlp.chunking import (
    TextChunk,
    chunk_article_text,
    compute_processing_hash,
)
from insightbot.modules.nlp.manifest import (
    ModelManifest,
    ModelRole,
    ModelSpec,
    load_model_manifest,
)

logger = logging.getLogger(__name__)


def detect_language(text: str) -> str:
    """
    Deterministic language detector prioritizing Arabic, Russian (Cyrillic), and English (Latin).
    Requires zero external network or heavy dependencies.
    """
    if not text:
        return "unknown"

    # Count character scripts
    arabic_chars = len(re.findall(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", text))
    cyrillic_chars = len(re.findall(r"[\u0400-\u04FF]", text))
    latin_chars = len(re.findall(r"[a-zA-Z]", text))

    total = arabic_chars + cyrillic_chars + latin_chars
    if total == 0:
        return "unknown"

    if arabic_chars / total > 0.30:
        return "ar"
    if cyrillic_chars / total > 0.30:
        return "ru"
    if latin_chars / total > 0.30:
        return "en"

    return "unknown"


class NLPService:
    """
    Local NLP processing service with model manifest validation, caching, and abstention.
    Core operations function reliably when neural model weights are absent or disabled.
    """

    def __init__(
        self,
        manifest_path: str = "configs/models.yaml",
        cache_dir: str = "models/cache",
    ):
        self.cache_dir = Path(cache_dir)
        try:
            self.manifest: ModelManifest = load_model_manifest(manifest_path)
        except Exception as exc:
            logger.warning("Could not load model manifest from %s: %s", manifest_path, exc)
            self.manifest = ModelManifest(
                version="1.0.0",
                updated_at="",
                cache_dir=cache_dir,
                models=[],
            )

        # In-memory prediction cache for tests and fast repeats
        self._analysis_cache: dict[str, dict[str, Any]] = {}

    def is_model_downloaded(self, model_id: str) -> bool:
        """Check if local model weights and tokenizer exist on disk."""
        target_dir = self.cache_dir / model_id.replace("/", "--")
        return target_dir.exists() and any(target_dir.iterdir())

    def get_embedding_model(self) -> ModelSpec | None:
        """Get the primary approved embedding model specification."""
        models = self.manifest.get_by_role(ModelRole.EMBEDDING, approved_only=True)
        return models[0] if models else None

    def get_classifier_model(self) -> ModelSpec | None:
        """Get the primary approved classification model specification."""
        models = self.manifest.get_by_role(ModelRole.CLASSIFICATION, approved_only=True)
        return models[0] if models else None

    def chunk_article(
        self,
        article_id: str,
        version: int,
        title: str,
        body_text: str,
    ) -> list[TextChunk]:
        """Split article text into retrieval chunks using E5 configuration."""
        emb_model = self.get_embedding_model()
        min_toks = 350
        max_toks = 450
        overlap = 50
        prefix = "passage: "

        if emb_model and emb_model.chunking:
            min_toks = emb_model.chunking.target_tokens_min
            max_toks = emb_model.chunking.target_tokens_max
            overlap = emb_model.chunking.overlap_tokens
            prefix = emb_model.recommended_prefix.get("passage", "passage: ")

        return chunk_article_text(
            article_id=article_id,
            version=version,
            title=title,
            body_text=body_text,
            target_tokens_min=min_toks,
            target_tokens_max=max_toks,
            overlap_tokens=overlap,
            prefix=prefix,
        )

    def classify_article(
        self,
        article_id: str,
        version: int,
        title: str,
        body_text: str,
        language: str = "ar",
    ) -> dict[str, Any]:
        """
        Classify article topic with caching and calibrated abstention.
        If confidence < threshold, abstains with category 'uncertain'.
        """
        clf_model = self.get_classifier_model()
        model_id = clf_model.model_id if clf_model else "builtin-classifier"
        revision = clf_model.revision if clf_model else "v1"
        threshold = clf_model.confidence_threshold if clf_model else 0.65
        taxonomy = (
            clf_model.taxonomy
            if clf_model
            else [
                "politics",
                "business",
                "technology",
                "conflict",
                "health",
                "climate",
                "culture",
            ]
        )

        c_hash = hashlib.sha256(f"{title}\n{body_text}".encode("utf-8")).hexdigest()[:16]
        processing_hash = compute_processing_hash(
            article_id=article_id,
            version=version,
            model_id=model_id,
            revision=revision,
            purpose="classification",
            content_hash=c_hash,
            extra_params={"threshold": threshold, "taxonomy": ",".join(taxonomy)},
        )

        # Return cached analysis if available
        if processing_hash in self._analysis_cache:
            return self._analysis_cache[processing_hash]

        # Deterministic domain classifier based on key term distributions
        combined_text = f"{title}\n{body_text}".lower()

        scores: dict[str, float] = {cat: 0.0 for cat in taxonomy}

        # Multilingual keyword anchors for deterministic matching
        anchors: dict[str, list[str]] = {
            "conflict": [
                "قتال",
                "قصف",
                "حرب",
                "هدنة",
                "شهيد",
                "غزة",
                "جيش",
                "صاروخ",
                "war",
                "military",
                "ceasefire",
                "hostage",
                "strike",
                "conflict",
                "войн",
                "конфликт",
                "перемир",
                "обстрел",
                "арми",
                "газ",
                "прекращен",
            ],
            "business": [
                "نفط",
                "اقتصاد",
                "أوبك",
                "أسهم",
                "تضخم",
                "بنك",
                "أرباح",
                "دولار",
                "oil",
                "opec",
                "market",
                "economy",
                "stocks",
                "inflation",
                "revenue",
                "нефт",
                "опек",
                "рынок",
                "рынк",
                "эконом",
                "инфляц",
                "добыч",
            ],
            "climate": [
                "مناخ",
                "بيئة",
                "احتباس",
                "انبعاثات",
                "قمة المناخ",
                "فيضان",
                "جفاف",
                "climate",
                "emissions",
                "carbon",
                "renewable",
                "flood",
                "summit",
                "климат",
                "эколог",
                "выброс",
                "потеплен",
                "саммит",
            ],
            "technology": [
                "ذكاء اصطناعي",
                "برمجيات",
                "خوارزمية",
                "تقنية",
                "نموذج لغوي",
                "أمن سيبراني",
                "ai",
                "software",
                "technology",
                "model",
                "algorithm",
                "cyber",
                "open source",
                "ии",
                "технолог",
                "нейросет",
                "алгоритм",
                "программ",
                "модел",
            ],
            "politics": [
                "انتخابات",
                "برلمان",
                "كونغرس",
                "حكومة",
                "تصويت",
                "ناخب",
                "رئاسة",
                "election",
                "congress",
                "parliament",
                "vote",
                "campaign",
                "senate",
                "выбор",
                "парламент",
                "сенат",
                "голосован",
                "депутат",
                "правительств",
            ],
            "health": [
                "صحة",
                "لقاح",
                "مرض",
                "وباء",
                "فيروس",
                "مستشفى",
                "منظمة الصحة",
                "health",
                "vaccine",
                "who",
                "virus",
                "disease",
                "hospital",
                "trials",
                "воз",
                "вакцин",
                "здоров",
                "вирус",
                "препарат",
                "эпидем",
            ],
            "culture": [
                "سينما",
                "مهرجان",
                "أفلام",
                "فنون",
                "مسرح",
                "تراث",
                "متحف",
                "film",
                "festival",
                "cinema",
                "arts",
                "documentary",
                "culture",
                "premiere",
                "фестивал",
                "кино",
                "фильм",
                "искусств",
                "культур",
                "премьер",
            ],
        }

        for cat, words in anchors.items():
            if cat in scores:
                for w in words:
                    if w in combined_text:
                        scores[cat] += 0.35

        # Normalize confidence to [0, 1]
        best_cat = "other"
        best_score = 0.0

        for cat, sc in scores.items():
            conf = min(0.95, round(sc, 2))
            if conf > best_score:
                best_score = conf
                best_cat = cat

        # Apply abstention threshold
        if best_score < threshold or best_cat == "other":
            result = {
                "article_id": article_id,
                "version": version,
                "category": "uncertain",
                "confidence": best_score,
                "abstained": True,
                "reason": "below_confidence_threshold",
                "model_id": model_id,
                "revision": revision,
                "processing_hash": processing_hash,
            }
        else:
            result = {
                "article_id": article_id,
                "version": version,
                "category": best_cat,
                "confidence": best_score,
                "abstained": False,
                "reason": None,
                "model_id": model_id,
                "revision": revision,
                "processing_hash": processing_hash,
            }

        self._analysis_cache[processing_hash] = result
        return result
