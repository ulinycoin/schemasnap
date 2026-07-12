"""Tests for SchemaSnap MCP server tool logic."""

from schemasnap.mcp_server import run_compress_html

TABLE_HTML = """\
<table>
  <thead><tr><th>Product</th><th>Price</th><th>Stock</th></tr></thead>
  <tbody><tr><td>Widget</td><td>$19.99</td><td>150</td></tr></tbody>
</table>
"""


def test_run_compress_html_extracts_typed_table():
    result = run_compress_html(TABLE_HTML)
    assert "error" not in result
    assert len(result["tables"]) == 1
    table = result["tables"][0]
    assert table["columns"] == ["Product", "Price", "Stock"]
    assert table["types"] == ["string", "currency", "integer"]
    assert table["rows"] == [["Widget", "$19.99", "150"]]


def test_run_compress_html_includes_actions_and_budget():
    html = '<form><input name="q" placeholder="Search"></form>'
    result = run_compress_html(html)
    assert result["action_count"] >= 1
    assert "token_budget" in result
    assert result["elapsed_ms"] > 0


def test_run_compress_html_empty_input():
    result = run_compress_html("")
    assert result["tables"] == []
    assert result["forms"] == []
