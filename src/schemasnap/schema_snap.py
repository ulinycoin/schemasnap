"""SchemaSnap — extract structured data schemas from HTML.

Turns HTML tables, forms, and lists into structured JSON-friendly dicts
(columns, types, fields, validation attrs). Pure lxml, no browser, no API keys.

Core functions:
  - parse_tables(html, max_rows=None) -> [{columns, rows, types, total_rows, ...}]
  - parse_forms(html)                 -> [{action, method, fields: [...]}]
  - parse_lists(html)               -> [{items, total, type}]
  - parse_page(html, max_rows=None)   -> {tables, forms, lists}
  - export_table_json(html, ...)      -> [{column: value, ...}, ...]
  - export_table_csv(html, ...)       -> "col1,col2\\nval1,val2\\n..."
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Optional, Union
from lxml import html as lxml_html, etree


# -- Safe parser (shared across all functions, guards against XXE/network) ------

_SAFE_PARSER = lxml_html.HTMLParser(no_network=True)


def _parse_html(html: str):
    """Parse HTML string into lxml tree. Returns None for unusable input.

    Empty, whitespace-only, comment-only and non-string input all return None
    instead of raising: callers treat "nothing to parse" as an empty result.
    """
    if not html or not isinstance(html, str) or not html.strip():
        return None
    try:
        return lxml_html.fromstring(html, parser=_SAFE_PARSER)
    except (etree.ParserError, ValueError):
        # A comment-only or otherwise rootless document.
        return None


# -- Text helpers ---------------------------------------------------------------


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# Inline markers of a hidden subtree. Admin UIs routinely park menus, tooltips
# and sort dropdowns inside a header/body cell with display:none, and
# text_content() would otherwise splice that hidden text into the value
# ("Id" + "Ascending" + "Descending" -> "IdAscendingDescending").
_HIDDEN_STYLE_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)


def _is_hidden(el) -> bool:
    if el.get("hidden") is not None:
        return True
    if (el.get("aria-hidden") or "").lower() == "true":
        return True
    return bool(_HIDDEN_STYLE_RE.search(el.get("style") or ""))


def _visible_text(el) -> str:
    """Text of an element with hidden subtrees dropped, parts joined by a space.

    text_content() glues sibling block elements together ("City" + "Berlin"
    -> "CityBerlin") and pulls in display:none menus. Both corrupt cell values,
    so the walk is explicit. Leaf nodes take a C-level fast path: most cells
    have no child elements, and the Python walk dominates parse time otherwise.
    """
    if el is None:
        return ""
    if len(el) == 0:
        return _clean(el.text or "")
    parts: List[str] = []

    def walk(node) -> None:
        if node.text:
            parts.append(node.text)
        for child in node.iterchildren():
            if isinstance(child.tag, str) and not _is_hidden(child):
                walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return _clean(" ".join(parts))


def _text_or_empty(el) -> str:
    if el is None:
        return ""
    return _visible_text(el)


def _li_item_text(li_el) -> str:
    """Text of a single <li>, excluding nested <ul>/<ol> content."""
    parts: List[str] = []
    if li_el.text:
        parts.append(li_el.text)
    for child in li_el.iterchildren():
        if child.tag in ("ul", "ol"):
            break
        parts.append(_text_or_empty(child))
        if child.tail:
            parts.append(child.tail)
    return _clean(" ".join(parts))


def _apply_max_rows(table: Dict[str, Any], max_rows: Optional[int]) -> Dict[str, Any]:
    if max_rows is None or table["total_rows"] <= max_rows:
        return table
    return {
        **table,
        "rows": table["rows"][:max_rows],
        "rows_returned": max_rows,
        "rows_truncated": True,
    }


# -- Table type inference -------------------------------------------------------


def _infer_column_type(values: List[str]) -> str:
    """Guess column data type from a sample of values."""
    non_empty = [v for v in values if v and v != "\u2014" and v != "-"]
    if not non_empty:
        return "string"

    # Sample first 20 non-empty values
    sample = non_empty[:20]
    total = len(sample)

    numeric = 0
    date_like = 0
    email_like = 0
    url_like = 0
    identifier_like = 0
    has_currency = False
    has_percent = False
    all_int = True

    for val in sample:
        val = val.strip()

        # Currency / percent flags
        if any(c in val for c in ("$", "\u20ac", "\u00a3")):
            has_currency = True
        if "%" in val:
            has_percent = True

        # A leading zero means an identifier, not a number: "0406" must stay a
        # string, otherwise coercion drops the zero and the id changes meaning.
        if re.fullmatch(r"0\d+", val):
            identifier_like += 1
            all_int = False
            continue

        # Try numeric
        cleaned = val.replace(",", "").replace("$", "").replace("\u20ac", "").replace("\u00a3", "").replace("%", "").strip()
        try:
            float(cleaned)
            numeric += 1
            if "." in cleaned:
                all_int = False
        except ValueError:
            all_int = False
            # Date (ISO, US, EU)
            if re.match(r"\d{4}-\d{2}-\d{2}", val) or re.match(r"\d{2}[/-]\d{2}[/-]\d{4}", val):
                date_like += 1
                continue
            # Email
            if "@" in val and "." in val.split("@")[-1]:
                email_like += 1
                continue
            # URL
            if val.startswith("http://") or val.startswith("https://"):
                url_like += 1
                continue

    if numeric / total >= 0.6:
        if has_currency:
            return "currency"
        if has_percent:
            return "percentage"
        if all_int:
            return "integer"
        return "number"
    if identifier_like / total >= 0.6:
        return "string"
    if date_like / total >= 0.6:
        return "date"
    if email_like / total >= 0.6:
        return "email"
    if url_like / total >= 0.6:
        return "url"
    return "string"


# -- Table extraction -----------------------------------------------------------

_TABLE_ROLES = frozenset({"table", "grid"})
_ROW_ROLE = "row"
_CELL_ROLES = frozenset({"cell", "columnheader", "rowheader", "gridcell"})
_TABLE_CLASS_RE = re.compile(
    r"(?:^|\s)(?:table|min-w-full|divide-[xy]|caption-bottom)(?:\s|$)",
    re.I,
)
_GRID_COLS_RE = re.compile(r"grid-cols-\d+", re.I)
_ROW_CLASS_RE = re.compile(r"(?:^|\s)(?:row|table-row|Box-row)(?:\s|$)", re.I)


def _element_class(el) -> str:
    return el.get("class") or ""


def _has_table_class_hint(el) -> bool:
    return bool(_TABLE_CLASS_RE.search(_element_class(el)))


def _has_grid_cols(el) -> bool:
    return bool(_GRID_COLS_RE.search(_element_class(el)))


def _role(el) -> str:
    return (el.get("role") or "").lower()


def _direct_element_children(el) -> List[Any]:
    return [c for c in el if isinstance(c.tag, str)]


def _finalize_table(
    columns: List[str],
    rows: List[List[str]],
    *,
    source: str = "native",
    min_cols: int = 2,
    row_kinds: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Normalize dimensions, infer types, attach source metadata.

    Returns None when there are no data rows: an empty or header-only <table>
    is page furniture, not a dataset, and used to surface as a phantom table
    with zero columns.
    """
    if not rows:
        return None

    max_row_len = max((len(row) for row in rows), default=0)
    max_cols = max(max_row_len, len(columns))
    if max_cols < min_cols:
        return None

    columns = list(columns)
    if columns:
        while len(columns) < max_cols:
            columns.append(f"column_{len(columns) + 1}")
    else:
        columns = [f"col_{i + 1}" for i in range(max_cols)]

    # Rectangular data: short rows get empty cells instead of shifting columns.
    widths = {len(row) for row in rows}
    if widths != {max_cols}:
        rows = [list(row) + [""] * (max_cols - len(row)) for row in rows]

    types: List[str] = []
    for col_idx in range(len(columns)):
        col_values = [row[col_idx] if col_idx < len(row) else "" for row in rows]
        types.append(_infer_column_type(col_values))

    return {
        "columns": columns,
        "types": types,
        "rows": rows,
        "total_rows": len(rows),
        "column_count": len(columns),
        "row_kinds": list(row_kinds) if row_kinds else ["data"] * len(rows),
        "source": source,
    }


def _row_cells_from_element(row_el) -> List[str]:
    """Extract cell text from a native <tr> or ARIA role=row element."""
    if row_el.tag == "tr":
        return [_text_or_empty(cell) for cell in row_el.xpath("./td | ./th")]

    cells = row_el.xpath(
        './*[@role="cell" or @role="columnheader" or @role="rowheader" or @role="gridcell"]'
    )
    if cells:
        return [_text_or_empty(cell) for cell in cells]
    return [_text_or_empty(cell) for cell in _direct_element_children(row_el)]


def _rows_in_role_table(table_el) -> List[Any]:
    """Collect role=row elements scoped to one table/grid root.

    A row belongs to its *nearest* table/grid ancestor. Unlike a real <table>,
    a div grid gives no reliable cell boundary, so a grid rendered inside a
    cell is sub-layout of that cell: its text stays in the outer row and the
    nested root is not reported as a second table (the root collector skips
    roots nested inside a claimed one).
    """
    scoped: List[Any] = []
    for row in table_el.xpath('.//*[@role="row"]'):
        nearest = next(
            (anc for anc in row.iterancestors() if _role(anc) in _TABLE_ROLES),
            None,
        )
        if nearest is table_el:
            scoped.append(row)
    return scoped


def _extract_role_table(table_el) -> Optional[Dict[str, Any]]:
    """Parse ARIA table/grid (role=table|grid + row + cell)."""
    row_els = _rows_in_role_table(table_el)
    if not row_els:
        return None

    columns: List[str] = []
    rows: List[List[str]] = []

    for idx, row_el in enumerate(row_els):
        cell_els = row_el.xpath(
            './*[@role="cell" or @role="columnheader" or @role="rowheader" or @role="gridcell"]'
        )
        if not cell_els:
            cell_els = _direct_element_children(row_el)
        cell_texts = [_text_or_empty(c) for c in cell_els]
        if not any(cell_texts):
            continue

        is_header_row = (
            idx == 0
            and (
                any(_role(c) == "columnheader" for c in cell_els)
                or row_el.get("aria-rowindex") == "1"
            )
        )
        if is_header_row and not columns:
            columns = cell_texts
            continue
        rows.append(cell_texts)

    if not rows:
        return None
    if not columns:
        # No columnheader row was found: every row carries data, so name the
        # columns generically instead of consuming the first row as a header.
        width = max(len(row) for row in rows)
        columns = [f"col_{i + 1}" for i in range(width)]
    # min_cols=1: role=table/grid is explicit semantics, and a one-column grid
    # is a legitimate dataset.
    return _finalize_table(columns, rows, source="aria", min_cols=1)


def _tailwind_row_children(container_el) -> List[Any]:
    """Direct children that look like grid/table rows."""
    children = _direct_element_children(container_el)
    grid_rows = [c for c in children if _has_grid_cols(c)]
    if len(grid_rows) >= 2:
        return grid_rows
    if _has_table_class_hint(container_el) and len(children) >= 2:
        return children
    return []


def _extract_tailwind_grid_table(container_el) -> Optional[Dict[str, Any]]:
    """Parse div-based Tailwind/shadcn grids (grid-cols-N + divide-y)."""
    row_els = _tailwind_row_children(container_el)
    if len(row_els) < 2:
        return None

    row_data: List[List[str]] = []
    col_counts: List[int] = []
    for row_el in row_els:
        cells = _direct_element_children(row_el)
        if not cells:
            continue
        texts = [_text_or_empty(c) for c in cells]
        if any(texts):
            row_data.append(texts)
            col_counts.append(len(texts))

    if len(row_data) < 2 or len(set(col_counts)) != 1 or col_counts[0] < 2:
        return None

    columns = row_data[0]
    data_rows = row_data[1:]
    return _finalize_table(columns, data_rows, source="tailwind")


def _extract_pseudo_table(container_el) -> Optional[Dict[str, Any]]:
    """Fallback: repeated .row / .Box-row siblings with uniform cell count."""
    row_els = [
        c
        for c in _direct_element_children(container_el)
        if _ROW_CLASS_RE.search(_element_class(c))
    ]
    if len(row_els) < 2:
        return None

    row_data: List[List[str]] = []
    col_counts: List[int] = []
    for row_el in row_els:
        cells = _direct_element_children(row_el)
        if not cells:
            texts = [_text_or_empty(row_el)]
        else:
            texts = [_text_or_empty(c) for c in cells]
        if any(texts):
            row_data.append(texts)
            col_counts.append(len(texts))

    if len(row_data) < 2 or len(set(col_counts)) != 1 or col_counts[0] < 2:
        return None

    columns = [f"col_{i + 1}" for i in range(col_counts[0])]
    return _finalize_table(columns, row_data, source="pseudo")


def _is_inside_native_table(el) -> bool:
    return bool(el.xpath("ancestor::table"))


def _is_inside_claimed_table(el, claimed: set[int]) -> bool:
    for anc in el.iterancestors():
        if id(anc) in claimed:
            return True
    return False


def _collect_table_roots(tree) -> List[tuple[Any, str]]:
    """Find native, ARIA, Tailwind, and pseudo-table roots (deduped)."""
    roots: List[tuple[Any, str]] = []
    claimed: set[int] = set()

    for table_el in tree.xpath("//table"):
        roots.append((table_el, "native"))
        claimed.add(id(table_el))

    for el in tree.xpath('//*[@role="table" or @role="grid"]'):
        if id(el) in claimed or _is_inside_native_table(el):
            continue
        if _is_inside_claimed_table(el, claimed):
            continue
        roots.append((el, "aria"))
        claimed.add(id(el))

    for el in tree.iter():
        if not isinstance(el.tag, str) or el.tag not in ("div", "section"):
            continue
        if id(el) in claimed or _is_inside_native_table(el) or _is_inside_claimed_table(el, claimed):
            continue
        if len(_tailwind_row_children(el)) >= 2:
            roots.append((el, "tailwind"))
            claimed.add(id(el))

    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        if id(el) in claimed or _is_inside_native_table(el) or _is_inside_claimed_table(el, claimed):
            continue
        row_children = [
            c for c in _direct_element_children(el) if _ROW_CLASS_RE.search(_element_class(c))
        ]
        if len(row_children) >= 2:
            roots.append((el, "pseudo"))
            claimed.add(id(el))

    return roots


def _extract_table_from_root(root_el, kind: str) -> Optional[Dict[str, Any]]:
    if kind == "native":
        return _extract_table(root_el)
    if kind == "aria":
        return _extract_role_table(root_el)
    if kind == "tailwind":
        return _extract_tailwind_grid_table(root_el)
    if kind == "pseudo":
        return _extract_pseudo_table(root_el)
    return None


def _parse_tables_from_tree(tree, max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []

    # No content-based de-duplication here. Roots are already unique (each is
    # claimed once by _collect_table_roots), while a signature over
    # (source, columns, total_rows) silently dropped a second, genuinely
    # different table that happened to share a header and a row count.
    for root_el, kind in _collect_table_roots(tree):
        parsed = _extract_table_from_root(root_el, kind)
        if not parsed:
            continue
        tables.append(_apply_max_rows(parsed, max_rows))

    return tables


def _span_int(el, attr: str) -> int:
    """colspan/rowspan as a positive int (1 when absent or malformed)."""
    raw = (el.get(attr) or "").strip()
    if not raw.isdigit():
        return 1
    return max(1, int(raw))


def _own_table_rows(table_el) -> List[Any]:
    """<tr> elements belonging to this table, nested tables excluded.

    ``.//tr`` crosses nested <table> boundaries: the inner table's rows then
    become rows of every ancestor, which both duplicates data and shifts the
    outer table's columns. Ownership is decided by the *nearest* table
    ancestor, so ``iterancestors()`` is used instead of the ``ancestor::``
    XPath axis (lxml returns that axis in document order, outermost first).
    """
    rows: List[Any] = []
    for tr in table_el.iterfind(".//tr"):
        owner = next((a for a in tr.iterancestors() if a.tag == "table"), None)
        if owner is not table_el:
            continue
        rows.append(tr)
    return rows


def _grid_from_rows(row_els: List[Any], *, repeat_spans: bool = False) -> List[List[str]]:
    """Expand colspan/rowspan into a rectangular text grid.

    Data cells keep the value in the first spanned slot and leave the others
    empty, so column indexes never shift. Header cells repeat the label across
    a colspan (a "Sales" banner over Q1 and Q2 names both columns).
    rowspan values are carried into the following rows either way.
    """
    grid: List[List[str]] = []
    carry: Dict[int, tuple] = {}  # column index -> (text, rows left)

    for tr in row_els:
        cell_els = tr.xpath("./td | ./th")
        texts = [_text_or_empty(cell) for cell in cell_els]
        spans = [
            (_span_int(cell, "colspan"), _span_int(cell, "rowspan"))
            for cell in cell_els
        ]

        row: List[str] = []
        col = 0
        cell_idx = 0
        while cell_idx < len(texts) or (carry and col <= max(carry)):
            if col in carry:
                text, rows_left = carry[col]
                row.append(text)
                if rows_left <= 1:
                    del carry[col]
                else:
                    carry[col] = (text, rows_left - 1)
                col += 1
                continue
            if cell_idx >= len(texts):
                row.append("")
                col += 1
                continue

            text = texts[cell_idx]
            colspan, rowspan = spans[cell_idx]
            cell_idx += 1
            for offset in range(colspan):
                slot_text = text if (offset == 0 or repeat_spans) else ""
                row.append(slot_text)
                if rowspan > 1:
                    carry[col + offset] = (slot_text, rowspan - 1)
            col += colspan

        grid.append(row)

    return grid


def _pad_grid(grid: List[List[str]]) -> List[List[str]]:
    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid]


def _header_names(header_grid: List[List[str]], width: int) -> List[str]:
    """Stack a multi-row header into one name per column ("Sales / Q1").

    A label repeated in consecutive header rows (rowspan) is written once.
    """
    names: List[str] = []
    for col_idx in range(width):
        parts: List[str] = []
        for row in header_grid:
            value = (row[col_idx] if col_idx < len(row) else "").strip()
            if value and (not parts or parts[-1] != value):
                parts.append(value)
        names.append(" / ".join(parts))
    return names


def _looks_vertical(row_els: List[Any]) -> bool:
    """True for "field -> value" tables (infoboxes, spec sheets).

    Their first cell of every row is a <th> label with <td> values next to it.
    Treating the first row as a horizontal header silently deletes that row and
    names the columns after one arbitrary pair.
    """
    pairs = 0
    for tr in row_els:
        cells = tr.xpath("./td | ./th")
        if len(cells) >= 2 and cells[0].tag == "th" and any(c.tag == "td" for c in cells[1:]):
            pairs += 1
    return pairs >= max(2, int(len(row_els) * 0.6))


def _extract_table(table_el) -> Optional[Dict[str, Any]]:
    """Parse a single <table> element into column schema + rows."""
    row_els = _own_table_rows(table_el)
    if not row_els:
        return None

    # -- Header rows. <thead> wins; without it, the leading run of rows built
    #    only from <th> is the header (multi-row headers are kept as a grid so
    #    colspan/rowspan survive). A "field -> value" table has no header row.
    header_els: List[Any] = []
    thead = table_el.find(".//thead")
    if thead is not None:
        header_els = [tr for tr in row_els if tr.xpath("ancestor::thead")]
    else:
        for tr in row_els:
            cells = tr.xpath("./td | ./th")
            if not cells or not all(cell.tag == "th" for cell in cells):
                break
            header_els.append(tr)

    vertical = not header_els and _looks_vertical(row_els)

    header_ids = {id(tr) for tr in header_els}
    data_els = [tr for tr in row_els if id(tr) not in header_ids]

    header_grid = _pad_grid(_grid_from_rows(header_els, repeat_spans=True)) if header_els else []
    data_grid = _grid_from_rows(data_els)

    width = max(
        [len(row) for row in header_grid] + [len(row) for row in data_grid] + [0]
    )
    if width == 0:
        return None

    if header_grid:
        columns = [
            name or f"col_{idx + 1}"
            for idx, name in enumerate(_header_names(header_grid, width))
        ]
    elif vertical and width == 2:
        columns = ["Field", "Value"]
    else:
        columns = [f"col_{idx + 1}" for idx in range(width)]

    # -- Data rows: drop blank rows, mark full-width single-cell section rows
    #    (a band like "Q1 2026" inside <tbody> that groups the rows below).
    rows: List[List[str]] = []
    row_kinds: List[str] = []
    for raw_row in data_grid:
        row = list(raw_row) + [""] * (width - len(raw_row))
        filled = [cell for cell in row if cell.strip()]
        if not filled:
            continue
        rows.append(row)
        row_kinds.append("section" if len(filled) == 1 and width > 1 else "data")

    return _finalize_table(
        columns, rows, source="native", min_cols=1, row_kinds=row_kinds
    )


def parse_tables(html: str, max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
    """Extract all tables from HTML as structured data.

    Args:
        html: Raw or compressed HTML.
        max_rows: Cap rows per table (None = no limit). When truncated,
            adds rows_truncated=True and rows_returned.

    Returns a list of table objects, each with:
      - columns, types, rows, total_rows, column_count
    """
    tree = _parse_html(html)
    if tree is None:
        return []
    return _parse_tables_from_tree(tree, max_rows)


# -- Form parsing ---------------------------------------------------------------


_INPUT_TYPES = {
    "text", "email", "password", "number", "tel", "url",
    "date", "datetime-local", "time", "month", "week",
    "checkbox", "radio", "file", "hidden", "search", "color",
    "range", "submit", "image",
}

_INPUT_ATTRS_TO_KEEP = {
    "name", "type", "placeholder", "required", "pattern",
    "minlength", "maxlength", "min", "max", "step",
    "autocomplete", "readonly", "disabled", "value",
}

_SELECT_ATTRS_TO_KEEP = {
    "name", "required", "multiple", "disabled",
}

_TEXTAREA_ATTRS_TO_KEEP = {
    "name", "placeholder", "required", "rows", "cols",
    "maxlength", "readonly", "disabled",
}


def _parse_field_attrs(el, keep: set) -> Dict[str, Any]:
    field = {}
    for attr in keep:
        val = el.get(attr)
        if val is not None:
            field[attr] = val
    return field


def _extract_label(form_el, field_el) -> str:
    """Try to find a label for a form field. Does NOT mutate the DOM."""
    field_id = field_el.get("id")
    if field_id:
        # Use parameterized XPath to avoid injection
        label_els = form_el.xpath(".//label[@for=$fid]", fid=field_id)
        if label_els:
            text = _text_or_empty(label_els[0])
            if text:
                return text

    # Check if field is wrapped in <label> -- collect text without the field itself
    parent = field_el.getparent()
    while parent is not None:
        if parent.tag == "label":
            parts: List[str] = []
            if parent.text:
                parts.append(parent.text)
            for child in parent.iterchildren():
                tail = (child.tail or "").strip()
                if child != field_el:
                    parts.append(_text_or_empty(child) + " " + tail)
                elif tail:
                    parts.append(tail)
            cleaned = _clean(" ".join(parts))
            if cleaned:
                return cleaned
        parent = parent.getparent()

    # Sibling <label> (e.g. checkbox then <label>Subscribe</label>).
    # A label that points at a *different* control through `for` must not be
    # borrowed. Without this check, a pipeline that hands us HTML with ids
    # stripped gives every field the first label on the page.
    parent = field_el.getparent()
    if parent is not None:
        for sibling in parent.iterchildren():
            if sibling.tag != "label" or sibling is field_el:
                continue
            target = (sibling.get("for") or "").strip()
            if target and target != field_id:
                continue
            text = _text_or_empty(sibling)
            if text:
                return text

    # Fallback: placeholder or name
    placeholder = _clean(field_el.get("placeholder"))
    if placeholder:
        return placeholder
    name = _clean(field_el.get("name"))
    if name:
        return name.replace("_", " ").replace("-", " ").capitalize()

    return ""


def _extract_form(form_el) -> Dict[str, Any]:
    """Parse a single <form> element into field schema."""
    form: Dict[str, Any] = {
        "action": _clean(form_el.get("action")) or None,
        "method": (form_el.get("method") or "get").upper(),
    }
    fields: List[Dict[str, Any]] = []

    # Parse <input> elements
    for input_el in form_el.iterfind(".//input"):
        field = _parse_field_attrs(input_el, _INPUT_ATTRS_TO_KEEP)
        field["tag"] = "input"
        field_type = input_el.get("type", "text")
        if field_type not in _INPUT_TYPES:
            field_type = "text"
        field["type"] = field_type
        field["label"] = _extract_label(form_el, input_el)
        if "required" in field:
            field["required"] = True
        if "disabled" in field:
            field["disabled"] = True
        if field_type == "submit":
            continue
        fields.append(field)

    # Parse <select> elements
    for select_el in form_el.iterfind(".//select"):
        field = _parse_field_attrs(select_el, _SELECT_ATTRS_TO_KEEP)
        field["tag"] = "select"
        field["type"] = "select"
        field["label"] = _extract_label(form_el, select_el)
        options = []
        for opt in select_el.iterfind(".//option"):
            opt_val = opt.get("value") or ""
            opt_label = _text_or_empty(opt) or opt_val
            options.append({"value": opt_val, "label": opt_label})
        if options:
            field["options"] = options
        if "required" in field:
            field["required"] = True
        if "disabled" in field:
            field["disabled"] = True
        fields.append(field)

    # Parse <textarea> elements
    for ta_el in form_el.iterfind(".//textarea"):
        field = _parse_field_attrs(ta_el, _TEXTAREA_ATTRS_TO_KEEP)
        field["tag"] = "textarea"
        field["type"] = "textarea"
        field["label"] = _extract_label(form_el, ta_el)
        if "required" in field:
            field["required"] = True
        if "disabled" in field:
            field["disabled"] = True
        fields.append(field)

    # Parse submit buttons
    for btn_el in form_el.iterfind(".//button"):
        btn_type = btn_el.get("type", "submit")
        if btn_type == "submit":
            fields.append({
                "tag": "button",
                "type": "submit",
                "label": _text_or_empty(btn_el),
            })

    # Also catch <input type="submit">
    for submit_el in form_el.iterfind('.//input[@type="submit"]'):
        fields.append({
            "tag": "input",
            "type": "submit",
            "label": submit_el.get("value", "Submit").strip(),
        })

    form["fields"] = fields
    form["field_count"] = len(fields)
    return form


def parse_forms(html: str) -> List[Dict[str, Any]]:
    """Extract all forms from HTML as structured field schemas.

    Returns a list of form objects, each with:
      - action: form action URL
      - method: GET/POST
      - fields: list of field objects (name, type, label, required, options, etc.)
      - field_count: number of fields
    """
    tree = _parse_html(html)
    if tree is None:
        return []
    return [_extract_form(f) for f in tree.xpath("//form")]


# -- List parsing ---------------------------------------------------------------


def _parse_lists_from_tree(tree) -> List[Dict[str, Any]]:
    """Extract lists from a pre-parsed lxml tree."""
    results: List[Dict[str, Any]] = []

    # Parse <ul> and <ol> (direct <li> children only)
    for tag, list_type in [("ul", "unordered"), ("ol", "ordered")]:
        for list_el in tree.xpath(f"//{tag}"):
            items = []
            for li in list_el.xpath("./li"):
                text = _li_item_text(li)
                if text:
                    items.append(text)
            if items:
                results.append({
                    "type": list_type,
                    "items": items,
                    "total": len(items),
                })

    # Standalone <select> lists (skip selects inside <form> — covered by parse_forms)
    for select_el in tree.xpath("//select[not(ancestor::form)]"):
        options = []
        for opt in select_el.iterfind(".//option"):
            val = opt.get("value") or ""
            label = _text_or_empty(opt) or val
            options.append({"value": val, "label": label})
        if len(options) > 2:
            results.append({
                "type": "select",
                "items": options,
                "total": len(options),
            })

    return results


def parse_lists(html: str) -> List[Dict[str, Any]]:
    """Extract lists (<ul>, <ol>, <select>) from HTML.

    Returns a list of list objects:
      - type: unordered | ordered | select
      - items: list of item texts (or {value, label} for select)
      - total: item count
    """
    tree = _parse_html(html)
    if tree is None:
        return []
    return _parse_lists_from_tree(tree)


# -- High-level -----------------------------------------------------------------


def parse_page(html: str, max_rows: Optional[int] = None) -> Dict[str, Any]:
    """Extract all structured data (tables, forms, lists) from HTML.

    Args:
        html: Raw or compressed HTML.
        max_rows: Cap rows per table (None = no limit).

    Returns a dict with keys: tables, forms, lists.
    Parses HTML only once internally.
    """
    tree = _parse_html(html)
    if tree is None:
        return {"tables": [], "forms": [], "lists": []}
    return {
        "tables": _parse_tables_from_tree(tree, max_rows),
        "forms": [_extract_form(f) for f in tree.xpath("//form")],
        "lists": _parse_lists_from_tree(tree),
    }


# -- Export (CSV / JSON records) ------------------------------------------------


def _coerce_cell(value: str, col_type: str) -> Union[str, int, float, None]:
    if not value or value in ("\u2014", "-"):
        return None
    if col_type == "integer":
        try:
            return int(value.replace(",", "").strip())
        except ValueError:
            return value
    if col_type in ("number", "currency", "percentage"):
        cleaned = (
            value.replace(",", "")
            .replace("$", "")
            .replace("\u20ac", "")
            .replace("\u00a3", "")
            .replace("%", "")
            .strip()
        )
        try:
            num = float(cleaned)
            return int(num) if num.is_integer() and col_type != "number" else num
        except ValueError:
            return value
    return value


def table_to_records(table: Dict[str, Any], coerce_types: bool = True) -> List[Dict[str, Any]]:
    """Convert a parsed table dict to a list of row objects keyed by column name."""
    columns = table.get("columns") or []
    types = table.get("types") or ["string"] * len(columns)
    records: List[Dict[str, Any]] = []
    for row in table.get("rows") or []:
        record: Dict[str, Any] = {}
        for idx, col in enumerate(columns):
            raw = row[idx] if idx < len(row) else ""
            if coerce_types and idx < len(types):
                record[col] = _coerce_cell(raw, types[idx])
            else:
                record[col] = raw
        records.append(record)
    return records


def table_to_csv(table: Dict[str, Any]) -> str:
    """Convert a parsed table dict to a CSV string (RFC-style quoting)."""
    columns = table.get("columns") or []
    if not columns:
        return ""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in table.get("rows") or []:
        writer.writerow([row[i] if i < len(row) else "" for i in range(len(columns))])
    return buf.getvalue().rstrip("\n")


def _pick_table(tables: List[Dict[str, Any]], table_index: int) -> Dict[str, Any]:
    if not tables:
        raise ValueError("No tables found in HTML")
    if table_index < 0 or table_index >= len(tables):
        raise IndexError(f"table_index {table_index} out of range (found {len(tables)} table(s))")
    return tables[table_index]


def export_table_json(
    html: str,
    table_index: int = 0,
    max_rows: Optional[int] = None,
    coerce_types: bool = True,
) -> List[Dict[str, Any]]:
    """Extract a table as JSON-ready records: [{Name: \"Alice\", Age: 30}, ...]."""
    tables = parse_tables(html, max_rows=max_rows)
    return table_to_records(_pick_table(tables, table_index), coerce_types=coerce_types)


def export_table_csv(
    html: str,
    table_index: int = 0,
    max_rows: Optional[int] = None,
) -> str:
    """Extract a table as CSV: \"Name,Age\\nAlice,30\\n...\"."""
    tables = parse_tables(html, max_rows=max_rows)
    return table_to_csv(_pick_table(tables, table_index))
