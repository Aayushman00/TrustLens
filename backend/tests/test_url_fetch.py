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
    httpserver.expect_request("/big.csv").respond_with_data(b"x" * 20_000_000, content_type="text/csv")
    url = httpserver.url_for("/big.csv")
    with pytest.raises(UrlFetchError, match="size|exceeds"):
        fetch_dataset_url(url, max_bytes=1_000_000)


def test_successful_fetch(httpserver, _localhost_allowed_for_fetch):
    httpserver.expect_request("/data.csv").respond_with_data(b"a,b\n1,2\n", content_type="text/csv")
    url = httpserver.url_for("/data.csv")
    result = fetch_dataset_url(url)
    assert result.data == b"a,b\n1,2\n"
    assert result.http_status == 200
