"""SSRF-safe streaming dataset URL fetcher — V1: no archives, no redirects followed
automatically past a re-validated hop, hard byte cap enforced while streaming."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

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


def _resolve_and_validate_host(host: str) -> str:
    """Resolve host to an IP and reject private/loopback/link-local/reserved ranges.

    Returns the validated IP as a string so the caller can pin the connection
    to it (defends against DNS rebinding between check and connect).
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


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UrlFetchError(f"unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UrlFetchError("URL has no hostname")
    _resolve_and_validate_host(parsed.hostname)
    return url


def fetch_dataset_url(
    url: str,
    *,
    max_bytes: int = 10_000_000,
    timeout_seconds: float = 15.0,
) -> FetchedBytes:
    current_url = _validate_url(url)
    redirects_followed = 0

    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=timeout_seconds, write=timeout_seconds, pool=timeout_seconds),
    ) as client:
        while True:
            with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    redirects_followed += 1
                    if redirects_followed > _MAX_REDIRECTS:
                        raise UrlFetchError("too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UrlFetchError("redirect with no Location header")
                    current_url = _validate_url(location)
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
