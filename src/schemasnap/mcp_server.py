"""
SchemaSnap MCP Server — stdio transport for Cursor, Claude Desktop, etc.

One tool: compress_html — typed tables, forms, lists, actions from raw HTML.

Usage:
  pip install "schemasnap[mcp]"
  schemasnap-mcp
"""

from __future__ import annotations

from typing import Any, Optional

from fastmcp import FastMCP

from schemasnap.extractor import extract_from_html

mcp = FastMCP(
    "schemasnap",
    instructions=(
        "Extract structured data from HTML: typed tables, form fields with "
        "validation attrs, lists, and clickable actions with semantic groups. "
        "Pass HTML from curl, Playwright, CDP, or files — no browser needed."
    ),
)


def run_compress_html(
    html: str,
    *,
    max_rows_per_table: Optional[int] = 50,
    url: str = "",
) -> dict[str, Any]:
    """Core logic shared by MCP tool and tests."""
    result = extract_from_html(
        html,
        url=url,
        max_rows_per_table=max_rows_per_table,
    )
    if result.error:
        return {"error": result.error}
    return result.to_dict()


@mcp.tool()
def compress_html(
    html: str,
    max_rows_per_table: Optional[int] = 50,
    url: str = "",
) -> dict[str, Any]:
    """Extract typed tables, forms, lists, and actions from raw HTML.

    Returns JSON with column type inference (string, integer, number, currency,
    percentage, date, email, url), form validation attrs (required, pattern,
    select options), and action map with semantic groups (Login Form, Navigation).

    Args:
        html: Raw HTML string from any source.
        max_rows_per_table: Cap rows per table (default 50, None for unlimited).
        url: Optional source URL for metadata only.
    """
    return run_compress_html(
        html,
        max_rows_per_table=max_rows_per_table,
        url=url,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
