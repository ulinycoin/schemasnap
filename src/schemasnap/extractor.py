"""
SchemaSnap Extractor — URL → structured data pipeline.

Orchestrates Playwright navigation, HTML compression, and SchemaSnap extraction
into a single call. Designed as the engine behind the /v1/extract API.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .compressor import process_html
from .schema_snap import parse_page

# ── URL safety ────────────────────────────────────────────────────

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]


def validate_url(url: str) -> str:
    """Validate and sanitize a URL. Returns error message or empty string on success."""
    if not url or not isinstance(url, str):
        return "URL is required"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Unsupported scheme: {parsed.scheme}"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return "Invalid URL: no hostname"
    if hostname in ("localhost", "0.0.0.0", "[::1]", "::1"):
        return "Blocked: localhost"
    try:
        ip = ipaddress.ip_address(hostname)
        for net in _PRIVATE_NETS:
            if ip in net:
                return f"Blocked: private/internal IP ({ip})"
    except ValueError:
        pass  # Not an IP — hostname, fine
    return ""


@dataclass
class ExtractResult:
    """Result of a single URL extraction."""

    url: str
    title: str = ""
    page_class: str = "Static"

    # Token budget
    raw_html_bytes: int = 0
    compressed_html_bytes: int = 0
    compression_ratio: float = 0.0

    # Structured data
    tables: List[Dict[str, Any]] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    lists: List[Dict[str, Any]] = field(default_factory=list)

    # Interactive surface
    action_count: int = 0
    actions: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    elapsed_ms: float = 0.0

    # Error
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "page_class": self.page_class,
            "token_budget": {
                "raw_bytes": self.raw_html_bytes,
                "compressed_bytes": self.compressed_html_bytes,
                "compression_ratio": round(self.compression_ratio, 2),
            },
            "tables": self.tables,
            "forms": self.forms,
            "lists": self.lists,
            "actions": self.actions,
            "action_count": self.action_count,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


def classify_page(page) -> tuple[str, str]:
    """Quick page classifier — detects SPA, anti-bot, auth-gated pages."""
    title_lower = ""
    try:
        title_lower = page.title().lower()
    except Exception:
        pass
    url_lower = ""
    try:
        url_lower = page.url.lower()
    except Exception:
        pass

    anti_bot_signals = ["captcha", "blocked", "challenge", "access denied", "verify"]
    for signal in anti_bot_signals:
        if signal in title_lower or signal in url_lower:
            return "Anti-bot", f"Detected '{signal}' in page context"

    # Check for auth redirects
    auth_patterns = ["/login", "/signin", "/auth", "redirect_uri"]
    try:
        current_url = page.url.lower()
        for pattern in auth_patterns:
            if pattern in current_url:
                return "Auth-gated", f"Redirected to authentication: {page.url[:120]}"
    except Exception:
        pass

    # Detect SPA via JS framework signals (quick check)
    try:
        has_framework = page.evaluate(
            """() => {
            return !!(window.__NEXT_DATA__ || window.__NUXT__ ||
                     document.querySelector('[data-reactroot]') ||
                     document.querySelector('#app') ||
                     document.querySelector('[ng-version]'));
        }"""
        )
        if has_framework:
            return "SPA", "JavaScript framework detected"
    except Exception:
        pass

    return "Static", "Standard server-rendered page"


def extract_from_url(
    url: str,
    *,
    timeout_ms: int = 30000,
    max_rows_per_table: Optional[int] = 50,
    wait_for_selector: Optional[str] = None,
) -> ExtractResult:
    """
    Extract structured data from a URL.

    Pipeline: Playwright navigate → classify → compress → SchemaSnap extract.

    Args:
        url: Full URL to extract data from.
        timeout_ms: Page load timeout.
        max_rows_per_table: Cap rows per table (None = unlimited).
        wait_for_selector: Optional CSS selector to wait for before extraction.

    Returns:
        ExtractResult with tables, forms, lists, actions, and metadata.
    """
    from playwright.sync_api import sync_playwright

    result = ExtractResult(url=url)
    t0 = time.monotonic()

    # Validate URL before launching browser
    url_error = validate_url(url)
    if url_error:
        result.error = url_error
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                if wait_for_selector:
                    page.wait_for_selector(wait_for_selector, timeout=timeout_ms)

                result.title = page.title()
                result.page_class, _ = classify_page(page)

                # Get raw HTML
                raw_html = page.content()
                result.raw_html_bytes = len(raw_html.encode("utf-8"))

                # Compress
                clean_html, action_map = process_html(raw_html)
                result.compressed_html_bytes = len(clean_html.encode("utf-8"))
                if result.raw_html_bytes > 0:
                    result.compression_ratio = round(
                        1 - result.compressed_html_bytes / result.raw_html_bytes, 4
                    )

                result.actions = action_map
                result.action_count = len(action_map)

                # SchemaSnap extraction (on clean HTML for better accuracy)
                structured = parse_page(clean_html, max_rows=max_rows_per_table)
                result.tables = structured["tables"]
                result.forms = structured["forms"]
                result.lists = structured["lists"]

            finally:
                browser.close()

    except Exception as exc:
        result.error = str(exc)

    result.elapsed_ms = (time.monotonic() - t0) * 1000
    return result


def extract_from_html(
    html: str,
    *,
    url: str = "",
    max_rows_per_table: Optional[int] = 50,
) -> ExtractResult:
    """
    Extract structured data from raw HTML string (no browser).

    Pipeline: compress → SchemaSnap extract. Stateless, fast.
    """
    t0 = time.monotonic()
    result = ExtractResult(url=url or "(inline HTML)")

    try:
        result.raw_html_bytes = len(html.encode("utf-8"))
        clean_html, action_map = process_html(html)
        result.compressed_html_bytes = len(clean_html.encode("utf-8"))
        if result.raw_html_bytes > 0:
            result.compression_ratio = round(
                1 - result.compressed_html_bytes / result.raw_html_bytes, 4
            )

        result.actions = action_map
        result.action_count = len(action_map)

        structured = parse_page(clean_html, max_rows=max_rows_per_table)
        result.tables = structured["tables"]
        result.forms = structured["forms"]
        result.lists = structured["lists"]

    except Exception as exc:
        result.error = str(exc)

    result.elapsed_ms = (time.monotonic() - t0) * 1000
    return result
