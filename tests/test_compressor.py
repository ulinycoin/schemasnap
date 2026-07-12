"""Unit tests for SchemaSnap compressor module."""

from schemasnap.compressor import process_html, clean_text, get_element_label

# ── Fixtures ──────────────────────────────────────────────────────

SIMPLE_PAGE = """\
<html><body>
<h1>Welcome</h1>
<a href="/login">Sign in</a>
<form action="/search" method="get">
  <input type="text" name="q" placeholder="Search...">
  <button type="submit">Go</button>
</form>
<script>console.log('noise')</script>
</body></html>
"""

PAGE_WITH_TABLE = """\
<html><body>
<table>
  <thead><tr><th>Name</th><th>Age</th></tr></thead>
  <tbody>
    <tr><td>Alice</td><td>30</td></tr>
    <tr><td>Bob</td><td>25</td></tr>
  </tbody>
</table>
<style>body { color: red; }</style>
<nav><a href="/">Home</a></nav>
</body></html>
"""

LOGIN_PAGE = """\
<html><body>
<form method="post" action="/login">
  <input type="email" name="email" placeholder="Email" required>
  <input type="password" name="password" placeholder="Password" minlength="8">
  <button type="submit">Sign In</button>
</form>
</body></html>
"""


# ── Tests ─────────────────────────────────────────────────────────


def test_process_html_removes_noise_tags():
    clean_html, actions = process_html(SIMPLE_PAGE)
    assert "script" not in clean_html
    assert "console.log" not in clean_html


def test_process_html_keeps_interactive_elements():
    clean_html, actions = process_html(SIMPLE_PAGE)
    # Should have interactive elements with data-sid
    assert "data-sid" in clean_html
    assert len(actions) >= 2  # at least the link and the form input


def test_process_html_action_map_structure():
    clean_html, actions = process_html(SIMPLE_PAGE)
    link_actions = [a for a in actions if a.get("type") == "a"]
    assert len(link_actions) == 1
    link = link_actions[0]
    assert link["id"] == "1" or "1" in [a["id"] for a in actions]
    assert "group" in link


def test_process_html_assigns_semantic_groups():
    clean_html, actions = process_html(LOGIN_PAGE)
    # Login form fields should get "Login Form" group
    groups = {a.get("group", "") for a in actions}
    assert "Login Form" in groups or any("orm" in g for g in groups)


def test_process_html_with_table():
    clean_html, actions = process_html(PAGE_WITH_TABLE)
    assert "Alice" in clean_html
    assert "Bob" in clean_html
    assert "style" not in clean_html.lower() or "color" not in clean_html
    # Navigation should get "Navigation" group
    groups = {a.get("group", "") for a in actions}
    assert "Navigation" in groups


def test_process_html_empty():
    clean_html, actions = process_html("")
    assert clean_html is not None
    assert actions == []


def test_clean_text_normalizes_whitespace():
    assert clean_text("  hello   world  ") == "hello world"
    assert clean_text("\n\ttest\n") == "test"
    assert clean_text("") == ""
