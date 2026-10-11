"""End-to-end pipeline tests: compress -> extract_from_html / extract_from_url.

These go through the real entry points on purpose. Unit tests on parse_forms
passed while the shipped pipeline produced wrong labels, because the
compressor drops the id that label[for] resolves against.
"""

from schemasnap.extractor import extract_from_html


TWO_FIELD_FORM = """\
<form action="/checkout" method="post">
  <label for="email">Email Address</label>
  <input type="email" id="email" name="email" required>
  <label for="qty">Quantity</label>
  <input type="number" id="qty" name="qty">
</form>
"""


def test_labels_stay_associated_through_the_full_pipeline():
    result = extract_from_html(TWO_FIELD_FORM)
    assert result.error is None
    labels = [(f.get("name"), f.get("label")) for f in result.forms[0]["fields"]]
    assert labels == [("email", "Email Address"), ("qty", "Quantity")]


def test_wrapped_label_is_still_resolved():
    html = '<form><label>Full name<input name="full_name"></label></form>'
    result = extract_from_html(html)
    fields = result.forms[0]["fields"]
    assert fields[0]["label"] == "Full name"


def test_compressed_html_never_borrows_another_fields_label():
    """Without ids, a sibling label with `for` belongs to a different control."""
    from schemasnap.compressor import process_html
    from schemasnap.schema_snap import parse_forms

    clean_html, _ = process_html(TWO_FIELD_FORM)
    assert "id=" not in clean_html.replace("data-sid=", "")

    labels = [(f.get("name"), f.get("label")) for f in parse_forms(clean_html)[0]["fields"]]
    assert labels == [("email", "Email"), ("qty", "Qty")]


def test_grouped_table_headers_survive_the_pipeline():
    html = """<html><body><table>
      <thead><tr><th rowspan="2">Name</th><th colspan="2">Sales</th></tr>
      <tr><th>Q1</th><th>Q2</th></tr></thead>
      <tbody><tr><td>Alice</td><td>10</td><td>20</td></tr></tbody>
    </table></body></html>"""
    result = extract_from_html(html)
    table = result.tables[0]
    assert table["columns"] == ["Name", "Sales / Q1", "Sales / Q2"]
    assert table["rows"] == [["Alice", "10", "20"]]


def test_empty_table_does_not_reach_the_result():
    result = extract_from_html("<html><body><table></table></body></html>")
    assert result.tables == []


def test_compression_stats_are_still_reported():
    result = extract_from_html(TWO_FIELD_FORM)
    assert result.raw_html_bytes > 0
    assert result.compressed_html_bytes > 0
    assert result.action_count >= 2  # two inputs carry data-sid
