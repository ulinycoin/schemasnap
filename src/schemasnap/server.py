"""
SchemaSnap API Server — FastAPI.

Endpoints:
  POST /v1/extract  — navigate URL → compress → extract → return structured data
  POST /v1/compress — compress raw HTML + SchemaSnap extraction (no browser)
  GET  /v1/health   — service health check

Usage:
  pip install "schemasnap[server]"
  uvicorn schemasnap.server:app --reload --port 8000
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from schemasnap.extractor import extract_from_html, ExtractResult
from schemasnap.compressor import process_html
from schemasnap.schema_snap import parse_page

# extract_from_url requires Playwright — wrapped in lazy import
_extract_from_url = None


def _get_extract_from_url():
    global _extract_from_url
    if _extract_from_url is None:
        try:
            from schemasnap.extractor import extract_from_url as _fn
            _extract_from_url = _fn
        except ImportError:
            _extract_from_url = False
    return _extract_from_url

app = FastAPI(
    title="SchemaSnap",
    description="Structured data extraction API — tables, forms, lists from any URL or HTML",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Rate limiter (in-memory, per-IP) ─────────────────────────────

_RATE_LIMIT = int(os.environ.get("SCHEMASNAP_RATE_LIMIT", "100"))
_RATE_WINDOW_SEC = int(os.environ.get("SCHEMASNAP_RATE_WINDOW", "86400"))

_rate_buckets: Dict[str, List[float]] = {}


def _check_rate_limit(client_ip: str) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    now = time.time()
    window_start = now - _RATE_WINDOW_SEC
    bucket = _rate_buckets.setdefault(client_ip, [])
    # Prune old entries
    bucket[:] = [t for t in bucket if t > window_start]
    if len(bucket) >= _RATE_LIMIT:
        return False
    bucket.append(now)
    # Cap bucket size to prevent memory growth
    if len(bucket) > _RATE_LIMIT + 100:
        bucket[:] = bucket[-_RATE_LIMIT:]
    return True


# ── Request/Response models ──────────────────────────────────────


class ExtractRequest(BaseModel):
    url: str = Field(..., description="URL to extract data from")
    max_rows_per_table: Optional[int] = Field(50, description="Cap rows per table")
    wait_for_selector: Optional[str] = Field(None, description="CSS selector to wait for")
    timeout_ms: int = Field(30000, ge=5000, le=60000, description="Page load timeout")


class CompressRequest(BaseModel):
    html: str = Field(..., max_length=5_000_000, description="Raw HTML to compress (max 5 MB)")
    url: str = Field("", description="Optional source URL for metadata")
    max_rows_per_table: Optional[int] = Field(50, description="Cap rows per table")


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""


# ── Endpoints ───────────────────────────────────────────────────


@app.get("/v1/health")
async def health():
    from schemasnap import __version__
    return {"status": "ok", "version": __version__, "timestamp": time.time()}


@app.post("/v1/extract")
async def extract(request: Request, body: ExtractRequest):
    """Navigate to URL, extract tables/forms/lists as structured JSON."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    import asyncio

    fn = _get_extract_from_url()
    if not fn:
        raise HTTPException(status_code=501, detail="/v1/extract unavailable: Playwright not installed")

    result = await asyncio.to_thread(
        fn,
        body.url,
        timeout_ms=body.timeout_ms,
        max_rows_per_table=body.max_rows_per_table,
        wait_for_selector=body.wait_for_selector,
    )

    if result.error:
        return JSONResponse(
            status_code=422,
            content={"error": "extraction_failed", "detail": result.error},
        )

    return result.to_dict()


@app.post("/v1/compress")
async def compress(request: Request, body: CompressRequest):
    """Compress raw HTML and extract structured data. No browser needed."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    result = extract_from_html(
        body.html,
        url=body.url,
        max_rows_per_table=body.max_rows_per_table,
    )

    # Track usage (fire-and-forget, non-blocking)
    _posthog_capture("compress_request", {
        "$ip": client_ip,
        "url": body.url or "(inline)",
        "html_bytes": len(body.html.encode("utf-8", errors="replace")),
        "compression_ratio": result.compression_ratio,
        "table_count": len(result.tables),
        "form_count": len(result.forms),
        "elapsed_ms": result.elapsed_ms,
    })

    if result.error:
        return JSONResponse(
            status_code=422,
            content={"error": "compression_failed", "detail": result.error},
        )

    return result.to_dict()


# ── Startup ─────────────────────────────────────────────────────

# PostHog — lightweight event capture (no SDK dep)
_PH_KEY = os.environ.get("POSTHOG_API_KEY", "")
_PH_HOST = os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com")


def _posthog_capture(event: str, properties: dict = None):
    """Fire-and-forget PostHog event. Non-blocking."""
    if not _PH_KEY:
        return
    try:
        import urllib.request, json

        payload = json.dumps({
            "api_key": _PH_KEY,
            "event": event,
            "properties": properties or {},
            "timestamp": time.time(),
            "distinct_id": properties.get("$ip", "unknown") if properties else "unknown",
        }).encode()
        req = urllib.request.Request(
            f"{_PH_HOST}/capture/",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # never block on analytics failure

def main():
    """Entry point for `schemasnap-server` CLI command."""
    import uvicorn
    uvicorn.run("schemasnap.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
