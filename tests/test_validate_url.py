"""Unit tests for URL validation (SSRF guard)."""

import pytest
from schemasnap.extractor import validate_url


def test_validate_url_allows_https():
    assert validate_url("https://example.com") == ""
    assert validate_url("https://en.wikipedia.org/wiki/Python") == ""


def test_validate_url_allows_http():
    assert validate_url("http://example.com") == ""


def test_validate_url_blocks_localhost_string():
    assert "Blocked" in validate_url("http://localhost")
    assert "Blocked" in validate_url("http://localhost:8080/path")


def test_validate_url_blocks_loopback_ip():
    assert "Blocked" in validate_url("http://127.0.0.1")
    assert "Blocked" in validate_url("http://127.0.0.1:3000/api")


def test_validate_url_blocks_private_ips():
    assert "Blocked" in validate_url("http://10.0.0.1")
    assert "Blocked" in validate_url("http://192.168.1.1")
    assert "Blocked" in validate_url("http://172.16.0.1")


def test_validate_url_blocks_link_local():
    assert "Blocked" in validate_url("http://169.254.169.254")  # AWS metadata


def test_validate_url_blocks_zero_network():
    assert "Blocked" in validate_url("http://0.0.0.0")


def test_validate_url_rejects_non_http_schemes():
    assert "Unsupported scheme" in validate_url("ftp://example.com")
    assert "Unsupported scheme" in validate_url("file:///etc/passwd")
    assert "Unsupported scheme" in validate_url("gopher://example.com")


def test_validate_url_rejects_empty():
    assert "required" in validate_url("")
    assert "required" in validate_url(None)


def test_validate_url_rejects_no_hostname():
    assert "no hostname" in validate_url("http://")


def test_validate_url_allows_ipv4_public():
    assert validate_url("http://8.8.8.8") == ""
    assert validate_url("http://1.1.1.1") == ""


def test_validate_url_allows_complex_urls():
    assert validate_url("https://user:pass@example.com:8080/path?q=1#frag") == ""


def test_validate_url_blocks_ipv6_localhost():
    assert "Blocked" in validate_url("http://[::1]")
    assert "Blocked" in validate_url("http://[::1]:8080/path")


def test_validate_url_allows_ipv6_public():
    # Google's IPv6
    assert validate_url("http://[2001:4860:4860::8888]") == ""
