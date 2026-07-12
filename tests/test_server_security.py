"""Security tests for IP extraction and SSRF guards."""

import pytest

from schemasnap.extractor import validate_url
from schemasnap.security import client_ip_from_forwarded


def test_client_ip_uses_second_to_last_in_proxy_chain():
    """Spoofed first hop must not become rate-limit identity."""
    xff = "10.0.0.99, 203.0.113.10, 169.254.1.1"
    assert client_ip_from_forwarded(xff) == "203.0.113.10"


def test_client_ip_single_forwarded_hop():
    assert client_ip_from_forwarded("203.0.113.10") == "203.0.113.10"


def test_client_ip_two_hop_chain():
    assert client_ip_from_forwarded("203.0.113.10, 169.254.1.1") == "203.0.113.10"


def test_client_ip_falls_back_to_socket_client():
    assert client_ip_from_forwarded("", "198.51.100.7") == "198.51.100.7"


def test_validate_url_blocks_metadata_hostname():
    assert "Blocked" in validate_url("http://metadata.google.internal")


def test_validate_url_blocks_internal_suffix():
    assert "Blocked" in validate_url("http://foo.internal")


@pytest.mark.integration
def test_validate_url_blocks_nip_io_rebinding():
    assert "Blocked" in validate_url("http://127.0.0.1.nip.io")
