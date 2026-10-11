"""Regression tests for native <table> extraction correctness.

Every case here was a real defect: merged header cells shifted columns,
nested tables merged into their ancestors, a second table with the same
schema was dropped, and empty tables surfaced as phantom datasets.
"""

from schemasnap.schema_snap import parse_tables, export_table_csv, export_table_json

GROUPED_HEADER = """\
<table>
  <thead>
    <tr><th rowspan="2">Name</th><th colspan="2">Sales</th></tr>
    <tr><th>Q1</th><th>Q2</th></tr>
  </thead>
  <tbody>
    <tr><td>Alice</td><td>10</td><td>20</td></tr>
    <tr><td>Bob</td><td>5</td><td>7</td></tr>
  </tbody>
</table>
"""

NESTED = """\
<table>
  <tr><td>Outer</td><td><table><tr><td>City</td><td>Berlin</td></tr></table></td></tr>
</table>
"""

SECTION_ROWS = """\
<table>
  <thead><tr><th>Item</th><th>Qty</th></tr></thead>
  <tbody>
    <tr><th colspan="2">Q1 2026</th></tr>
    <tr><td>Widget</td><td>10</td></tr>
    <tr><th colspan="2">Q2 2026</th></tr>
    <tr><td>Gadget</td><td>5</td></tr>
  </tbody>
</table>
"""


# -- colspan / rowspan ---------------------------------------------------------


def test_grouped_header_is_stacked_not_shifted():
    table = parse_tables(GROUPED_HEADER)[0]
    assert table["columns"] == ["Name", "Sales / Q1", "Sales / Q2"]
    assert table["rows"] == [["Alice", "10", "20"], ["Bob", "5", "7"]]
    assert table["column_count"] == 3


def test_grouped_header_types_follow_real_columns():
    table = parse_tables(GROUPED_HEADER)[0]
    assert table["types"] == ["string", "integer", "integer"]


def test_data_colspan_does_not_shift_following_cells():
    html = """<table>
      <thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>
      <tbody>
        <tr><td colspan="2">Merged</td><td>3</td></tr>
        <tr><td>x</td><td>y</td><td>z</td></tr>
      </tbody>
    </table>"""
    table = parse_tables(html)[0]
    assert table["rows"][0] == ["Merged", "", "3"]
    assert table["rows"][1] == ["x", "y", "z"]


def test_data_rowspan_carries_value_downward():
    html = """<table>
      <thead><tr><th>Region</th><th>City</th><th>N</th></tr></thead>
      <tbody>
        <tr><td rowspan="2">EU</td><td>Riga</td><td>1</td></tr>
        <tr><td>Berlin</td><td>2</td></tr>
      </tbody>
    </table>"""
    table = parse_tables(html)[0]
    assert table["rows"] == [["EU", "Riga", "1"], ["EU", "Berlin", "2"]]


# -- nested tables -------------------------------------------------------------


def test_nested_table_rows_are_isolated():
    tables = parse_tables(NESTED)
    assert len(tables) == 2
    outer, inner = tables
    assert outer["rows"] == [["Outer", "City Berlin"]]
    assert inner["rows"] == [["City", "Berlin"]]


# -- table-level data loss -----------------------------------------------------


def test_two_tables_with_same_schema_are_both_returned():
    html = """<table><thead><tr><th>A</th><th>B</th></tr></thead>
      <tbody><tr><td>1</td><td>2</td></tr></tbody></table>
      <table><thead><tr><th>A</th><th>B</th></tr></thead>
      <tbody><tr><td>3</td><td>4</td></tr></tbody></table>"""
    tables = parse_tables(html)
    assert len(tables) == 2
    assert tables[0]["rows"] == [["1", "2"]]
    assert tables[1]["rows"] == [["3", "4"]]


def test_empty_table_is_not_a_dataset():
    assert parse_tables("<table></table>") == []
    assert parse_tables("<table><tbody></tbody></table>") == []


def test_header_only_table_is_not_a_dataset():
    assert parse_tables("<table><thead><tr><th>A</th><th>B</th></tr></thead></table>") == []


def test_single_column_table_is_kept():
    table = parse_tables("<table><tr><th>Only</th></tr><tr><td>x</td></tr></table>")[0]
    assert table["columns"] == ["Only"]
    assert table["rows"] == [["x"]]


def test_leading_th_row_is_treated_as_header():
    html = "<table><tr><th>Name</th><th>Age</th></tr><tr><td>Alice</td><td>30</td></tr></table>"
    table = parse_tables(html)[0]
    assert table["columns"] == ["Name", "Age"]
    assert table["rows"] == [["Alice", "30"]]
    assert table["total_rows"] == 1


def test_multi_row_header_without_thead_is_not_data():
    html = """<table>
      <tr><th>Name</th><th colspan="2">Latest release</th></tr>
      <tr><th></th><th>Version</th><th>Date</th></tr>
      <tr><td>Vim</td><td>9.1</td><td>2024-01-01</td></tr>
    </table>"""
    table = parse_tables(html)[0]
    assert table["columns"] == ["Name", "Latest release / Version", "Latest release / Date"]
    assert table["rows"] == [["Vim", "9.1", "2024-01-01"]]
    assert table["total_rows"] == 1


def test_vertical_field_value_table_keeps_every_row():
    html = """<table>
      <tr><th>Capital</th><td>Riga</td></tr>
      <tr><th>Population</th><td>1.9M</td></tr>
      <tr><th>Area</th><td>64,589 km2</td></tr>
    </table>"""
    table = parse_tables(html)[0]
    assert table["columns"] == ["Field", "Value"]
    assert table["total_rows"] == 3
    assert table["rows"][0] == ["Capital", "Riga"]


# -- section rows --------------------------------------------------------------


def test_full_width_single_cell_rows_are_marked_sections():
    table = parse_tables(SECTION_ROWS)[0]
    assert table["row_kinds"] == ["section", "data", "section", "data"]
    assert table["rows"][0] == ["Q1 2026", ""]
    assert table["rows"][1] == ["Widget", "10"]


def test_row_kinds_default_to_data():
    table = parse_tables("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")[0]
    assert table["row_kinds"] == ["data"]


# -- cell text quality ---------------------------------------------------------


def test_hidden_subtree_text_is_dropped():
    html = """<table><thead><tr>
      <th>Id<div style="display:none">Ascending</div></th><th>Name</th>
      </tr></thead><tbody><tr><td>1</td><td>x</td></tr></tbody></table>"""
    table = parse_tables(html)[0]
    assert table["columns"][0] == "Id"


def test_block_cell_children_are_joined_with_a_space():
    html = """<table><thead><tr><th>City</th><th>N</th></tr></thead>
      <tbody><tr><td><div>City</div><div>Berlin</div></td><td>1</td></tr></tbody></table>"""
    table = parse_tables(html)[0]
    assert table["rows"][0][0] == "City Berlin"


# -- interaction with truncation and exports -----------------------------------


def test_max_rows_still_truncates_the_normalized_grid():
    table = parse_tables(GROUPED_HEADER, max_rows=1)[0]
    assert table["rows_returned"] == 1
    assert table["rows_truncated"] is True
    assert table["rows"] == [["Alice", "10", "20"]]
    assert table["total_rows"] == 2


def test_csv_export_uses_stacked_headers():
    csv_text = export_table_csv(GROUPED_HEADER)
    lines = csv_text.split("\n")
    assert lines[0] == "Name,Sales / Q1,Sales / Q2"
    assert lines[1] == "Alice,10,20"
    assert len(lines) == 3


def test_json_export_uses_stacked_headers():
    records = export_table_json(GROUPED_HEADER)
    assert records[0]["Sales / Q1"] == 10
    assert records[1]["Name"] == "Bob"


# -- degenerate input ----------------------------------------------------------


def test_comment_only_input_does_not_raise():
    assert parse_tables("<!-- c -->") == []


def test_none_input_does_not_raise():
    assert parse_tables(None) == []


# -- identifier-like values ----------------------------------------------------


def test_zero_padded_ids_stay_strings():
    html = "<table><tr><th>Id</th><th>Name</th></tr><tr><td>0406</td><td>A</td></tr><tr><td>0295</td><td>B</td></tr></table>"
    table = parse_tables(html)[0]
    assert table["types"][0] == "string"
    assert [row[0] for row in table["rows"]] == ["0406", "0295"]
    assert export_table_json(html)[0]["Id"] == "0406"


def test_decimal_below_one_is_still_numeric():
    html = "<table><tr><th>Rate</th><th>N</th></tr><tr><td>0.25</td><td>1</td></tr><tr><td>0.5</td><td>2</td></tr></table>"
    assert parse_tables(html)[0]["types"][0] == "number"


# -- ARIA grids ----------------------------------------------------------------


def test_single_column_aria_grid_is_parsed():
    html = """<div role="table">
      <div role="row"><div role="columnheader">Price</div></div>
      <div role="row"><div role="cell">$10<span aria-hidden="true">per unit</span></div></div>
    </div>"""
    table = parse_tables(html)[0]
    assert table["columns"] == ["Price"]
    assert table["rows"] == [["$10"]]


def test_aria_grid_without_header_does_not_eat_the_first_row():
    html = """<div role="table">
      <div role="row"><div role="cell">a1</div><div role="cell">a2</div></div>
      <div role="row"><div role="cell">b1</div><div role="cell">b2</div></div>
    </div>"""
    table = parse_tables(html)[0]
    assert table["columns"] == ["col_1", "col_2"]
    assert table["rows"] == [["a1", "a2"], ["b1", "b2"]]
    assert table["total_rows"] == 2


def test_nested_aria_grid_stays_inside_the_outer_cell():
    html = """<div role="grid">
      <div role="row"><div role="columnheader">Outer</div></div>
      <div role="row"><div role="cell">outer-1</div></div>
      <div role="row"><div role="cell">
        <div role="grid"><div role="row"><div role="gridcell">inner-1</div></div></div>
      </div></div>
    </div>"""
    tables = parse_tables(html)
    assert len(tables) == 1
    assert [row[0] for row in tables[0]["rows"]] == ["outer-1", "inner-1"]
