import ipaddress
import socket
from unittest.mock import MagicMock, Mock, patch

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


def test_rejects_oversized_response(httpserver, _localhost_allowed_for_fetch):
    """Test that oversized responses are rejected during streaming."""
    url = httpserver.url_for("/big.csv")

    # Mock httpx.Client.stream to simulate large response
    with patch("httpx.Client.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "text/csv"
        # Return chunks that exceed max_bytes limit
        mock_response.iter_bytes.return_value = [b"x" * 500_000 for _ in range(50)]  # Total 25MB
        mock_stream.return_value.__enter__.return_value = mock_response

        with pytest.raises(UrlFetchError, match="size|exceeds"):
            fetch_dataset_url(url, max_bytes=1_000_000)


def test_successful_fetch(httpserver, _localhost_allowed_for_fetch):
    """Test successful fetch with validated hostname and correct Host header."""
    url = httpserver.url_for("/data.csv")

    # Mock httpx.Client.stream to simulate successful response
    with patch("httpx.Client.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "text/csv"
        mock_response.iter_bytes.return_value = [b"a,b\n1,2\n"]
        mock_stream.return_value.__enter__.return_value = mock_response

        result = fetch_dataset_url(url)
        assert result.data == b"a,b\n1,2\n"
        assert result.http_status == 200
        assert result.content_type == "text/csv"

        # Verify that stream was called with pinned IP URL, not hostname
        call_args = mock_stream.call_args
        request_url = call_args[0][1]  # Second positional arg is URL
        # URL should contain IP address (from validation), not "localhost"
        assert "localhost" not in request_url, f"URL should use pinned IP, not hostname: {request_url}"


def test_dns_rebinding_defense(monkeypatch):
    """Verify DNS rebinding defense: validation-time IP is pinned, not re-resolved at connect.

    Attack scenario: attacker controls DNS. They return a public IP (1.1.1.1) when we validate,
    but a private IP (127.0.0.1) when httpx tries to connect. Without pinning, httpx would
    connect to 127.0.0.1 (internal) even though we validated 1.1.1.1 (public).

    This test mocks socket.getaddrinfo to return different IPs on subsequent calls:
    - First call (validation): returns 1.1.1.1 (public, passes SSRF check)
    - Second call (if httpx re-resolves): would return 127.0.0.1 (private, blocked)

    With proper connection pinning, fetch should succeed by connecting to 1.1.1.1,
    NOT re-resolve and connect to 127.0.0.1.
    """
    call_count = [0]  # Mutable counter to track calls
    public_ip_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0))]
    private_ip_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    def mock_getaddrinfo(host, port, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call (validation): return public IP
            return public_ip_info
        else:
            # Subsequent calls (connection time): would return private IP (attacker DNS rebinding)
            return private_ip_info

    # Mock socket.getaddrinfo to simulate DNS rebinding attack
    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # Mock httpx response to avoid actual network call to 1.1.1.1
    with patch("httpx.Client.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "text/csv"
        mock_response.iter_bytes.return_value = [b"data"]
        mock_stream.return_value.__enter__.return_value = mock_response

        # Fetch should succeed by connecting to the validated IP (1.1.1.1),
        # not re-resolving to the attacker's private IP (127.0.0.1)
        result = fetch_dataset_url("http://attacker.example.com/data.csv")
        assert result.data == b"data"
        assert result.http_status == 200

        # Verify that httpx.Client.stream was called with IP-based URL
        # (not hostname-based URL that would trigger getaddrinfo again)
        call_args = mock_stream.call_args
        assert call_args is not None
        request_url = call_args[0][1]  # Second positional arg is the URL
        # The URL should contain the IP (1.1.1.1), not the hostname
        assert "1.1.1.1" in request_url, f"Expected pinned IP in URL, got: {request_url}"


def test_redirect_to_private_ip_rejected():
    """Verify that redirects to private-IP URLs are rejected (re-validation on redirect).

    Test the critical re-validation path: when a server sends a redirect to a
    private IP, the SSRF check should reject it even if the initial request was valid.
    """
    with patch("httpx.Client.stream") as mock_stream:
        # Set up mock to return redirect on first call, then trigger validation of Location
        redirect_response = MagicMock()
        redirect_response.is_redirect = True
        redirect_response.headers.get.return_value = "http://169.254.169.254/metadata"  # AWS link-local
        mock_stream.return_value.__enter__.return_value = redirect_response

        # Should raise UrlFetchError when trying to follow redirect to private IP
        # (the Location header will be re-validated via _validate_url)
        with pytest.raises(UrlFetchError, match="private|link-local"):
            fetch_dataset_url("http://example.com/public")
