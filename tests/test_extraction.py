import mongomock
import pytest

from insightbot.modules.extraction.extractor import ArticleExtractor
from insightbot.modules.extraction.service import ExtractionService

SAMPLE_ARABIC_COLON_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>غزة: مباحثات مكثفة لوقف إطلاق النار وتبادل الأسرى - الجزيرة نت</title>
    <meta name="description" content="ملخص التقرير الأولي">
</head>
<body>
    <article>
        <h1>غزة: مباحثات مكثفة لوقف إطلاق النار وتبادل الأسرى</h1>
        <p class="lead">أفادت مصادر مطلعة بوصول وفود التفاوض إلى العاصمة لمناقشة بنود التهدئة الشاملة.</p>
        <p>وتشمل المباحثات ملفات إدخال المساعدات الإنسانية وإعادة إعمار المناطق المتضررة وفق جدول زمني محدد.</p>
        <p>وأكدت الأطراف المعنية أن الأجواء إيجابية مع استمرار النقاش حول التفاصيل اللوجستية.</p>
    </article>
</body>
</html>
"""

SAMPLE_NO_DATE_HTML = """<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="utf-8">
    <title>تقرير تحليلي: مستقبل الطاقة المتجددة في الشرق الأوسط</title>
</head>
<body>
    <article>
        <h1>تقرير تحليلي: مستقبل الطاقة المتجددة في الشرق الأوسط</h1>
        <p>تشهد منطقة الشرق الأوسط تحولاً كبيراً نحو مشاريع الطاقة الشمسية وطاقة الرياح على مدار العقد الحالي.</p>
        <p>وتسعى الدول المصدرة للنفط لتنويع مصادر دخلها من خلال استثمارات ضخمة في البنية التحتية الخضراء.</p>
    </article>
</body>
</html>
"""

SAMPLE_ENGLISH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>London: Bank of England Maintains Interest Rates - BBC News</title>
    <meta property="article:published_time" content="2026-11-16T10:00:00Z">
</head>
<body>
    <article>
        <h1>London: Bank of England Maintains Interest Rates</h1>
        <p>The Bank of England has voted to hold interest rates steady as inflation remains near the target level.</p>
        <p>Policy makers noted that global economic uncertainties warrant a cautious approach over the coming months.</p>
    </article>
</body>
</html>
"""

SAMPLE_RUSSIAN_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Москва: Состоялись переговоры по торговому сотрудничеству - TASS</title>
    <meta property="article:published_time" content="2026-11-16T08:30:00Z">
</head>
<body>
    <article>
        <h1>Москва: Состоялись переговоры по торговому сотрудничеству</h1>
        <p>В столице завершился раунд консультаций представителей торгово-промышленных палат двух стран.</p>
        <p>Стороны обсудили новые логистические маршруты и упрощение взаимных таможенных процедур.</p>
    </article>
</body>
</html>
"""


@pytest.fixture
def extractor():
    return ArticleExtractor()


def test_arabic_colon_title_and_full_text_survive(extractor):
    extracted = extractor.extract_from_html(
        html_content=SAMPLE_ARABIC_COLON_HTML,
        url="https://aljazeera.net/news/123",
        language="ar",
    )

    # 1. Title verification: Colon MUST survive, site branding stripped
    assert ":" in extracted.title
    assert extracted.title.startswith("غزة:")
    assert extracted.title == "غزة: مباحثات مكثفة لوقف إطلاق النار وتبادل الأسرى"
    assert "الجزيرة نت" not in extracted.title

    # 2. Full text verification: Text is NOT truncated or replaced
    assert "أفادت مصادر مطلعة" in extracted.body_text
    assert "إدخال المساعدات الإنسانية" in extracted.body_text
    assert "التفاصيل اللوجستية" in extracted.body_text
    assert len(extracted.body_text) > 150
    assert extracted.quarantine_reason is None


def test_missing_publication_date_stays_unknown(extractor):
    extracted = extractor.extract_from_html(
        html_content=SAMPLE_NO_DATE_HTML,
        url="https://example.com/energy",
        language="ar",
    )

    # Must NOT invent dates; published_at must stay None with explicit reason
    assert extracted.published_at is None
    assert extracted.publication_date_unknown_reason == "missing_in_feed_and_metadata"
    # Title with colon still survives
    assert ":" in extracted.title
    assert extracted.title.startswith("تقرير تحليلي:")


def test_multilingual_benchmarks(extractor):
    # English benchmark
    extracted_en = extractor.extract_from_html(SAMPLE_ENGLISH_HTML, "https://bbc.com/news/1")
    assert ":" in extracted_en.title
    assert extracted_en.title == "London: Bank of England Maintains Interest Rates"
    assert "Bank of England has voted" in extracted_en.body_text
    assert extracted_en.published_at is not None
    assert extracted_en.language == "en"

    # Russian benchmark
    extracted_ru = extractor.extract_from_html(SAMPLE_RUSSIAN_HTML, "https://tass.com/news/1")
    assert ":" in extracted_ru.title
    assert extracted_ru.title == "Москва: Состоялись переговоры по торговому сотрудничеству"
    assert "В столице завершился раунд" in extracted_ru.body_text
    assert extracted_ru.published_at is not None
    assert extracted_ru.language == "ru"


def test_empty_or_corrupted_html_is_quarantined(extractor):
    extracted = extractor.extract_from_html(
        "<html><body><div></div></body></html>", "https://example.com/empty"
    )
    assert extracted.quarantine_reason == "insufficient_extracted_text"


def test_extraction_service_end_to_end():
    client = mongomock.MongoClient()
    db = client["test_extraction_db"]
    service = ExtractionService(db)

    article, extracted = service.process_raw_html(
        html_content=SAMPLE_ARABIC_COLON_HTML,
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/news/gaza-talks",
        original_url="https://aljazeera.net/news/gaza-talks?utm_source=twitter",
        resolved_url="https://aljazeera.net/news/gaza-talks",
        language="ar",
        raw_storage_key="aljazeera_ar/2026/11/hash123.html",
    )

    assert article.title == "غزة: مباحثات مكثفة لوقف إطلاق النار وتبادل الأسرى"
    assert ":" in article.title
    assert article.current_version == 1
    assert article.stage_states["extraction"] == "completed"

    # Verify immutable revision in database
    versions = service.article_repo.get_versions(article.article_id)
    assert len(versions) == 1
    assert versions[0].title == article.title
    assert versions[0].body_text == article.body_text
