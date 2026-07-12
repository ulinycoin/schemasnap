"""Unit tests for SchemaSnap extraction engine (tables, forms, lists)."""

from schemasnap.schema_snap import (
    parse_tables,
    parse_forms,
    parse_lists,
    parse_page,
    export_table_json,
    export_table_csv,
    _infer_column_type,
)

# ── Fixtures ──────────────────────────────────────────────────────

TABLE_HTML = """\
<html><body>
<table>
  <thead><tr><th>Product</th><th>Price</th><th>Stock</th></tr></thead>
  <tbody>
    <tr><td>Widget A</td><td>$19.99</td><td>150</td></tr>
    <tr><td>Widget B</td><td>$24.50</td><td>75</td></tr>
    <tr><td>Widget C</td><td>$9.99</td><td>0</td></tr>
  </tbody>
</table>
</body></html>
"""

FORM_HTML = """\
<html><body>
<form action="/checkout" method="post">
  <label for="email">Email Address</label>
  <input type="email" id="email" name="email" required placeholder="you@example.com">
  <label for="country">Country</label>
  <select id="country" name="country">
    <option value="US">United States</option>
    <option value="UK">United Kingdom</option>
  </select>
  <textarea name="notes" placeholder="Order notes"></textarea>
  <button type="submit">Place Order</button>
</form>
</body></html>
"""

LIST_HTML = """\
<html><body>
<ul>
  <li>Apples</li>
  <li>Bananas</li>
  <li>Cherries</li>
</ul>
<ol>
  <li>First step</li>
  <li>Second step</li>
</ol>
</body></html>
"""

MIXED_HTML = TABLE_HTML.replace("</body>", "") + FORM_HTML.replace("<html><body>", "") + LIST_HTML.replace("<html><body>", "")


# ── Table tests ───────────────────────────────────────────────────


def test_parse_tables_extracts_columns():
    tables = parse_tables(TABLE_HTML)
    assert len(tables) == 1
    assert tables[0]["columns"] == ["Product", "Price", "Stock"]


def test_parse_tables_extracts_rows():
    tables = parse_tables(TABLE_HTML)
    assert tables[0]["total_rows"] == 3
    assert tables[0]["rows"][0] == ["Widget A", "$19.99", "150"]


def test_parse_tables_infers_types():
    tables = parse_tables(TABLE_HTML)
    types = tables[0]["types"]
    assert types[0] == "string"   # Product
    assert types[1] == "currency"  # Price
    assert types[2] == "integer"   # Stock


def test_parse_tables_max_rows():
    tables = parse_tables(TABLE_HTML, max_rows=2)
    assert tables[0]["rows_returned"] == 2
    assert tables[0]["rows_truncated"] is True
    assert len(tables[0]["rows"]) == 2


def test_parse_tables_no_limit():
    tables = parse_tables(TABLE_HTML, max_rows=None)
    assert "rows_truncated" not in tables[0]
    assert len(tables[0]["rows"]) == 3


def test_parse_tables_empty():
    assert parse_tables("") == []
    assert parse_tables("<div>no table</div>") == []


# ── Type inference ────────────────────────────────────────────────


def test_infer_currency():
    assert _infer_column_type(["$10.00", "$20.50", "$5.99"]) == "currency"


def test_infer_integer():
    assert _infer_column_type(["1", "2", "3", "100", "0"]) == "integer"


def test_infer_number():
    assert _infer_column_type(["1.5", "2.7", "3.14"]) == "number"


def test_infer_date():
    assert _infer_column_type(["2024-01-15", "2024-02-20", "2024-03-10"]) == "date"


def test_infer_email():
    assert _infer_column_type(["a@b.com", "c@d.org", "e@f.net"]) == "email"


def test_infer_string():
    assert _infer_column_type(["hello", "world", "test"]) == "string"


# ── Form tests ────────────────────────────────────────────────────


def test_parse_forms_extracts_fields():
    forms = parse_forms(FORM_HTML)
    assert len(forms) == 1
    form = forms[0]
    assert form["action"] == "/checkout"
    assert form["method"] == "POST"
    assert form["field_count"] >= 3  # email, select, textarea, button


def test_parse_forms_field_types():
    forms = parse_forms(FORM_HTML)
    fields = forms[0]["fields"]
    types = {f["tag"]: f["type"] for f in fields}
    assert types.get("input") == "email"
    assert types.get("select") == "select"
    assert types.get("textarea") == "textarea"


def test_parse_forms_label_extraction():
    forms = parse_forms(FORM_HTML)
    fields = forms[0]["fields"]
    labels = {f.get("label", ""): f.get("type") for f in fields}
    assert "Email Address" in labels


def test_parse_forms_empty():
    assert parse_forms("") == []
    assert parse_forms("<div>no form</div>") == []


# ── List tests ────────────────────────────────────────────────────


def test_parse_lists_unordered():
    lists = parse_lists(LIST_HTML)
    ul = [l for l in lists if l["type"] == "unordered"][0]
    assert ul["total"] == 3
    assert "Apples" in ul["items"]


def test_parse_lists_ordered():
    lists = parse_lists(LIST_HTML)
    ol = [l for l in lists if l["type"] == "ordered"][0]
    assert ol["total"] == 2
    assert "First step" in ol["items"]


def test_parse_lists_empty():
    assert parse_lists("") == []
    assert parse_lists("<div>no lists</div>") == []


# ── parse_page (combined) ─────────────────────────────────────────


def test_parse_page_combined():
    result = parse_page(MIXED_HTML)
    assert len(result["tables"]) == 1
    assert len(result["forms"]) == 1
    assert len(result["lists"]) == 2


def test_parse_page_empty():
    result = parse_page("")
    assert result == {"tables": [], "forms": [], "lists": []}


# ── Export tests ──────────────────────────────────────────────────


def test_export_table_json():
    records = export_table_json(TABLE_HTML)
    assert len(records) == 3
    assert records[0]["Product"] == "Widget A"
    assert records[0]["Price"] == 19.99   # currency coerced to float (symbol stripped)
    assert records[0]["Stock"] == 150      # integer coerced to int


def test_export_table_json_with_max_rows():
    records = export_table_json(TABLE_HTML, max_rows=1)
    assert len(records) == 1


def test_export_table_csv():
    csv = export_table_csv(TABLE_HTML)
    lines = csv.strip().split("\n")
    assert lines[0] == "Product,Price,Stock"
    assert len(lines) == 4  # header + 3 rows


def test_export_table_json_no_tables():
    try:
        export_table_json("<div>empty</div>")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_export_table_csv_no_tables():
    try:
        export_table_csv("<div>empty</div>")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
