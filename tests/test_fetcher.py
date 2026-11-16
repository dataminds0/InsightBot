from unittest.mock import patch

import httpx
import pytest

from insightbot.config import Settings
from insightbot.infra.fetcher import CentralFetcher
from insightbot.modules.ingestion.url import SSRFViolationError


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        raw_storage_path=tmp_path / "raw",
        export_storage_path=tmp_path / "exports",
    )


def test_fetcher_handles_304_not_modified(test_settings):
    fetcher = CentralFetcher(test_settings, allow_private_ips=True)

    mock_resp = httpx.Response(
        status_code=304,
        headers={"etag": '"etag-abc"', "last-modified": "Mon, 16 Nov 2026 12:00:00 GMT"},
        request=httpx.Request("GET", "http://127.0.0.1:8000/feed.xml"),
    )

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        res = fetcher.fetch(
            url="http://127.0.0.1:8000/feed.xml",
            source_id="test_source",
            etag='"etag-abc"',
        )
        assert res.status_code == 304
        assert res.is_not_modified is True
        assert res.etag == '"etag-abc"'
        assert res.content_bytes == b""


def test_private_redirects_fail(test_settings):
    # Public URL redirects to a private internal address (127.0.0.1 or 192.168.1.1)
    fetcher = CentralFetcher(test_settings, allow_private_ips=False)

    redirect_resp = httpx.Response(
        status_code=302,
        headers={"location": "http://127.0.0.1:8000/admin"},
        request=httpx.Request("GET", "http://example.com/redirect"),
    )

    with patch.object(httpx.Client, "get", return_value=redirect_resp):
        # The fetcher MUST detect the private redirect location and raise SSRFViolationError!
        with patch("insightbot.infra.fetcher.validate_safe_url") as mock_val:
            # First hop (example.com) passes, second hop (127.0.0.1) raises SSRFViolationError
            def side_effect(url, allow_private=False):
                if "127.0.0.1" in url or "localhost" in url:
                    raise SSRFViolationError(f"Target resolves to private IP: {url}")
                return url

            mock_val.side_effect = side_effect

            with pytest.raises(SSRFViolationError) as exc:
                fetcher.fetch("http://example.com/redirect", source_id="test_source")
            assert "private IP" in str(exc.value)


def test_fetcher_persists_raw_snapshot(test_settings):
    fetcher = CentralFetcher(test_settings, allow_private_ips=True)
    sample_html = b"<html><body><h1>Real News</h1></body></html>"

    mock_resp = httpx.Response(
        status_code=200,
        content=sample_html,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", "http://127.0.0.1:8000/article/1"),
    )

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        res = fetcher.fetch("http://127.0.0.1:8000/article/1", source_id="aljazeera_ar")
        assert res.status_code == 200
        assert res.raw_storage_key is not None
        assert res.raw_storage_key.endswith(".html")

        # Verify file exists on disk
        saved_file = test_settings.raw_storage_path / res.raw_storage_key
        assert saved_file.exists()
        assert saved_file.read_bytes() == sample_html


def test_fetcher_exceeds_max_body_bytes(test_settings):
    fetcher = CentralFetcher(test_settings, allow_private_ips=True, max_body_bytes=100)
    huge_content = b"x" * 200

    mock_resp = httpx.Response(
        status_code=200,
        content=huge_content,
        request=httpx.Request("GET", "http://127.0.0.1:8000/huge"),
    )

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        res = fetcher.fetch("http://127.0.0.1:8000/huge", source_id="test_source")
        assert "exceeded maximum allowed limit" in (res.error or "")
