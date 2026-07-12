# SchemaSnap

**Structured data extraction from any URL — tables, forms, lists as JSON.**

Born from [shadow-web](https://github.com/ulinycoin/shadow-web)'s SchemaSnap module. Focused, standalone, and designed to be the API that AI agents (and humans) call when they need structured web data.

```python
from schemasnap import extract_from_url

result = extract_from_url("https://en.wikipedia.org/wiki/List_of_countries_by_GDP")
# result.tables[0] → {columns: ["Country", "GDP", ...], types: ["string", "currency", ...], rows: [[...], ...]}
# result.forms   → [{action: "/search", method: "GET", fields: [...]}]
# result.lists   → [{type: "unordered", items: ["Item 1", "Item 2"], total: 2}]
```

## What it does

| Input | Output | Browser needed? |
|-------|--------|----------------|
| URL | Tables + Forms + Lists as JSON | Yes (Playwright) |
| Raw HTML | Tables + Forms + Lists as JSON | No (lxml only) |

## Quick install

```bash
pip install schemasnap

# For URL extraction (requires Playwright)
pip install "schemasnap[browser]"
playwright install chromium

# For API server
pip install "schemasnap[server]"
```

## Usage

### Python SDK

```python
from schemasnap import extract_from_url, extract_from_html, parse_page

# From URL (needs Playwright)
result = extract_from_url("https://example.com/data")
print(result.tables)      # [{columns, types, rows, total_rows, ...}]
print(result.forms)       # [{action, method, fields: [{name, type, label, required}]}]
print(result.lists)       # [{type, items, total}]
print(result.token_budget) # {raw_bytes, compressed_bytes, compression_ratio}

# From HTML string (no browser)
html = open("page.html").read()
result = extract_from_html(html)
print(result.tables)
```

### API Server

```bash
pip install "schemasnap[server]"
uvicorn schemasnap.server:app --reload --port 8000
```

```bash
# Extract from URL
curl -X POST http://localhost:8000/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"url": "https://en.wikipedia.org/wiki/List_of_countries_by_GDP"}'

# Compress HTML
curl -X POST http://localhost:8000/v1/compress \
  -H "Content-Type: application/json" \
  -d '{"html": "<table>...", "url": "https://example.com"}'

# Health check
curl http://localhost:8000/v1/health
```

## Features

- **Tables** → columns, types (string/integer/number/currency/percentage/date/email/url), rows, total_rows
- **Forms** → action, method, fields with name, type, label, required, placeholder, options
- **Lists** → type (unordered/ordered/select), items, total
- **HTML compression** → 83-97% size reduction before extraction
- **Semantic groups** → "Login Form", "Navigation", "Checkout" auto-detected

## Relationship to shadow-web

SchemaSnap started as `schema_snap.py` inside [shadow-web](https://github.com/ulinycoin/shadow-web) — a broader agent-facing web interaction suite. This standalone version:

- Removes MCP server, security scan, self-healing, form fill, browser-use integration
- Inlines semantic grouping (no external dependency)
- Fixes the tree mutation bug during tag removal
- Adds FastAPI server with rate limiting and input validation
- Focuses entirely on one thing: URL → structured data

## License

MIT
