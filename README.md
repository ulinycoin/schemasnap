# SchemaSnap

[![PyPI version](https://img.shields.io/pypi/v/schemasnap.svg)](https://pypi.org/project/schemasnap/)
[![Python](https://img.shields.io/pypi/pyversions/schemasnap.svg)](https://pypi.org/project/schemasnap/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![tests](https://img.shields.io/badge/tests-100%20passed-brightgreen)](https://github.com/ulinycoin/schemasnap/actions)

**HTML → typed tables, forms, lists as JSON. 30ms, no key, no browser.**

Born from [shadow-web](https://github.com/ulinycoin/shadow-web)'s SchemaSnap module. A parse primitive — not a scraper, not a crawler. Feed it HTML, get structured data.

```bash
pip install "schemasnap[server]"
uvicorn schemasnap.server:app --port 8000 &

curl -X POST http://127.0.0.1:8000/v1/compress \
  -H "Content-Type: application/json" \
  -d '{"html":"<table><thead><tr><th>Product</th><th>Price</th><th>Stock</th></tr></thead><tbody><tr><td>Widget</td><td>$19.99</td><td>150</td></tr></tbody></table>"}'
```
```json
{"tables":[{"columns":["Product","Price","Stock"],
  "types":["string","currency","integer"],
  "rows":[["Widget","$19.99","150"]]}]}
```

## Self-hosted API

There is **no hosted endpoint** — the Cloud Run deployment was retired in October 2026.
Run it yourself; it is two commands:

```bash
pip install "schemasnap[server]"
uvicorn schemasnap.server:app --port 8000
```

| Endpoint | Auth | Notes |
|----------|------|-------|
| `POST /v1/compress` — HTML → structured JSON | none by default | stateless, pure `lxml`, ~30 ms |
| `GET /v1/health` | none | reads `__version__` from the package |
| `POST /v1/extract` — URL → structured JSON | — | off unless you set `DISABLE_EXTRACT=0`; needs Playwright |

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
curl -X POST http://127.0.0.1:8000/v1/compress \
  -H "Content-Type: application/json" \
  -d '{"html": "<table>...your html...</table>"}'
```

## Benchmarks

| Page | Raw | Compressed | Savings | Latency |
|------|-----|-----------|---------|---------|
| Wikipedia GDP | 641 KB | 215 KB | 66% | 256ms |
| W3Schools Tables | 212 KB | 87 KB | 59% | 34ms |
| Hacker News | 35 KB | 24 KB | 32% | 23ms |

*Measured July 2026 on a 1 vCPU / 256 MB instance (Cloud Run, us-central1), Python 3.12. Cold start ~250 ms — irrelevant when you call the library in-process.*

## Features

- **Tables** → columns, types (`string|integer|number|currency|percentage|date|email|url`), rows — from `<table>`, ARIA `role=table|grid`, Tailwind grids, or `.row` pseudo-tables
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

SchemaSnap started as `schema_snap.py` inside [shadow-web](https://github.com/ulinycoin/shadow-web) — a broader agent-facing web interaction suite.

Since 0.1.9 the direction is reversed: **this package is the implementation** and shadow-web depends on it (`schemasnap>=0.1.9`). Its `shadow_web.schema_snap` module is now a thin facade that re-exports these functions and keeps shadow-web's historic `source` vocabulary (`table`/`aria_grid`). One core, two facades, so a fix lands once.

What this standalone package adds on top of that module:

- MCP server (`compress_html` tool) for Cursor / Claude Desktop
- Tailwind and `.row` pseudo-table planes, plus ARIA `role=table|grid`
- Stacked multi-row headers with `colspan`/`rowspan` normalisation
- Deterministic type inference (8 types), zero-padded ids kept as strings
- Hardened for a public API (SSRF guard, rate limiting, oversize protection)

## License

MIT

---

#web-scraping #data-extraction #ai-agents #html-parser #json-api #python #llm-tools
