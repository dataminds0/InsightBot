"""Tests for NLP Model Manifest, Chunking, Caching, and Language Detection."""

from insightbot.modules.nlp.chunking import (
    chunk_article_text,
    compute_processing_hash,
)
from insightbot.modules.nlp.manifest import (
    ModelRole,
    ModelStatus,
    load_model_manifest,
)
from insightbot.modules.nlp.service import NLPService, detect_language


def test_model_manifest_validation():
    """Verify models.yaml manifest loads correctly with required pinned specs and licenses."""
    manifest = load_model_manifest("configs/models.yaml")
    assert manifest.version == "1.0.0"
    assert len(manifest.models) >= 3

    # Primary approved embedding model
    e5 = manifest.get_model("intfloat/multilingual-e5-small")
    assert e5 is not None
    assert e5.role == ModelRole.EMBEDDING
    assert e5.status == ModelStatus.APPROVED
    assert e5.license == "MIT"
    assert e5.dimensions == 384
    assert e5.max_tokens == 512
    assert e5.recommended_prefix.get("passage") == "passage: "
    assert e5.recommended_prefix.get("query") == "query: "
    assert e5.chunking is not None
    assert e5.chunking.target_tokens_min == 350
    assert e5.chunking.target_tokens_max == 450

    # Primary approved classification model
    deberta = manifest.get_model("MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
    assert deberta is not None
    assert deberta.role == ModelRole.CLASSIFICATION
    assert deberta.status == ModelStatus.APPROVED
    assert deberta.license in ("MIT", "CC-BY-4.0")
    assert deberta.confidence_threshold == 0.65
    assert "politics" in deberta.taxonomy
    assert "conflict" in deberta.taxonomy

    # Experimental models
    challenger = manifest.get_model("BAAI/bge-m3")
    assert challenger is not None
    assert challenger.status == ModelStatus.EXPERIMENTAL
    assert challenger.is_approved() is False


def test_language_detection():
    """Test deterministic language detection on Arabic, Russian, and English samples."""
    arabic_text = "أعلنت وزارة الخارجية استمرار المساعي الدبلوماسية لوقف إطلاق النار في المنطقة."
    russian_text = (
        "Министерство иностранных дел заявило о продолжении консультаций по безопасности."
    )
    english_text = (
        "The Ministry of Foreign Affairs announced the continuation of diplomatic efforts."
    )

    assert detect_language(arabic_text) == "ar"
    assert detect_language(russian_text) == "ru"
    assert detect_language(english_text) == "en"
    assert detect_language("") == "unknown"


def test_deterministic_chunking_with_offsets():
    """Test chunking preserves offsets, respects token bounds, and formats prefixes."""
    title = "تقرير إخباري موسع"
    body = (
        ("هذه فقرة أولى تحتوي على نص طويل نسبياً لمناقشة التطورات الميدانية والسياسية. " * 8)
        + "\n\n"
        + ("هذه فقرة ثانية تشرح تداعيات القرارات الاقتصادية على أسواق الطاقة والنفط. " * 8)
        + "\n\n"
        + ("وهذه فقرة ثالثة تتضمن استنتاجات الباحثين والمحللين حول مستقبل المباحثات. " * 8)
    )

    chunks = chunk_article_text(
        article_id="art-test-1",
        version=1,
        title=title,
        body_text=body,
        target_tokens_min=80,
        target_tokens_max=150,
        overlap_tokens=20,
        prefix="passage: ",
    )

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.article_id == "art-test-1"
        assert chunk.version == 1
        assert chunk.formatted_text.startswith("passage: ")
        assert title in chunk.formatted_text

        # Verify character offset slicing against original body
        sliced_text = body[chunk.char_start : chunk.char_end]
        assert sliced_text == chunk.text


def test_processing_hash_reproducibility():
    """Verify processing hash changes when model revision or parameters change."""
    h1 = compute_processing_hash("art-1", 1, "model-a", "rev-1", "embed", "hash-1")
    h2 = compute_processing_hash("art-1", 1, "model-a", "rev-1", "embed", "hash-1")
    assert h1 == h2

    # Different version
    h_v2 = compute_processing_hash("art-1", 2, "model-a", "rev-1", "embed", "hash-1")
    assert h1 != h_v2

    # Different revision
    h_rev2 = compute_processing_hash("art-1", 1, "model-a", "rev-2", "embed", "hash-1")
    assert h1 != h_rev2

    # Different parameters
    h_params = compute_processing_hash(
        "art-1", 1, "model-a", "rev-1", "embed", "hash-1", extra_params={"threshold": 0.8}
    )
    assert h1 != h_params


def test_nlp_service_classification_and_abstention():
    """Verify calibrated abstention when confidence is below threshold."""
    nlp = NLPService()

    # Confident sample: should return specific category
    confident = nlp.classify_article(
        article_id="art-10",
        version=1,
        title="مفاوضات وقف إطلاق النار في غزة",
        body_text="تتواصل المباحثات العسكرية حول تبادل الأسرى وهدنة إنسانية بين الجيش والمقاتلين.",
        language="ar",
    )
    assert confident["category"] == "conflict"
    assert confident["abstained"] is False
    assert confident["confidence"] >= 0.65

    # Ambiguous or vague sample: should abstain as 'uncertain'
    vague = nlp.classify_article(
        article_id="art-20",
        version=1,
        title="مقال عام وملاحظات سريعة",
        body_text="هذا نص تجريبي عام لا يتضمن أي كلمات دالة أو مواضيع رئيسية محددة.",
        language="ar",
    )
    assert vague["category"] == "uncertain"
    assert vague["abstained"] is True
    assert vague["reason"] == "below_confidence_threshold"
