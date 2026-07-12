"""Integration tests — full pipeline with real browser and server."""

import pytest

# ── Inline HTML extraction tests (no browser) ─────────────────────


def test_extract_from_html_tables():
    from schemasnap.extractor import extract_from_html

    html = """\
<html><body>
<table><thead><tr><th>Name</th><th>Score</th></tr></thead>
<tbody><tr><td>Team A</td><td>42</td></tr></tbody>
</table>
</body></html>
"""
    result = extract_from_html(html, url="https://example.com")
    assert result.error is None
    assert len(result.tables) == 1
    assert result.tables[0]["columns"] == ["Name", "Score"]
    assert result.compression_ratio > 0
    assert result.action_count >= 0
    assert result.elapsed_ms > 0


def test_extract_from_html_forms():
    from schemasnap.extractor import extract_from_html

    html = """\
<html><body>
<form action="/search" method="get">
  <input type="text" name="q" placeholder="Search..." required>
  <button type="submit">Go</button>
</form>
</body></html>
"""
    result = extract_from_html(html)
    assert result.error is None
    assert len(result.forms) == 1
    assert result.forms[0]["method"] == "GET"
    assert any(f["label"] for f in result.forms[0]["fields"])


def test_extract_from_html_token_budget():
    from schemasnap.extractor import extract_from_html

    html = "<html><head><script>console.log('x');</script><style>body{color:red}</style></head><body>" + ("<p>padding</p>" * 100) + "</body></html>"
    result = extract_from_html(html)
    assert result.raw_html_bytes > 0
    assert result.compressed_html_bytes > 0
    assert result.compressed_html_bytes <= result.raw_html_bytes  # compressor removes noise
    assert result.compression_ratio >= 0.0


def test_extract_from_html_error():
    from schemasnap.extractor import extract_from_html

    result = extract_from_html("not valid <html>")
    # lxml usually handles broken HTML gracefully — should not error
    assert result.error is None


# ── Live URL tests (requires Playwright + internet) ───────────────


@pytest.mark.integration
def test_extract_from_url_wikipedia():
    """Extract table from a Wikipedia page."""
    from schemasnap.extractor import extract_from_url

    result = extract_from_url(
        "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)",
        timeout_ms=45000,
    )
    assert result.error is None
    assert result.title
    assert len(result.tables) >= 1
    # First table should have data
    assert result.tables[0]["total_rows"] > 0
    assert len(result.tables[0]["columns"]) > 0


@pytest.mark.integration
def test_extract_from_url_form():
    """Extract form from a page with a login form."""
    from schemasnap.extractor import extract_from_url

    result = extract_from_url(
        "https://httpbin.org/forms/post",
        timeout_ms=30000,
    )
    assert result.error is None
    assert len(result.forms) >= 1


@pytest.mark.integration
def test_extract_from_url_result_structure():
    """Verify full result dict structure."""
    from schemasnap.extractor import extract_from_url

    result = extract_from_url("https://example.com", timeout_ms=30000)
    assert result.error is None
    data = result.to_dict()
    assert "url" in data
    assert "tables" in data
    assert "forms" in data
    assert "lists" in data
    assert "token_budget" in data
    assert "action_count" in data
    assert "elapsed_ms" in data
    assert data["token_budget"]["compression_ratio"] > 0
