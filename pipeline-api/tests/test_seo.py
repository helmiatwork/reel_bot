"""
Unit tests for SEO agent helpers in pipeline-api/main.py.

Covers:
- _seo_autocomplete: parses the [query, [suggestions,...]] shape correctly
- _seo_autocomplete: returns [] on bad/empty response
- _seo_trends: returns safe empty dict when pytrends raises
- _seo_trends: returns safe empty dict when pytrends is missing
- _seo_synthesize: returns {} when CLIPROXY_KEY is absent
- _seo_synthesize: returns {} on HTTP error
- _seo_synthesize: strips ```json fences before JSON parse
- SeoAnalyzeRequest: endpoint returns 400 when topic is blank (no network)

Run:
    cd pipeline-api && pytest tests/test_seo.py -v
"""
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _seo_autocomplete, _seo_trends, _seo_synthesize  # noqa: E402


# ── _seo_autocomplete ─────────────────────────────────────────────────────────

def _make_suggest_response(seed: str, suggestions: list) -> MagicMock:
    """Build a mock httpx Response matching Google's [query, [suggestions]] shape."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [seed, suggestions]
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_autocomplete_parses_suggest_shape():
    """Parser must extract resp[1] — the suggestion list — correctly."""
    suggestions = ["street food tokyo", "street food japan", "street food viral"]
    mock_resp = _make_suggest_response("street food", suggestions)

    with patch("httpx.get", return_value=mock_resp):
        result = _seo_autocomplete("street food", platform="youtube")

    # Base seed returns the 3 suggestions; no alphabet expansion needed
    assert "street food tokyo" in result
    assert "street food japan" in result
    assert isinstance(result, list)


def test_autocomplete_deduplicates():
    """Terms appearing in multiple expansion calls are deduplicated."""
    # Both the base call and the 'a' expansion return overlapping terms
    def fake_get(url, timeout=5.0):
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        mock.json.return_value = ["q", ["food a", "food b"]]
        return mock

    with patch("httpx.get", side_effect=fake_get):
        result = _seo_autocomplete("food", platform="youtube")

    # "food a" and "food b" appear only once despite many calls
    assert result.count("food a") == 1
    assert result.count("food b") == 1


def test_autocomplete_caps_at_30():
    """Result is capped at 30 terms."""
    long_list = [f"term {i}" for i in range(100)]
    mock_resp = _make_suggest_response("topic", long_list)

    with patch("httpx.get", return_value=mock_resp):
        result = _seo_autocomplete("topic")

    assert len(result) <= 30


def test_autocomplete_empty_on_network_error():
    """Network failures return [] — never raise."""
    with patch("httpx.get", side_effect=Exception("network down")):
        result = _seo_autocomplete("anything")

    assert result == []


def test_autocomplete_empty_on_malformed_response():
    """Non-list or wrong-shape response returns [] — never raise."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"unexpected": "dict"}

    with patch("httpx.get", return_value=mock_resp):
        result = _seo_autocomplete("anything")

    assert result == []


def test_autocomplete_google_platform_skips_ds_param():
    """Platform='google' must NOT add ds=yt to the request URL."""
    calls = []

    def capture_get(url, timeout=5.0):
        calls.append(url)
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        mock.json.return_value = ["q", []]
        return mock

    with patch("httpx.get", side_effect=capture_get):
        _seo_autocomplete("food", platform="google")

    assert calls, "httpx.get should have been called at least once"
    assert "ds=yt" not in calls[0]


# ── _seo_trends ───────────────────────────────────────────────────────────────

def test_trends_returns_empty_when_pytrends_unavailable():
    """If pytrends is not installed, _seo_trends returns the safe empty dict."""
    import importlib
    import builtins

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "pytrends.request":
            raise ImportError("pytrends not installed")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        result = _seo_trends("street food")

    assert result == {"related_top": [], "related_rising": [], "interest": []}


def test_trends_returns_empty_on_http_429():
    """HTTP 429 / TooManyRequests from pytrends returns safe empty dict."""
    with patch("pytrends.request.TrendReq") as mock_cls:
        mock_cls.side_effect = Exception("429 Too Many Requests")
        result = _seo_trends("ramen")

    assert result == {"related_top": [], "related_rising": [], "interest": []}


def test_trends_returns_empty_on_any_exception():
    """Any unexpected exception returns the safe empty dict — never raises."""
    with patch("pytrends.request.TrendReq", side_effect=RuntimeError("boom")):
        result = _seo_trends("anything")

    assert result == {"related_top": [], "related_rising": [], "interest": []}


def test_trends_result_shape_when_successful():
    """When pytrends works, result has the expected keys."""
    import pandas as pd

    top_df = pd.DataFrame({"query": ["sushi recipe", "sushi roll"], "value": [100, 80]})
    rising_df = pd.DataFrame({"query": ["sushi viral", "sushi asmr"], "value": [5000, 3200]})
    iot_df = pd.DataFrame({"sushi": [60, 80, 100]}, index=pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"]))

    mock_pt = MagicMock()
    mock_pt.related_queries.return_value = {"sushi": {"top": top_df, "rising": rising_df}}
    mock_pt.interest_over_time.return_value = iot_df

    with patch("pytrends.request.TrendReq", return_value=mock_pt):
        result = _seo_trends("sushi")

    assert "related_top" in result
    assert "related_rising" in result
    assert "interest" in result
    assert result["related_top"][0]["query"] == "sushi recipe"
    assert result["related_rising"][0]["query"] == "sushi viral"
    assert len(result["interest"]) == 3


# ── _seo_synthesize ───────────────────────────────────────────────────────────

def test_synthesize_returns_empty_when_no_key(monkeypatch):
    """Without CLIPROXY_KEY set, synthesize returns {} immediately."""
    monkeypatch.delenv("CLIPROXY_KEY", raising=False)
    result = _seo_synthesize("topic", [], {}, "youtube")
    assert result == {}


def test_synthesize_returns_empty_on_http_error(monkeypatch):
    """HTTP failure returns {} — never raises."""
    monkeypatch.setenv("CLIPROXY_KEY", "test-key")
    monkeypatch.setenv("CLIPROXY_URL", "http://localhost:8317/v1")

    with patch("httpx.post", side_effect=Exception("connection refused")):
        result = _seo_synthesize("topic", [], {}, "youtube")

    assert result == {}


def test_synthesize_strips_json_fences(monkeypatch):
    """```json ... ``` fences are stripped before JSON parsing."""
    monkeypatch.setenv("CLIPROXY_KEY", "test-key")
    monkeypatch.setenv("CLIPROXY_URL", "http://localhost:8317/v1")

    payload = {
        "titles": ["Title 1", "Title 2", "Title 3"],
        "hashtags": ["#food", "#viral"],
        "description": "Great food content.",
    }
    fenced = f"```json\n{json.dumps(payload)}\n```"

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": fenced}}]
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _seo_synthesize("food", [], {}, "youtube")

    assert result["titles"] == payload["titles"]
    assert result["hashtags"] == payload["hashtags"]
    assert result["description"] == payload["description"]


def test_synthesize_clean_json(monkeypatch):
    """Clean JSON response (no fences) is parsed correctly."""
    monkeypatch.setenv("CLIPROXY_KEY", "test-key")
    monkeypatch.setenv("CLIPROXY_URL", "http://localhost:8317/v1")

    payload = {
        "titles": ["Viral Ramen Recipe"],
        "hashtags": ["#ramen", "#japanese"],
        "description": "Best ramen in Tokyo.",
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _seo_synthesize("ramen", [], {}, "youtube")

    assert result["titles"] == ["Viral Ramen Recipe"]


def test_synthesize_returns_empty_on_bad_json(monkeypatch):
    """Non-JSON response body returns {} — never raises."""
    monkeypatch.setenv("CLIPROXY_KEY", "test-key")
    monkeypatch.setenv("CLIPROXY_URL", "http://localhost:8317/v1")

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "not valid json at all"}}]
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _seo_synthesize("topic", [], {}, "youtube")

    assert result == {}
