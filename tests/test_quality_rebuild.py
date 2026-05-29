"""
Acceptance tests for Story B — Code Quality Rebuild.
Tests structural ACs via file content checks and behavioral ACs via real imports.
"""
import os
import sys

# Ensure project root is on sys.path so modules can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# AC-1: summary.js has try/catch around loadSummary
# ---------------------------------------------------------------------------

def test_summary_js_has_try_catch():
    """loadSummary() has a try block."""
    content = (PROJECT_ROOT / "static" / "js" / "summary.js").read_text(encoding="utf-8")
    assert "try {" in content, "summary.js must contain 'try {'"


def test_summary_js_has_catch():
    """loadSummary() has a catch block."""
    content = (PROJECT_ROOT / "static" / "js" / "summary.js").read_text(encoding="utf-8")
    assert "catch (e)" in content, "summary.js must contain 'catch (e)'"


def test_summary_js_catch_has_failed_to_load_message():
    """The catch block shows a 'Failed to load summary' message."""
    content = (PROJECT_ROOT / "static" / "js" / "summary.js").read_text(encoding="utf-8")
    assert "Failed to load summary" in content, (
        "summary.js catch block must contain 'Failed to load summary'"
    )


# ---------------------------------------------------------------------------
# AC-2: escHtml defined in base.html, absent from JS files
# ---------------------------------------------------------------------------

def test_eschtml_in_base_html():
    """escHtml is defined in base.html."""
    content = (PROJECT_ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "function escHtml" in content, "base.html must contain 'function escHtml'"


def test_eschtml_not_in_receipts_js():
    """escHtml is NOT redefined in receipts.js."""
    content = (PROJECT_ROOT / "static" / "js" / "receipts.js").read_text(encoding="utf-8")
    assert "function escHtml" not in content, (
        "receipts.js must NOT contain 'function escHtml' (it should come from base.html)"
    )


def test_eschtml_not_in_programs_js():
    """escHtml is NOT redefined in programs.js."""
    content = (PROJECT_ROOT / "static" / "js" / "programs.js").read_text(encoding="utf-8")
    assert "function escHtml" not in content, (
        "programs.js must NOT contain 'function escHtml' (it should come from base.html)"
    )


# ---------------------------------------------------------------------------
# AC-3: renderPrograms heading uses textContent, no escHtml wrapping
# ---------------------------------------------------------------------------

def test_render_programs_heading_uses_plain_textcontent():
    """The heading assignment uses textContent, not escHtml-wrapped innerHTML."""
    content = (PROJECT_ROOT / "static" / "js" / "programs.js").read_text(encoding="utf-8")
    assert "heading.textContent" in content, (
        "programs.js must assign heading via 'heading.textContent'"
    )
    # The textContent assignment line must NOT wrap the value with escHtml()
    for line in content.splitlines():
        if "heading.textContent" in line:
            assert "escHtml(farmType)" not in line, (
                "heading.textContent line must not wrap farmType with escHtml()"
            )
            assert "escHtml(state)" not in line, (
                "heading.textContent line must not wrap state with escHtml()"
            )


# ---------------------------------------------------------------------------
# AC-4: _build_month_sheet has comment on the else / no-items branch
# ---------------------------------------------------------------------------

def test_month_sheet_no_items_comment():
    """The no-items else branch in _build_month_sheet has a comment."""
    content = (PROJECT_ROOT / "modules" / "exporter.py").read_text(encoding="utf-8")
    assert "# No line items" in content, (
        "exporter.py must contain a '# No line items' comment in _build_month_sheet"
    )


# ---------------------------------------------------------------------------
# AC-5: _strip_markdown handles all fence cases correctly
# ---------------------------------------------------------------------------

from modules.ocr import _strip_markdown  # noqa: E402 — import after path setup


def test_strip_markdown_no_fences():
    """Plain JSON passes through unchanged."""
    assert _strip_markdown('{"key": "value"}') == '{"key": "value"}'


def test_strip_markdown_with_json_fence():
    """Fenced block with language hint is unwrapped."""
    assert _strip_markdown('```json\n{"key": "value"}\n```') == '{"key": "value"}'


def test_strip_markdown_with_plain_fence():
    """Fenced block without language hint is unwrapped."""
    assert _strip_markdown('```\n{"key": "value"}\n```') == '{"key": "value"}'


def test_strip_markdown_no_closing_fence():
    """Fenced block without closing fence still returns the content."""
    assert _strip_markdown('```json\n{"key": "value"}') == '{"key": "value"}'


def test_strip_markdown_with_trailing_whitespace_on_fence():
    """Trailing whitespace after closing fence is handled gracefully."""
    result = _strip_markdown('```json\n{"key": "value"}\n```   ')
    assert result == '{"key": "value"}'


# ---------------------------------------------------------------------------
# AC-6: programCard function exists and is called in renderPrograms
# ---------------------------------------------------------------------------

def test_program_card_function_defined():
    """programCard function is defined in programs.js."""
    content = (PROJECT_ROOT / "static" / "js" / "programs.js").read_text(encoding="utf-8")
    assert "function programCard" in content, (
        "programs.js must define 'function programCard'"
    )


def test_render_programs_calls_program_card():
    """renderPrograms calls programCard (via .map())."""
    content = (PROJECT_ROOT / "static" / "js" / "programs.js").read_text(encoding="utf-8")
    # Find the renderPrograms function body and check programCard is called inside it
    assert "programCard" in content, "programs.js renderPrograms must reference programCard"
    # More specifically, verify the .map() call includes programCard
    assert ".map(" in content, "programs.js must use .map() to call programCard"
    # Verify programCard appears after renderPrograms definition (i.e., called, not just defined)
    render_idx = content.find("function renderPrograms")
    card_call_idx = content.find("programCard", render_idx)
    assert card_call_idx != -1, "programCard must be called inside renderPrograms"


# ---------------------------------------------------------------------------
# AC-7: import io is top-level, no __import__ hack
# ---------------------------------------------------------------------------

def test_import_io_is_top_level():
    """import io appears as a top-level statement in app.py."""
    content = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    # Look for a line that is exactly 'import io' (possibly with leading whitespace stripped)
    top_level_imports = [
        line.strip() for line in content.splitlines()
        if line.strip() == "import io"
    ]
    assert len(top_level_imports) >= 1, (
        "app.py must have 'import io' as a top-level import statement"
    )


def test_no_dynamic_import_io():
    """No __import__('io') hack exists in app.py."""
    content = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert '__import__("io")' not in content, (
        "app.py must not use __import__(\"io\") — use top-level import io instead"
    )
    assert "__import__('io')" not in content, (
        "app.py must not use __import__('io') — use top-level import io instead"
    )


# ---------------------------------------------------------------------------
# AC-8: error messages follow the 'Failed to load [thing]: ' pattern
# ---------------------------------------------------------------------------

def test_error_messages_receipts_js():
    """receipts.js uses the correct 'Failed to load items:' error pattern."""
    content = (PROJECT_ROOT / "static" / "js" / "receipts.js").read_text(encoding="utf-8")
    assert "Failed to load items:" in content, (
        "receipts.js must contain 'Failed to load items:'"
    )
    assert "Error loading items:" not in content, (
        "receipts.js must NOT use 'Error loading items:' — use 'Failed to load items:'"
    )


def test_error_messages_programs_js():
    """programs.js uses the correct error patterns for programs and counties."""
    content = (PROJECT_ROOT / "static" / "js" / "programs.js").read_text(encoding="utf-8")
    assert "Failed to load programs:" in content, (
        "programs.js must contain 'Failed to load programs:'"
    )
    assert "Failed to load counties:" in content, (
        "programs.js must contain 'Failed to load counties:'"
    )
    assert "Could not load county list" not in content, (
        "programs.js must NOT use 'Could not load county list'"
    )


def test_error_messages_summary_js():
    """summary.js uses the correct 'Failed to load summary:' error pattern."""
    content = (PROJECT_ROOT / "static" / "js" / "summary.js").read_text(encoding="utf-8")
    assert "Failed to load summary:" in content, (
        "summary.js must contain 'Failed to load summary:'"
    )


# ---------------------------------------------------------------------------
# AC-9: null-checks use != null ternary, not || short-circuit in receipts.js
# ---------------------------------------------------------------------------

def test_no_or_null_check_for_date():
    """receipt_date null-check uses != null, not || fallback."""
    content = (PROJECT_ROOT / "static" / "js" / "receipts.js").read_text(encoding="utf-8")
    assert "r.receipt_date ||" not in content, (
        "receipts.js must not use 'r.receipt_date ||' — use '!= null' ternary"
    )
    assert "r.receipt_date != null" in content, (
        "receipts.js must use 'r.receipt_date != null' for the null-check"
    )


def test_no_or_null_check_for_company():
    """company_name null-check uses != null, not || fallback."""
    content = (PROJECT_ROOT / "static" / "js" / "receipts.js").read_text(encoding="utf-8")
    assert "r.company_name ||" not in content, (
        "receipts.js must not use 'r.company_name ||' — use '!= null' ternary"
    )
    assert "r.company_name != null" in content, (
        "receipts.js must use 'r.company_name != null' for the null-check"
    )


# ---------------------------------------------------------------------------
# AC-10: _month_key helper exists and is called in both sheet builders
# ---------------------------------------------------------------------------

from modules.exporter import _month_key  # noqa: E402


def test_month_key_helper_exists():
    """_month_key is importable and callable."""
    assert callable(_month_key), "_month_key must be a callable function in exporter.py"


def test_month_key_full_date():
    """_month_key returns YYYY-MM from a full ISO date."""
    assert _month_key("2024-03-15") == "2024-03"


def test_month_key_year_month_only():
    """_month_key returns YYYY-MM when given a YYYY-MM string."""
    assert _month_key("2024-03") == "2024-03"


def test_month_key_empty_string():
    """_month_key returns None for empty string."""
    assert _month_key("") is None


def test_month_key_none():
    """_month_key returns None for None input."""
    assert _month_key(None) is None


def test_month_key_called_in_summary_sheet():
    """_month_key is called inside _build_summary_sheet."""
    content = (PROJECT_ROOT / "modules" / "exporter.py").read_text(encoding="utf-8")
    # Locate _build_summary_sheet and check _month_key appears in its body
    summary_idx = content.find("def _build_summary_sheet(")
    assert summary_idx != -1, "_build_summary_sheet must exist in exporter.py"
    # Next function definition after _build_summary_sheet
    next_def_idx = content.find("\ndef ", summary_idx + 1)
    body = content[summary_idx:next_def_idx] if next_def_idx != -1 else content[summary_idx:]
    assert "_month_key" in body, (
        "_month_key must be called inside _build_summary_sheet"
    )


def test_month_key_called_in_monthly_sheets():
    """_month_key is called inside _build_monthly_sheets."""
    content = (PROJECT_ROOT / "modules" / "exporter.py").read_text(encoding="utf-8")
    monthly_idx = content.find("def _build_monthly_sheets(")
    assert monthly_idx != -1, "_build_monthly_sheets must exist in exporter.py"
    next_def_idx = content.find("\ndef ", monthly_idx + 1)
    body = content[monthly_idx:next_def_idx] if next_def_idx != -1 else content[monthly_idx:]
    assert "_month_key" in body, (
        "_month_key must be called inside _build_monthly_sheets"
    )


# ---------------------------------------------------------------------------
# AC-11: _collect_error_detail helper exists and is called from scan_folder
# ---------------------------------------------------------------------------

from modules.scanner import _collect_error_detail  # noqa: E402


def test_collect_error_detail_exists():
    """_collect_error_detail is importable and callable."""
    assert callable(_collect_error_detail), (
        "_collect_error_detail must be a callable function in scanner.py"
    )


def test_collect_error_detail_called_in_scan_folder():
    """_collect_error_detail is called inside scan_folder."""
    content = (PROJECT_ROOT / "modules" / "scanner.py").read_text(encoding="utf-8")
    scan_idx = content.find("def scan_folder(")
    assert scan_idx != -1, "scan_folder must exist in scanner.py"
    next_def_idx = content.find("\ndef ", scan_idx + 1)
    body = content[scan_idx:next_def_idx] if next_def_idx != -1 else content[scan_idx:]
    assert "_collect_error_detail" in body, (
        "_collect_error_detail must be called inside scan_folder"
    )


# ---------------------------------------------------------------------------
# AC-12: modules/__init__.py contains a comment (not empty)
# ---------------------------------------------------------------------------

def test_init_py_has_comment():
    """modules/__init__.py is not empty and starts with a comment."""
    content = (PROJECT_ROOT / "modules" / "__init__.py").read_text(encoding="utf-8").strip()
    assert len(content) > 0, "modules/__init__.py must not be empty"
    assert content.startswith("#"), (
        "modules/__init__.py must start with a comment (# ...)"
    )
