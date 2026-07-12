# SchemaSnap — Project Memory (Hot Cache)

## Quick Context

SchemaSnap is the standalone extraction engine extracted from [shadow-web](https://github.com/ulinycoin/shadow-web). One job: URL or HTML → structured data (tables, forms, lists) as JSON.

Born: July 2026. v0.1.0. Alpha.

## Directory Structure

```
schemasnap/
├── pyproject.toml              # Build config (setuptools)
├── README.md                   # User-facing docs
├── ROADMAP.md                  # 6-phase plan with kill/success criteria
├── CLAUDE.md                   # This file
├── src/
│   └── schemasnap/
│       ├── __init__.py         # Exports (extract_from_url, parse_page, ...)
│       ├── schema_snap.py      # Core extraction engine (lxml) — from shadow-web
│       ├── compressor.py       # HTML cleaning + Action Map + semantic groups
│       ├── extractor.py        # Playwright orchestrator (URL → structured data)
│       └── server.py           # FastAPI server (/v1/extract, /v1/compress)
└── tests/
    ├── test_compressor.py      # Compressor unit tests
    ├── test_schema_snap.py     # Schema extraction unit tests
    └── test_integration.py     # Full pipeline (URL → extract)
```

## Key Differences from shadow-web

| shadow-web | SchemaSnap |
|-----------|------------|
| 18 modules, 6,259 lines | 3 core modules, ~1,500 lines |
| 24 MCP tools | 1 API endpoint |
| Healing, security scan, form fill | Extraction only |
| Hard grouping.py dependency | Inlined grouping (zero external deps beyond lxml) |
| Tree mutation bug in compressor | Fixed (collect nodes before removal) |
| No server input validation | 5 MB cap, rate limiter with pruning |
| `process_html` returns 3-tuple | Returns 2-tuple (no separate groups) |

## Development

```bash
# Install
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run extraction-only tests (no browser)
pytest tests/test_compressor.py tests/test_schema_snap.py -v

# Run server
pip install -e ".[server]"
uvicorn schemasnap.server:app --reload --port 8000
```

## Dependencies

- **Core (always):** lxml, pydantic
- **Browser (extract_from_url):** playwright
- **Server:** fastapi, uvicorn, playwright

## Design Decisions

1. **SchemaSnap is NOT shadow-web-lite.** It's a purpose-built extraction engine. No MCP, no healing, no security scan.
2. **Python-first, browser-optional.** `extract_from_html()` works without Playwright — pure lxml.
3. **One call, one result.** `extract_from_url()` does navigate → compress → extract in one function. No multi-step agent workflow.
4. **Stateless where possible.** `/v1/compress` is pure function. `/v1/extract` is the only stateful endpoint (Playwright browser).
