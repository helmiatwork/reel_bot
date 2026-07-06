#!/usr/bin/env python3
"""
Test: niche inference model ID fix.
Asserts that:
1. The bad model ID "claude-haiku-4" is completely removed from main.py
2. The correct model ID "claude-haiku-4-5" is present where expected
"""

import sys
import ast
from pathlib import Path


def test_model_id_fix():
    """Assert the model ID fix is complete."""
    main_py = Path(__file__).parent / "main.py"
    content = main_py.read_text()

    # Assert no occurrence of the bad model ID
    bad_id = '"claude-haiku-4"'
    bad_count = content.count(bad_id)
    assert bad_count == 0, f"FAIL: Found {bad_count} occurrence(s) of bad model ID {bad_id}"

    # Assert the correct model ID is present (should be at least 4: 2 in bridge calls + 2 in fallbacks)
    good_id = '"claude-haiku-4-5"'
    good_count = content.count(good_id)
    assert good_count >= 4, f"FAIL: Expected ≥4 occurrences of {good_id}, found {good_count}"

    # Verify the file parses as valid Python
    try:
        ast.parse(content)
    except SyntaxError as e:
        raise AssertionError(f"FAIL: main.py syntax error: {e}")

    print(f"✓ Bad model ID ({bad_id}): count={bad_count} (expected 0)")
    print(f"✓ Good model ID ({good_id}): count={good_count} (expected ≥4)")
    print("✓ main.py parses as valid Python")
    print("\nAll assertions passed.")


if __name__ == "__main__":
    try:
        test_model_id_fix()
        sys.exit(0)
    except AssertionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
