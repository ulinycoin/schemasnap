"""
SchemaSnap — structured data extraction from web pages.

Usage:
    from schemasnap import extract_from_url, extract_from_html, parse_page

    result = extract_from_url("https://example.com/data")
    print(result.tables)  # [{columns, types, rows, ...}]
    print(result.forms)   # [{action, method, fields: [...]}]
"""

from .extractor import ExtractResult, extract_from_url, extract_from_html, validate_url
from .compressor import process_html, generate_xml_map
from .schema_snap import (
    parse_tables,
    parse_forms,
    parse_lists,
    parse_page,
    table_to_records,
    table_to_csv,
    export_table_json,
    export_table_csv,
)

__all__ = [
    "extract_from_url",
    "extract_from_html",
    "validate_url",
    "ExtractResult",
    "process_html",
    "generate_xml_map",
    "parse_tables",
    "parse_forms",
    "parse_lists",
    "parse_page",
    "table_to_records",
    "table_to_csv",
    "export_table_json",
    "export_table_csv",
]

__version__ = "0.1.7"
