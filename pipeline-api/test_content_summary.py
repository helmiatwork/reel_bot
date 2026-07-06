#!/usr/bin/env python3
"""
Test: verify content_summary and content_detail are wired in prompt, DB, and return shape.
This is a pure helper test — no pytest framework, just assertions + __main__.
"""

import ast
import re
import json


def test_prompt_template():
    """Assert the prompt template now contains 'summary' and 'detail' fields."""
    # Read main.py and extract the _CLAUDE_RE_PROMPT_TEMPLATE
    with open("main.py", "r") as f:
        content = f.read()

    # Find the template string
    match = re.search(r'_CLAUDE_RE_PROMPT_TEMPLATE = """(.*?)"""', content, re.DOTALL)
    assert match, "Could not find _CLAUDE_RE_PROMPT_TEMPLATE in main.py"

    template = match.group(1)

    # Check for the JSON structure with both fields
    assert '"summary"' in template, "Prompt template missing 'summary' field"
    assert '"detail"' in template, "Prompt template missing 'detail' field"
    assert '1 kalimat lugas' in template, "Prompt template summary instruction missing"
    assert 'play-by-play' in template, "Prompt template detail instruction missing"

    print("✓ Prompt template contains summary and detail fields")


def test_db_migration():
    """Assert db/video_analysis.sql contains both ALTER lines."""
    with open("../db/video_analysis.sql", "r") as f:
        sql = f.read()

    assert "content_summary" in sql, "DB migration missing content_summary column"
    assert "content_detail" in sql, "DB migration missing content_detail column"
    assert "ALTER TABLE video_analysis ADD COLUMN IF NOT EXISTS content_summary TEXT" in sql
    assert "ALTER TABLE video_analysis ADD COLUMN IF NOT EXISTS content_detail TEXT" in sql

    print("✓ DB migration adds both content_summary and content_detail columns")


def test_main_py_parse_section():
    """Assert main.py parses summary and detail from the JSON result."""
    with open("main.py", "r") as f:
        content = f.read()

    # Check that summary and detail are extracted
    assert 'summary = parsed.get("summary", "")' in content, "main.py missing summary parse"
    assert 'detail = parsed.get("detail", "")' in content, "main.py missing detail parse"

    print("✓ main.py parses summary and detail from JSON")


def test_main_py_insert_section():
    """Assert main.py INSERT statement includes the new columns."""
    with open("main.py", "r") as f:
        content = f.read()

    # Check INSERT statement for new columns
    assert "content_summary" in content and "content_detail" in content, \
        "INSERT statement missing content_summary or content_detail"

    # Check that summary and detail are included in the VALUES tuple
    assert "summary or None" in content, "INSERT not passing summary to DB"
    assert "detail or None" in content, "INSERT not passing detail to DB"

    print("✓ main.py INSERT includes content_summary and content_detail")


def test_main_py_return_section():
    """Assert main.py returns summary and detail in both fresh and cached paths."""
    with open("main.py", "r") as f:
        content = f.read()

    # Fresh path return
    fresh_return = re.search(
        r'return _json\(\{\s*"youtube_url": req\.youtube_url,\s*"summary":',
        content,
        re.DOTALL
    )
    assert fresh_return, "Fresh path return missing summary field"

    # Cached path return
    cached_return = re.search(
        r'"summary": cached_summary,',
        content
    )
    assert cached_return, "Cached path return missing summary field"

    print("✓ main.py returns summary and detail in fresh and cached paths")


def test_main_py_select_statement():
    """Assert SELECT statement includes content_summary and content_detail columns."""
    with open("main.py", "r") as f:
        content = f.read()

    # Find the SELECT for cached rows
    select_match = re.search(
        r'SELECT youtube_url, intent, hook, structure, retention, tags, model, cost_usd, created_at, retention_score, content_summary, content_detail',
        content
    )
    assert select_match, "SELECT statement missing content_summary or content_detail"

    # Check that indices are properly handled
    assert "cached_summary = cached_row[10]" in content, "Missing cached_summary index extraction"
    assert "cached_detail = cached_row[11]" in content, "Missing cached_detail index extraction"

    print("✓ main.py SELECT includes new columns with correct indices")


def test_soul_template():
    """Assert SOUL.md includes the new Isi Video section."""
    with open("../openclaw/agents/main/SOUL.md", "r") as f:
        soul = f.read()

    assert "📹 **Isi Video**" in soul, "SOUL.md missing Isi Video section"
    assert "Ringkas: <summary>" in soul, "SOUL.md missing summary render instruction"
    assert "Detail: <detail>" in soul, "SOUL.md missing detail render instruction"
    assert 'if both `summary` AND `detail` are empty' in soul, \
        "SOUL.md missing instruction for handling empty old rows"

    print("✓ SOUL.md includes Isi Video section with summary and detail")


def main():
    """Run all tests."""
    try:
        test_prompt_template()
        test_db_migration()
        test_main_py_parse_section()
        test_main_py_insert_section()
        test_main_py_return_section()
        test_main_py_select_statement()
        test_soul_template()

        print("\n✅ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
