# Show HN: SchemaSnap — deterministic HTML → typed JSON parser

We've gotten very good at fetching web pages.

We have Firecrawl, Jina, Playwright, Browser Use, Crawl4AI, and plenty of browser automation tools.

But once you already have the HTML, there's still a surprisingly common problem:

**The missing piece is turning HTML into deterministic structured data.**

Most libraries stop at parsing HTML into a DOM. Most scraping tools return Markdown or raw text. LLMs can understand both — but they spend a lot of context reconstructing information that is already present in the page.

SchemaSnap takes a different approach.

It doesn't crawl. It doesn't render JavaScript. It doesn't use an LLM.

Instead, it accepts HTML and produces typed JSON. Same input → same output, every time.

```html
<table>
  <thead><tr><th>Product</th><th>Price</th><th>Stock</th></tr></thead>
  <tbody><tr><td>Widget</td><td>$19.99</td><td>150</td></tr></tbody>
</table>
```

becomes:

```json
{
  "tables": [{
    "columns": ["Product", "Price", "Stock"],
    "types": ["string", "currency", "integer"],
    "rows": [["Widget", "$19.99", "150"]]
  }]
}
```

No prompts. No model calls. No hallucinations. No API costs.

The parser also extracts forms (with field names, types, labels, required/pattern/minlength attributes, select options), lists, and semantic groups like "Login", "Navigation", "Checkout", and "Search".

## Why?

The idea came from building AI agents.

Agents rarely need an entire web page. Usually they need things like: what's in this table, what fields does this form have, which input is required, what options does this select contain.

Sending hundreds of kilobytes of HTML to an LLM just to recover that structure felt wasteful. You already paid the cost of fetching the page. SchemaSnap lets you keep the structure instead of reconstructing it with an LLM.

The browser already parsed the page. The HTML already contains the structure. SchemaSnap preserves that structure instead of asking an LLM to rediscover it.

## Where it fits

SchemaSnap is not another scraping framework. It's one component in a pipeline:

```
Playwright → HTML → SchemaSnap → Typed JSON → LLM / Agent
```

Or:

```
Firecrawl → HTML → SchemaSnap
```

Or:

```
requests → HTML → SchemaSnap
```

## What it intentionally does not do

- Crawl websites
- Execute JavaScript
- Rotate proxies
- Bypass anti-bot protection

Those problems are already solved by excellent tools. SchemaSnap does one thing: turning HTML into predictable, structured data. Built on lxml, ~30ms typical latency.

## Try it

**Python:**
```bash
pip install schemasnap
```

**MCP server for Cursor/Claude:**
```bash
pip install "schemasnap[mcp]"
```

**Run the API locally (no hosted endpoint, no auth):**
```bash
pip install "schemasnap[server]" && uvicorn schemasnap.server:app --port 8000
```
```bash
curl -X POST http://127.0.0.1:8000/v1/compress \
  -H "Content-Type: application/json" \
  -d '{"html":"<table><thead><tr><th>Product</th><th>Price</th><th>Stock</th></tr></thead><tbody><tr><td>Widget</td><td>$19.99</td><td>150</td></tr></tbody></table>"}'
```

**GitHub:** https://github.com/ulinycoin/schemasnap

54 tests, 0 failures. MIT license.

I'd appreciate feedback from people building agents, scraping pipelines, or automation tools — especially use cases I haven't considered.
