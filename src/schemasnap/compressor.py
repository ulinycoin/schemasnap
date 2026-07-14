"""
HTML compressor — strips noise, injects data-sid, builds Action Map.

Adapted from shadow-web. Dependencies: lxml only.
"""

import re
from lxml import html, etree
from typing import Dict, List, Tuple, Any, Optional

# Safe parser — no XXE, no network access (same as schema_snap.py)
_SAFE_PARSER = html.HTMLParser(no_network=True)

# Tags that are completely useless for LLMs and data extraction
REMOVE_TAGS = {
    'script', 'style', 'noscript', 'iframe',
    'meta', 'link', 'head', 'canvas', 'audio', 'video'
}

# Attributes to keep for LLM context and functionality
KEEP_ATTRS = {
    'href', 'src', 'alt', 'type', 'value', 'placeholder',
    'name', 'for', 'action', 'method', 'aria-label',
    'data-sid', 'class', 'role',
}

# Interactive tag types
INTERACTIVE_TAGS = {'a', 'button', 'input', 'select', 'textarea'}

# ── Semantic grouping (inlined from shadow-web grouping.py) ──────────

LOGIN_HINTS = re.compile(
    r"login|log in|sign in|signin|password|email|username",
    re.I,
)
CHECKOUT_HINTS = re.compile(r"checkout|payment|billing|cart|buy|order", re.I)
SEARCH_HINTS = re.compile(r"search|query|find", re.I)


def _clean(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _form_group_name(form_el) -> str:
    for attr in ("aria-label", "name", "id"):
        val = _clean(form_el.get(attr))
        if val:
            return val[:80]
    legend = form_el.find(".//legend")
    if legend is not None:
        text = _clean(legend.text_content())
        if text:
            return text[:80]
    fields = form_el.xpath(".//input | .//select | .//textarea")
    labels = " ".join(_clean(f.get("placeholder")) for f in fields)
    if "password" in {(_clean(f.get("type")) or "text").lower() for f in fields} or LOGIN_HINTS.search(labels):
        return "Login Form"
    if SEARCH_HINTS.search(labels):
        return "Search Form"
    if CHECKOUT_HINTS.search(labels):
        return "Checkout Form"
    return "Form"


def _section_group_name(el) -> Optional[str]:
    tag = el.tag.lower() if isinstance(el.tag, str) else ""
    role = _clean(el.get("role")).lower()
    if tag == "form":
        return _form_group_name(el)
    if tag == "nav" or role == "navigation":
        return "Navigation"
    if tag in ("header", "footer", "main", "aside"):
        return tag.capitalize()
    if role in ("dialog", "alertdialog"):
        return _clean(el.get("aria-label")) or "Dialog"
    if role == "search":
        return "Search"
    return None


def _find_group_for_element(el) -> str:
    current = el.getparent()
    while current is not None:
        name = _section_group_name(current)
        if name:
            return name
        current = current.getparent()
    return "Page"


def _sid_for_element(el) -> Optional[str]:
    sid = el.get("data-sid")
    return sid if sid else None


def _apply_groups(action_map: List[Dict[str, Any]], tree) -> List[Dict[str, Any]]:
    """Enrich action_map items with a ``group`` field based on DOM ancestry."""
    sid_to_group: Dict[str, str] = {}
    for el in tree.iter():
        sid = _sid_for_element(el)
        if sid:
            sid_to_group[sid] = _find_group_for_element(el)
    for action in action_map:
        sid = action.get("id", "")
        action["group"] = sid_to_group.get(sid, "Page")
    return action_map

# ── Core compressor ──────────────────────────────────────────────────


def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def get_element_label(el) -> str:
    """Extracts a human-readable label for an interactive element."""
    label = el.get('aria-label')
    if label:
        return clean_text(label)
    label = el.get('placeholder')
    if label:
        return clean_text(label)
    label = clean_text(el.text_content())
    if label:
        return label
    for attr in ('name', 'alt', 'value'):
        label = el.get(attr)
        if label:
            return clean_text(label)
    return ""


def process_html(html_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Parses HTML, strips styles/scripts, adds shadow IDs (data-sid) to interactive
    elements, extracts an Action Map with semantic groups.

    Returns:
        Tuple of (clean_html_string, action_map_list)
        Each action: {id, type, label, group, href?, placeholder?}
    """
    if not html_text or not html_text.strip():
        return "", []
    tree = html.fromstring(html_text, parser=_SAFE_PARSER)

    # 1. Collect and remove non-content tags (fix: collect first, then remove)
    nodes_to_remove = []
    for tag in REMOVE_TAGS:
        nodes_to_remove.extend(tree.xpath(f'//{tag}'))
    for el in nodes_to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    # 2. Identify interactive elements, inject data-sid and build action map
    action_map = []
    sid_counter = 1

    for el in tree.iter():
        is_interactive = False
        if el.tag in INTERACTIVE_TAGS:
            is_interactive = True
        elif el.get('role') == 'button' or el.get('onclick') is not None:
            is_interactive = True

        if is_interactive:
            sid = str(sid_counter)
            el.set('data-sid', sid)

            label = get_element_label(el)
            el_type = el.tag
            if el.tag == 'input':
                el_type = f"input[{el.get('type', 'text')}]"

            action_info = {
                "id": sid,
                "type": el_type,
                "label": label[:100],
                "href": el.get('href', ''),
                "placeholder": el.get('placeholder', ''),
            }
            action_info = {k: v for k, v in action_info.items() if v}
            action_map.append(action_info)
            sid_counter += 1

        # 3. Clean up element attributes
        attrs = list(el.attrib.keys())
        for attr in attrs:
            if attr not in KEEP_ATTRS:
                del el.attrib[attr]

    # Generate clean HTML
    clean_html = etree.tostring(tree, encoding='unicode', method='html')
    clean_html = re.sub(r'\n\s*\n', '\n', clean_html)

    # Apply semantic groups
    action_map = _apply_groups(action_map, tree)

    return clean_html, action_map


def generate_xml_map(url: str, title: str, action_map: List[Dict[str, Any]]) -> str:
    """Flat Action Map as XML."""
    root = etree.Element("page", url=url, title=title)
    for action in action_map:
        action_el = etree.SubElement(root, "action")
        for k, v in action.items():
            action_el.set(k, str(v))
    return etree.tostring(root, encoding='unicode', pretty_print=True)
