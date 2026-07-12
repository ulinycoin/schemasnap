# SchemaSnap

[![PyPI version](https://img.shields.io/pypi/v/schemasnap.svg)](https://pypi.org/project/schemasnap/)
[![Python](https://img.shields.io/pypi/pyversions/schemasnap.svg)](https://pypi.org/project/schemasnap/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![tests](https://img.shields.io/badge/tests-54%20passed-brightgreen)](https://github.com/ulinycoin/schemasnap/actions)

**HTML → typed tables, forms, lists as JSON. 30ms, no key, no browser.**

Born from [shadow-web](https://github.com/ulinycoin/shadow-web)'s SchemaSnap module. A parse primitive — not a scraper, not a crawler. Feed it HTML, get structured data.

```bash
curl -X POST https://schemasnap-464919960073.us-central1.run.app/v1/compress \
  -H "Content-Type: application/json" \
  -d '{"html":"<table><thead><tr><th>Product</th><th>Price</th><th>Stock</th></tr></thead><tbody><tr><td>Widget</td><td>$19.99</td><td>150</td></tr></tbody></table>"}'
```
```json
{"tables":[{"columns":["Product","Price","Stock"],
  "types":["string","currency","integer"],
  "rows":[["Widget","$19.99","150"]]}]}
```

## Live API

| Endpoint | Rate limit | Auth |
|----------|-----------|------|
| `POST /v1/compress` — HTML → structured JSON | 500 req/day per IP | None |
| `GET /v1/health` | Unlimited | None |

**Base URL:** `https://schemasnap-464919960073.us-central1.run.app`

## Quick install

```bash
pip install schemasnap

# For MCP (Cursor, Claude Desktop)
pip install "schemasnap[mcp]"

# For URL extraction (requires Playwright)
pip install "schemasnap[browser]"
playwright install chromium
```

## Usage

### Python SDK

```python
from schemasnap import extract_from_html, parse_page

# From HTML string (no browser, 30ms)
result = extract_from_html(open("page.html").read())
print(result.tables)      # [{columns, types, rows, total_rows}]
print(result.forms)       # [{action, method, fields}]
print(result.lists)       # [{type, items, total}]
print(result.token_budget) # {raw_bytes, compressed_bytes, compression_ratio}
```

### MCP (Cursor, Claude Desktop)

```bash
pip install "schemasnap[mcp]"
```

Add to Cursor **Settings → MCP**:

```json
{
  "mcpServers": {
    "schemasnap": {
      "command": "schemasnap-mcp"
    }
  }
}
```

**Tool:** `compress_html(html, max_rows_per_table=50, url="")` → typed tables, forms, lists, actions.

### curl (no Python needed)

```bash
curl -X POST https://schemasnap-464919960073.us-central1.run.app/v1/compress \
  -H "Content-Type: application/json" \
  -d '{"html": "<table>...your html...</table>"}'
```

## Benchmarks

| Page | Raw | Compressed | Savings | Latency |
|------|-----|-----------|---------|---------|
| Wikipedia GDP | 641 KB | 215 KB | 66% | 256ms |
| W3Schools Tables | 212 KB | 87 KB | 59% | 34ms |
| Hacker News | 35 KB | 24 KB | 32% | 23ms |

*Measured on Cloud Run (us-central1), July 2026. Cold start ~250ms.*

## Features

- **Tables** → columns, types (`string|integer|number|currency|percentage|date|email|url`), rows, total_rows
- **Forms** → action, method, fields with `name`, `type`, `label`, `required`, `placeholder`, `pattern`, `minlength`, select `options`
- **Lists** → type (`unordered|ordered|select`), items, total
- **Semantic groups** → "Login Form", "Navigation", "Checkout", "Search" auto-detected
- **Deterministic** — same input → same output. No LLM guess, $0 per call

## Competitive positioning

SchemaSnap is a **parse primitive**, not a scraper:

```
Firecrawl / Jina     =  URL → content (crawl + render)
Crawl4AI             =  URL → markdown (self-host crawl)
pandas read_html()   =  HTML → strings (dev tool)
SchemaSnap           =  HTML → typed structure (agent utility)
```

Composable: `Firecrawl fetch → SchemaSnap parse`. Or `curl → SchemaSnap parse`.

**Honest limits:** HTML only (no JS render), layout tables skipped, no crawl, no proxy rotation.

## Relationship to shadow-web

SchemaSnap started as `schema_snap.py` inside [shadow-web](https://github.com/ulinycoin/shadow-web) — a broader agent-facing web interaction suite. This standalone version:

- Adds MCP server (`compress_html` tool) for Cursor / Claude Desktop
- Inlines semantic grouping (no external dependency)
- Fixes tree mutation bug during tag removal
- Adds deterministic type inference (8 types)
- Hardened for public API (SSRF guard, rate limiting, oversize protection)

## License

MIT

---

#web-scraping #data-extraction #ai-agents #html-parser #json-api #python #llm-tools
