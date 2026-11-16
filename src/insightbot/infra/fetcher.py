"""Central HTTPX fetcher with SSRF defense, redirect inspection, ETag conditional requests, and raw blob persistence."""

import hashlib
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel

from insightbot.config import Settings
from insightbot.models.fetch import FetchRecord
from insightbot.modules.ingestion.url import SSRFViolationError, validate_safe_url

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "InsightBot/1.0 (+https://insightbot.local/bot; news-research; self-hosted)"
DEFAULT_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB safety cap
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 15.0
DEFAULT_MAX_REDIRECTS = 5


class FetchResult(BaseModel):
    """Result of an HTTP fetch operation."""

    url: str
    resolved_url: str
    status_code: int
    is_not_modified: bool = False  # True for HTTP 304
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    content_hash: Optional[str] = None
    raw_storage_key: Optional[str] = None
    response_time_ms: int = 0
    content_bytes: bytes = b""
    text: str = ""
    error: Optional[str] = None


class CentralFetcher:
    """Handles all outgoing HTTP requests with strict security and provenance guarantees."""

    def __init__(
        self,
        settings: Settings,
        allow_private_ips: bool = False,
        user_agent: str = DEFAULT_USER_AGENT,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ):
        self.settings = settings
        self.allow_private_ips = allow_private_ips
        self.user_agent = user_agent
        self.max_body_bytes = max_body_bytes

    def fetch(
        self,
        url: str,
        source_id: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        allow_raw_storage: bool = True,
    ) -> FetchResult:
        """
        Execute safe HTTP GET with conditional headers, manual redirect inspection for SSRF,
        and atomic raw response persistence.
        """
        current_url = url
        redirect_count = 0
        start_time = time.time()

        headers: dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        # Create un-redirecting client to manually inspect and validate each hop against SSRF
        with httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(
                connect=DEFAULT_CONNECT_TIMEOUT,
                read=DEFAULT_READ_TIMEOUT,
                write=5.0,
                pool=5.0,
            ),
        ) as client:
            while True:
                # Validate URL before every dispatch
                validate_safe_url(current_url, allow_private=self.allow_private_ips)

                try:
                    resp = client.get(current_url, headers=headers)
                except httpx.RequestError as exc:
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.warning("Network error fetching '%s': %s", current_url, exc)
                    return FetchResult(
                        url=url,
                        resolved_url=current_url,
                        status_code=0,
                        response_time_ms=duration_ms,
                        error=f"Request error: {exc}",
                    )

                # Check for redirect (301, 302, 303, 307, 308)
                if resp.is_redirect and "location" in resp.headers:
                    redirect_count += 1
                    if redirect_count > DEFAULT_MAX_REDIRECTS:
                        duration_ms = int((time.time() - start_time) * 1000)
                        return FetchResult(
                            url=url,
                            resolved_url=current_url,
                            status_code=resp.status_code,
                            response_time_ms=duration_ms,
                            error=f"Exceeded max redirects ({DEFAULT_MAX_REDIRECTS})",
                        )

                    next_url = str(
                        resp.next_request.url if resp.next_request else resp.headers["location"]
                    )
                    # Inspect next URL target against SSRF! Private redirect MUST fail!
                    try:
                        validate_safe_url(next_url, allow_private=self.allow_private_ips)
                    except SSRFViolationError as ssrf_err:
                        logger.error(
                            "Blocked SSRF redirect from '%s' to '%s': %s",
                            current_url,
                            next_url,
                            ssrf_err,
                        )
                        raise

                    current_url = next_url
                    continue

                # Finished redirects; handle final response
                duration_ms = int((time.time() - start_time) * 1000)
                resp_etag = resp.headers.get("etag")
                resp_last_modified = resp.headers.get("last-modified")

                # Handle HTTP 304 Not Modified
                if resp.status_code == 304:
                    return FetchResult(
                        url=url,
                        resolved_url=current_url,
                        status_code=304,
                        is_not_modified=True,
                        etag=resp_etag or etag,
                        last_modified=resp_last_modified or last_modified,
                        response_time_ms=duration_ms,
                    )

                # Check body length safety cap
                body_bytes = resp.content
                if len(body_bytes) > self.max_body_bytes:
                    return FetchResult(
                        url=url,
                        resolved_url=current_url,
                        status_code=resp.status_code,
                        response_time_ms=duration_ms,
                        error=f"Response body exceeded maximum allowed limit ({len(body_bytes)} > {self.max_body_bytes} bytes)",
                    )

                content_hash = hashlib.sha256(body_bytes).hexdigest()

                raw_storage_key: Optional[str] = None
                if allow_raw_storage and resp.status_code == 200:
                    raw_storage_key = self._persist_raw_snapshot(
                        source_id, content_hash, body_bytes
                    )

                return FetchResult(
                    url=url,
                    resolved_url=current_url,
                    status_code=resp.status_code,
                    is_not_modified=False,
                    etag=resp_etag,
                    last_modified=resp_last_modified,
                    content_hash=content_hash,
                    raw_storage_key=raw_storage_key,
                    response_time_ms=duration_ms,
                    content_bytes=body_bytes,
                    text=resp.text,
                )

    def _persist_raw_snapshot(self, source_id: str, content_hash: str, content: bytes) -> str:
        """Persist raw response bytes to local storage using atomic temporary file write and rename."""
        now = datetime.now(timezone.utc)
        target_dir = (
            self.settings.raw_storage_path / source_id / f"{now.year:04d}" / f"{now.month:02d}"
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / f"{content_hash}.html"
        rel_key = str(target_file.relative_to(self.settings.raw_storage_path)).replace("\\", "/")

        if target_file.exists():
            return rel_key

        # Atomic write via temporary file in the same directory
        temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix="tmp_raw_")
        try:
            with open(temp_fd, "wb") as f:
                f.write(content)
            Path(temp_path).replace(target_file)
        except Exception:
            Path(temp_path).unlink(missing_ok=True)
            raise

        return rel_key

    def to_fetch_record(self, source_id: str, result: FetchResult) -> FetchRecord:
        """Convert a FetchResult to an immutable FetchRecord model for persistence."""
        return FetchRecord(
            source_id=source_id,
            url=result.url,
            status_code=result.status_code,
            etag=result.etag,
            last_modified=result.last_modified,
            response_time_ms=result.response_time_ms,
            content_hash=result.content_hash,
            raw_storage_key=result.raw_storage_key,
            error=result.error,
        )
