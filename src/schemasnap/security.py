"""Shared security helpers (rate-limit identity, URL validation)."""

from __future__ import annotations


def client_ip_from_forwarded(forwarded: str, fallback: str = "unknown") -> str:
    """Resolve client IP from X-Forwarded-For behind GCP Cloud Run.

    Clients may prepend spoofed IPs. Cloud Run appends the real client and
    Google frontend, so the client IP is second-to-last when multiple hops exist.
    """
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        if len(ips) >= 2:
            return ips[-2]
        if ips:
            return ips[-1]
    return fallback
