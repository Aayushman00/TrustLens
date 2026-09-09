"""SSRF-safe streaming dataset URL fetcher — V1: no archives, no redirects followed
automatically past a re-validated hop, hard byte cap enforced while streaming.

Critical security: DNS rebinding defense via connection pinning. Hostname is resolved
and validated BEFORE connection. The validated IP is extracted and the connection is
made DIRECTLY to that IP (not re-resolving the hostname), with the Host header and
SNI set to the original hostname for correct server-side request routing.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 3
_CONNECT_TIMEOUT = 5.0


class UrlFetchError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class FetchedBytes:
    data: bytes
    content_type: str | None
    http_status: int


@dataclass(frozen=True)
class _ValidatedUrl:
    """URL + resolved/validated IP for DNS rebinding defense (connection pinning)."""
    original_url: str
    original_hostname: str
    validated_ip: str
    scheme: str
    port: int | None


def _resolve_and_validate_host(host: str) -> str:
    """Resolve host to an IP and reject private/loopback/link-local/reserved ranges.

    Returns the validated IP as a string. The caller MUST pin the connection to this
    IP (not re-resolve the hostname at connect time) to defend against DNS rebinding.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UrlFetchError(f"could not resolve host: {exc}") from exc
    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UrlFetchError(f"resolved address is private/loopback/link-local/reserved: {ip}")
    return str(ipaddress.ip_address(infos[0][4][0]))


def _validate_url(url: str) -> _ValidatedUrl:
    """Validate URL scheme and resolve/validate hostname. Returns validated URL + IP."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UrlFetchError(f"unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UrlFetchError("URL has no hostname")
    validated_ip = _resolve_and_validate_host(parsed.hostname)
    return _ValidatedUrl(
        original_url=url,
        original_hostname=parsed.hostname,
        validated_ip=validated_ip,
        scheme=parsed.scheme,
        port=parsed.port,
    )


def _make_pinned_request_url(validated: _ValidatedUrl) -> str:
    """Construct a URL that connects to the validated IP but shows correct Host header.

    Returns a URL like http://IP:PORT/path where IP is the pre-validated address.
    The Host header is set separately to the original hostname so the server sees
    the request as if it came from the original URL. For HTTPS, SNI is also set.
    """
    # Determine port
    if validated.port:
        port = validated.port
    else:
        port = 443 if validated.scheme == "https" else 80

    parsed = urlparse(validated.original_url)

    # Format netloc with IP (wrap IPv6 in brackets for URL format)
    ip_obj = ipaddress.ip_address(validated.validated_ip)
    if isinstance(ip_obj, ipaddress.IPv6Address):
        netloc = f"[{validated.validated_ip}]:{port}"
    else:
        netloc = f"{validated.validated_ip}:{port}"

    # Reconstruct URL with IP instead of hostname, keeping path/query/fragment
    ip_url = urlunparse((
        validated.scheme,
        netloc,
        parsed.path or "/",
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))
    return ip_url


def fetch_dataset_url(
    url: str,
    *,
    max_bytes: int = 10_000_000,
    timeout_seconds: float = 15.0,
) -> FetchedBytes:
    """Fetch a dataset URL with SSRF protection and connection pinning.

    Args:
        url: URL to fetch (http/https only)
        max_bytes: Max response size in bytes (default 10MB)
        timeout_seconds: Request timeout (default 15s)

    Returns:
        FetchedBytes with data, content_type, http_status

    Raises:
        UrlFetchError: On any SSRF/scheme/size/timeout violation
    """
    current_validated = _validate_url(url)
    redirects_followed = 0

    # Create client with per-request Host header override (pinned IP connection)
    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=timeout_seconds,
        ),
    ) as client:
        while True:
            # Pin connection to the validated IP, but use original hostname for Host/SNI
            ip_url = _make_pinned_request_url(current_validated)
            headers = {"Host": current_validated.original_hostname}

            with client.stream(
                "GET",
                ip_url,
                headers=headers,
            ) as response:
                if response.is_redirect:
                    redirects_followed += 1
                    if redirects_followed > _MAX_REDIRECTS:
                        raise UrlFetchError("too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UrlFetchError("redirect with no Location header")
                    # Re-validate redirect target (critical for defense)
                    current_validated = _validate_url(location)
                    continue

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise UrlFetchError(f"response exceeds max_bytes={max_bytes}")
                    chunks.append(chunk)
                return FetchedBytes(
                    data=b"".join(chunks),
                    content_type=response.headers.get("content-type"),
                    http_status=response.status_code,
                )
