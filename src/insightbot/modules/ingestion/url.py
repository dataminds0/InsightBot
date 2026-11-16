"""URL canonicalization, tracking parameter normalization, and SSRF prevention."""

import ipaddress
import re
import socket
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

TRACKING_PARAMS: set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_eid",
    "ref",
    "ref_src",
    "ocid",
    "cmpid",
    "_ga",
    "_gl",
    "igshid",
    "spm",
    "rss",
}


class SSRFViolationError(Exception):
    """Raised when an HTTP request targets a private, loopback, or non-routable address."""

    pass


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP string belongs to a private, loopback, link-local, or reserved network."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_reserved
            or ip.is_link_local
            or ip.is_multicast
            or ip_str in ("0.0.0.0", "::")
        )
    except ValueError:
        return True


def validate_safe_url(url: str, allow_private: bool = False) -> str:
    """
    Validate that a URL uses a safe scheme (http/https) and resolves only to public routable IP addresses.
    Raises SSRFViolationError on violation.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFViolationError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFViolationError(f"Missing hostname in URL: '{url}'")

    # Reject literal localhost or loopback names immediately
    if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        if not allow_private:
            raise SSRFViolationError(f"Access to localhost/loopback is blocked: '{hostname}'")

    if allow_private:
        return url

    # Resolve hostname via DNS and inspect resolved IPs
    try:
        # Get both IPv4 and IPv6 addresses
        addr_infos = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_infos:
            ip_candidate = str(sockaddr[0])
            if is_private_ip(ip_candidate):
                raise SSRFViolationError(
                    f"Host '{hostname}' resolves to private/non-routable IP address '{ip_candidate}'. SSRF blocked."
                )
    except socket.gaierror as e:
        raise SSRFViolationError(f"Could not resolve host '{hostname}': {e}")

    return url


def normalize_canonical_url(url: str) -> str:
    """
    Canonicalize URL:
    - Normalizes scheme and hostname to lowercase.
    - Strips default ports (:80, :443).
    - Removes URL fragments (#...).
    - Filters out known tracking parameters while preserving functional parameters.
    - Deterministically sorts remaining query parameters.
    - Preserves meaningful path casing while cleaning duplicate slashes.
    - Normalizes percent-encoding (properly preserves Arabic and UTF-8 characters).
    """
    parsed = urlparse(url.strip())

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default port from netloc
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Clean path: eliminate duplicate slashes and decode safe characters
    raw_path = parsed.path or "/"
    # Deduplicate consecutive slashes
    clean_path = re.sub(r"/{2,}", "/", raw_path)

    # Normalize safe percent-encoded characters (like Arabic characters in URLs)
    # unquote path, then quote only strictly necessary unsafe chars, preserving UTF-8
    decoded_path = unquote(clean_path)
    # Re-quote path allowing unicode characters
    encoded_path = quote(decoded_path, safe="/:@&=+$,-_.!~*'()")

    # Remove trailing slash unless it is the root path '/'
    if len(encoded_path) > 1 and encoded_path.endswith("/"):
        encoded_path = encoded_path[:-1]

    # Process query parameters
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_items: list[tuple[str, str]] = []
    for k, v in query_items:
        lower_k = k.lower()
        if lower_k in TRACKING_PARAMS or lower_k.startswith("utm_"):
            continue
        filtered_items.append((k, v))

    # Sort remaining query parameters deterministically
    filtered_items.sort(key=lambda item: (item[0], item[1]))
    clean_query = urlencode(filtered_items) if filtered_items else ""

    # Reconstruct normalized URL without fragment
    return urlunparse((scheme, netloc, encoded_path, "", clean_query, ""))
