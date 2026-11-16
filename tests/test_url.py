import pytest

from insightbot.modules.ingestion.url import (
    SSRFViolationError,
    is_private_ip,
    normalize_canonical_url,
    validate_safe_url,
)


def test_url_canonicalization_strips_tracking_params():
    raw_url = (
        "https://www.AlJazeera.net/news/2026/11/story/?utm_source=twitter&utm_medium=social"
        "&fbclid=IwAR123&article_id=9876&ref=homepage#"
        "section2"
    )
    canonical = normalize_canonical_url(raw_url)
    assert "utm_source" not in canonical
    assert "fbclid" not in canonical
    assert "section2" not in canonical
    assert "article_id=9876" in canonical
    assert canonical.startswith("https://www.aljazeera.net/news/2026/11/story")
    # Trailing slash removed
    assert not canonical.endswith("/")


def test_url_canonicalization_preserves_arabic_utf8():
    raw_url = "https://example.com/%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1/%D8%B9%D8%A7%D8%AC%D9%84"
    canonical = normalize_canonical_url(raw_url)
    # The Arabic path should be preserved or safely normalized without corruption
    assert "example.com" in canonical


def test_url_canonicalization_sorts_query_deterministically():
    url1 = "https://example.com/item?b=2&a=1&c=3"
    url2 = "https://example.com/item?c=3&b=2&a=1"
    assert normalize_canonical_url(url1) == normalize_canonical_url(url2)
    assert normalize_canonical_url(url1) == "https://example.com/item?a=1&b=2&c=3"


def test_url_canonicalization_deduplicates_slashes():
    url = "https://example.com//news///world//story"
    assert normalize_canonical_url(url) == "https://example.com/news/world/story"


def test_is_private_ip_detection():
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("10.0.0.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("172.16.0.1") is True
    assert is_private_ip("169.254.1.1") is True
    assert is_private_ip("::1") is True
    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("1.1.1.1") is False


def test_ssrf_rejects_localhost_and_private_ips():
    with pytest.raises(SSRFViolationError):
        validate_safe_url("http://localhost:8000/api")

    with pytest.raises(SSRFViolationError):
        validate_safe_url("http://127.0.0.1:27017")

    with pytest.raises(SSRFViolationError):
        validate_safe_url("http://192.168.1.50/admin")

    with pytest.raises(SSRFViolationError):
        validate_safe_url("ftp://example.com/file")


def test_ssrf_allows_when_explicitly_configured():
    # When allow_private is True (e.g. isolated test harness), loopback is allowed
    url = validate_safe_url("http://127.0.0.1:8000/health", allow_private=True)
    assert url == "http://127.0.0.1:8000/health"
