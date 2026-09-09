import socket
from unittest.mock import patch

import httpx
import pytest

from app.datasets.url_fetch import UrlFetchError, fetch_dataset_url


def test_rejects_non_http_scheme():
    with pytest.raises(UrlFetchError, match="scheme"):
        fetch_dataset_url("file:///etc/passwd")


def test_rejects_loopback_address():
    with pytest.raises(UrlFetchError, match="private|loopback"):
        fetch_dataset_url("http://127.0.0.1/data.csv")


def test_rejects_link_local_address():
    with pytest.raises(UrlFetchError, match="private|link-local"):
        fetch_dataset_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_private_rfc1918_address():
    with pytest.raises(UrlFetchError, match="private"):
        fetch_dataset_url("http://10.0.0.5/data.csv")


def test_successful_fetch(httpserver, _localhost_allowed_for_fetch):
    """Test successful fetch validates URL and streams response (real httpserver).

    Uses real httpserver to demonstrate connection pinning works correctly.
    The fixture allows localhost/loopback to pass SSRF validation for testing purposes.
    """
    httpserver.expect_request("/data.csv").respond_with_data(b"a,b\n1,2\n", content_type="text/csv")
    url = httpserver.url_for("/data.csv")
    result = fetch_dataset_url(url)
    assert result.data == b"a,b\n1,2\n"
    assert result.http_status == 200
    assert result.content_type == "text/csv"


def test_rejects_oversized_response(httpserver, _localhost_allowed_for_fetch):
    """Test that oversized responses are rejected during streaming (real httpserver).

    Uses real httpserver to demonstrate byte-cap enforcement works.
    """
    httpserver.expect_request("/big.csv").respond_with_data(b"x" * 20_000_000, content_type="text/csv")
    url = httpserver.url_for("/big.csv")
    with pytest.raises(UrlFetchError, match="size|exceeds"):
        fetch_dataset_url(url, max_bytes=1_000_000)


def test_https_sni_extension_set_to_original_hostname():
    """Verify SNI extension is actually set to the original hostname.

    CRITICAL TEST: Proves that the sni_hostname extension is set when making
    HTTPS requests. Uses httpx.MockTransport to intercept the real Request
    object that would be sent, without needing a live TLS server.

    The test:
    1. Mocks DNS resolution to return a public IP (93.184.216.34 = example.com's real IP)
    2. Uses MockTransport to intercept httpx's request-building code
    3. Asserts the request has sni_hostname="example.com" in extensions
    4. Asserts the request URL connects to the pinned IP (93.184.216.34), not the hostname
    """
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, content=b"data", headers={"content-type": "text/csv"})

    # Mock DNS to return example.com's real public IP
    with patch("app.datasets.url_fetch._resolve_and_validate_host", return_value="93.184.216.34"):
        # Patch httpx.Client to use MockTransport while keeping all other kwargs
        # (this lets real request building happen through our code path)
        original_client_init = httpx.Client.__init__

        def patched_client_init(self, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            original_client_init(self, **kw)

        with patch.object(httpx.Client, "__init__", patched_client_init):
            result = fetch_dataset_url("https://example.com/data.csv")

    # Verify the fetch succeeded
    assert result.data == b"data"
    assert result.http_status == 200

    # Verify SNI extension was set correctly
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.extensions.get("sni_hostname") == "example.com", \
        f"Expected sni_hostname='example.com', got {request.extensions}"

    # Verify connection was pinned to the IP, not the hostname
    assert request.url.host == "93.184.216.34", \
        f"Expected URL host='93.184.216.34', got {request.url.host}"


def test_dns_rebinding_defense(httpserver, _localhost_allowed_for_fetch):
    """Verify DNS rebinding defense: connection uses pinned IP, not re-resolved hostname.

    CRITICAL TEST: Proves that once we resolve and validate an IP, we connect to that
    exact IP in the request URL, preventing re-resolution at connection time. Uses real
    httpserver plus monkeypatched socket.getaddrinfo to track DNS resolution behavior.

    The test:
    1. Monkeypatches getaddrinfo for a fake "attacker.example" hostname
    2. Makes it return the real httpserver's address (simulating successful validation)
    3. Calls fetch_dataset_url with that fake hostname
    4. Asserts getaddrinfo was called at least once for validation
    5. Asserts the request successfully reaches the real httpserver (proving pinning worked)
    6. Confirms that once we have the IP, we use it directly (not via hostname in request)

    The critical defense: even if the attacker's DNS changes after validation,
    the request goes to the validated IP, not a re-resolved one.
    """
    httpserver.expect_request("/data.csv").respond_with_data(b"a,b\n1,2\n", content_type="text/csv")
    server_ip = "127.0.0.1"  # httpserver binds to this after our fixture reorders DNS
    server_port = httpserver.port

    call_count = {"attacker.example": 0}
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "attacker.example":
            call_count["attacker.example"] += 1
            # Return the real test server's address, simulating successful validation
            return real_getaddrinfo(server_ip, *args, **kwargs)
        return real_getaddrinfo(host, *args, **kwargs)

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        result = fetch_dataset_url(f"http://attacker.example:{server_port}/data.csv")

    # Verify the fetch succeeded by reaching the real server
    assert result.data == b"a,b\n1,2\n"
    assert result.http_status == 200

    # CRITICAL: "attacker.example" must be resolved EXACTLY ONCE — during
    # _resolve_and_validate_host's validation pass. If connection pinning were
    # broken (e.g. the pinned-IP URL were replaced with a hostname URL), httpx/
    # httpcore would independently resolve "attacker.example" again at connect
    # time in order to open the TCP socket, pushing this count to 2+. A ">= 1"
    # assertion here would be satisfied in both the pinned and unpinned case and
    # proves nothing; "== 1" is what actually discriminates pinned behavior from
    # unpinned behavior (verified by deliberately breaking pinning — see
    # task-1.3-report.md round 4 for the red/green evidence).
    assert call_count["attacker.example"] == 1, (
        f"Expected exactly one resolution of 'attacker.example' (during "
        f"validation only), got {call_count['attacker.example']}. A count > 1 "
        f"means the hostname was re-resolved at connect time, i.e. connection "
        f"pinning is NOT in effect and DNS rebinding is possible."
    )


def test_redirect_to_private_ip_rejected(httpserver, _localhost_allowed_for_fetch):
    """Verify redirects to private IPs are rejected via re-validation (real redirect).

    CRITICAL TEST: Proves the redirect re-validation path — not the initial-URL
    check — is what rejects the request.

    Why this needs care: pytest-httpserver binds to 127.0.0.1, which is itself a
    loopback address. If the *initial* request used strict (unrelaxed) SSRF
    validation, it would be rejected before the server ever sent its 302
    response, and the redirect-handling code would never run — the exact bug
    found in round 3 (httpserver.log was empty afterwards, proving no request
    was ever sent).

    The fix: use the same `_localhost_allowed_for_fetch` fixture the other
    httpserver-based tests use, so the *initial* request to
    `httpserver.url_for(...)` (127.0.0.1) is allowed through. The redirect's
    `Location` then points at 10.0.0.5 — a private RFC1918 address that is
    NOT in the fixture's localhost/loopback allowlist — so it is the
    *redirect re-validation* branch (running after `response.is_redirect`)
    that must reject it, genuinely exercising that code path.

    The test also asserts on `httpserver.log` to prove the initial request
    really was sent to and served by the real server (i.e. the 302 was
    actually issued), not merely that some exception happened to be raised.
    """
    from werkzeug.wrappers import Response

    httpserver.expect_request("/start.csv").respond_with_response(
        Response(status=302, headers={"Location": "http://10.0.0.5:1/data.csv"})
    )
    url = httpserver.url_for("/start.csv")

    # The fetch should fail when trying to follow the redirect to 10.0.0.5 (a
    # private RFC1918 address the fixture does NOT exempt).
    with pytest.raises(UrlFetchError, match="private|loopback"):
        fetch_dataset_url(url)

    # Prove the initial request was genuinely sent to and answered by the real
    # server (the 302 with its malicious Location header actually round-tripped)
    # rather than the request having been rejected before ever reaching it.
    assert len(httpserver.log) == 1, (
        "Expected exactly one real request to the httpserver (the initial "
        "/start.csv request that received the 302). An empty log means the "
        "initial URL was rejected before the redirect was ever sent, and the "
        "redirect re-validation code path was never exercised."
    )
    received_request, _ = httpserver.log[0]
    assert received_request.path == "/start.csv"
