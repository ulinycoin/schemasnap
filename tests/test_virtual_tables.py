"""Tests for ARIA, Tailwind, and pseudo-table detection."""

from schemasnap.schema_snap import parse_tables, parse_page

# ── ARIA role=table (Stripe / Linear dashboard style) ────────────

ARIA_TABLE_HTML = """\
<html><body>
<div role="table" aria-label="Invoices">
  <div role="rowgroup">
    <div role="row">
      <div role="columnheader">Customer</div>
      <div role="columnheader">Amount</div>
      <div role="columnheader">Status</div>
    </div>
  </div>
  <div role="rowgroup">
    <div role="row">
      <div role="cell">Acme Corp</div>
      <div role="cell">$1,200.00</div>
      <div role="cell">Paid</div>
    </div>
    <div role="row">
      <div role="cell">Globex</div>
      <div role="cell">$450.50</div>
      <div role="cell">Pending</div>
    </div>
  </div>
</div>
</body></html>
"""

# ── Tailwind grid data-table (div-based, no <table>) ─────────────

TAILWIND_GRID_HTML = """\
<html><body>
<div class="rounded-md border">
  <div class="relative w-full overflow-auto">
    <div class="min-w-full divide-y">
      <div class="grid grid-cols-3 font-medium border-b">
        <div>Name</div><div>Email</div><div>Role</div>
      </div>
      <div class="grid grid-cols-3">
        <div>Alice</div><div>alice@co.com</div><div>Admin</div>
      </div>
      <div class="grid grid-cols-3">
        <div>Bob</div><div>bob@co.com</div><div>User</div>
      </div>
    </div>
  </div>
</div>
</body></html>
"""

# ── shadcn/ui — still uses semantic <table> ──────────────────────

SHADCN_TABLE_HTML = """\
<html><body>
<div class="rounded-md border">
  <table class="w-full caption-bottom text-sm">
    <thead class="border-b">
      <tr><th class="h-10 px-2">Invoice</th><th class="h-10 px-2">Status</th><th class="h-10 px-2">Amount</th></tr>
    </thead>
    <tbody>
      <tr><td class="p-2">INV001</td><td class="p-2">Paid</td><td class="p-2">$250.00</td></tr>
      <tr><td class="p-2">INV002</td><td class="p-2">Pending</td><td class="p-2">$150.00</td></tr>
    </tbody>
  </table>
</div>
</body></html>
"""

# ── GitHub Trending — Box-row pseudo-table ───────────────────────

GITHUB_TRENDING_HTML = """\
<html><body>
<article class="Box-sc">
  <div class="Box-row">
    <span>facebook/react</span><span>JavaScript</span><span>234k</span>
  </div>
  <div class="Box-row">
    <span>vercel/next.js</span><span>JavaScript</span><span>128k</span>
  </div>
  <div class="Box-row">
    <span>tailwindlabs/tailwindcss</span><span>CSS</span><span>82k</span>
  </div>
</article>
</body></html>
"""

# ── Airtable-like grid (role=grid) ───────────────────────────────

AIRTABLE_GRID_HTML = """\
<html><body>
<div role="grid" aria-label="Projects">
  <div role="row">
    <div role="columnheader">Project</div>
    <div role="columnheader">Owner</div>
    <div role="columnheader">Due</div>
  </div>
  <div role="row">
    <div role="gridcell">Website redesign</div>
    <div role="gridcell">Alice</div>
    <div role="gridcell">2026-08-01</div>
  </div>
  <div role="row">
    <div role="gridcell">API migration</div>
    <div role="gridcell">Bob</div>
    <div role="gridcell">2026-09-15</div>
  </div>
</div>
</body></html>
"""

# ── Vercel dashboard — native table inside Tailwind wrapper ──────

VERCEL_DASHBOARD_HTML = """\
<html><body>
<div class="min-w-full divide-y">
  <table class="min-w-full">
    <thead><tr><th>Deployment</th><th>Status</th><th>Duration</th></tr></thead>
    <tbody>
      <tr><td>schemasnap-abc</td><td>Ready</td><td>32s</td></tr>
      <tr><td>schemasnap-def</td><td>Building</td><td>—</td></tr>
    </tbody>
  </table>
</div>
</body></html>
"""


def test_aria_role_table_extraction():
    tables = parse_tables(ARIA_TABLE_HTML)
    assert len(tables) == 1
    t = tables[0]
    assert t["source"] == "aria"
    assert t["columns"] == ["Customer", "Amount", "Status"]
    assert t["total_rows"] == 2
    assert t["types"][1] == "currency"


def test_tailwind_grid_table_extraction():
    tables = parse_tables(TAILWIND_GRID_HTML)
    assert len(tables) >= 1
    t = next(tbl for tbl in tables if tbl.get("source") == "tailwind")
    assert "Name" in t["columns"]
    assert t["total_rows"] >= 2
    assert ["Alice", "alice@co.com", "Admin"] in t["rows"]


def test_shadcn_semantic_table_still_works():
    tables = parse_tables(SHADCN_TABLE_HTML)
    assert len(tables) == 1
    assert tables[0]["source"] == "native"
    assert tables[0]["columns"] == ["Invoice", "Status", "Amount"]
    assert tables[0]["types"][2] == "currency"


def test_github_trending_pseudo_table():
    tables = parse_tables(GITHUB_TRENDING_HTML)
    assert len(tables) == 1
    t = tables[0]
    assert t["source"] == "pseudo"
    assert t["total_rows"] == 3
    assert t["column_count"] == 3
    assert "facebook/react" in t["rows"][0][0]


def test_airtable_role_grid():
    tables = parse_tables(AIRTABLE_GRID_HTML)
    assert len(tables) == 1
    t = tables[0]
    assert t["source"] == "aria"
    assert t["columns"] == ["Project", "Owner", "Due"]
    assert t["types"][2] == "date"


def test_vercel_native_table_not_duplicated():
    tables = parse_tables(VERCEL_DASHBOARD_HTML)
    native = [t for t in tables if t["source"] == "native"]
    assert len(native) == 1
    assert native[0]["columns"] == ["Deployment", "Status", "Duration"]


def test_tailwind_page_prefers_tables_over_lists():
    """Div grids should land in tables, not lists."""
    result = parse_page(TAILWIND_GRID_HTML)
    assert len(result["tables"]) >= 1
    assert any(t.get("source") == "tailwind" for t in result["tables"])


def test_mixed_sources_in_one_page():
    html = """<html><body>
<div role="table"><div role="row"><div role="columnheader">A</div><div role="columnheader">B</div></div>
<div role="row"><div role="cell">1</div><div role="cell">2</div></div></div>
<div class="min-w-full divide-y">
  <div class="grid grid-cols-2"><div>X</div><div>Y</div></div>
  <div class="grid grid-cols-2"><div>1</div><div>2</div></div>
</div>
</body></html>"""
    tables = parse_tables(html)
    sources = {t["source"] for t in tables}
    assert "aria" in sources
    assert "tailwind" in sources
