#!/usr/bin/env python3
"""
Reelbot MCP Server for Antigravity

Provides tools to pull analysis/segments and generate shot-prompts/director briefs
via Claude bridge for media generation in Gemini.

Environment:
- DATABASE_URL: psycopg connection string (required)
- CLAUDE_BRIDGE_URL: Claude bridge endpoint (defaults to http://localhost:9999)

Schema (sources, video_analysis, video_segments):
- sources: id, youtube_url, title, niche, platform, channel, views_at_analysis, status, created_at
- video_analysis: youtube_url, hook, structure, retention, retention_score, tags (JSON), model, cost_usd, created_at
- video_segments: source_id, clip_index, start_sec, end_sec, credit_handle, original_url, origin_status, confidence, segment_path
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# MCP
from mcp.server.fastmcp import FastMCP

# Database
import psycopg

# HTTP to Claude bridge
import httpx

# Env
from dotenv import load_dotenv

# Load .env if present
load_dotenv(Path(__file__).parent.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
CLAUDE_BRIDGE_URL = os.getenv("CLAUDE_BRIDGE_URL", "http://localhost:9999")
PIPELINE_API_URL = os.getenv("PIPELINE_API_URL", "http://localhost:8000")
REPO_ROOT = Path(__file__).parent.parent

# MCP server
server = FastMCP("reelbot")


# ── Pure helpers (testable without DB/network) ──────────────────────────

def _valid_url(url: str) -> bool:
    """
    Validate that a URL is non-empty and looks like an http(s) URL.

    Returns True if valid, False otherwise.
    """
    if not url or not isinstance(url, str):
        return False
    url_lower = url.lower().strip()
    return url_lower.startswith("http://") or url_lower.startswith("https://")


def _clamp_limit(limit: int) -> int:
    """Clamp limit to [1, 100]."""
    return max(1, min(int(limit), 100))


def _parse_tags(tags_input) -> list:
    """
    Parse tags field (may be string JSON, dict, list, or None).
    Returns list of strings; empty list on any error.
    """
    if tags_input is None:
        return []
    if isinstance(tags_input, list):
        return tags_input
    if isinstance(tags_input, dict):
        return []
    if isinstance(tags_input, str):
        try:
            parsed = json.loads(tags_input)
            if isinstance(parsed, list):
                return parsed
            return []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _source_row_to_dict(row, cols: list) -> dict:
    """Map a sources row to a dict."""
    result = dict(zip(cols, row))
    # Ensure numeric types
    if "id" in result and result["id"] is not None:
        result["id"] = int(result["id"])
    if "views_at_analysis" in result and result["views_at_analysis"] is not None:
        result["views_at_analysis"] = int(result["views_at_analysis"])
    return result


def _analysis_row_to_dict(row, cols: list) -> dict:
    """Map a video_analysis row to a dict."""
    result = dict(zip(cols, row))
    # Parse tags
    if "tags" in result:
        result["tags"] = _parse_tags(result["tags"])
    # Ensure cost_usd is float
    if "cost_usd" in result and result["cost_usd"] is not None:
        result["cost_usd"] = float(result["cost_usd"])
    # Ensure retention_score is int
    if "retention_score" in result and result["retention_score"] is not None:
        result["retention_score"] = int(result["retention_score"])
    return result


def _segment_row_to_dict(row, cols: list) -> dict:
    """Map a video_segments row to a dict."""
    result = dict(zip(cols, row))
    # Ensure numeric types
    if "clip_index" in result and result["clip_index"] is not None:
        result["clip_index"] = int(result["clip_index"])
    if "start_sec" in result and result["start_sec"] is not None:
        result["start_sec"] = float(result["start_sec"])
    if "end_sec" in result and result["end_sec"] is not None:
        result["end_sec"] = float(result["end_sec"])
    if "confidence" in result and result["confidence"] is not None:
        result["confidence"] = float(result["confidence"])
    return result


def _read_soul(agent_name: str) -> str:
    """
    Read SOUL.md file for a given agent.

    Args:
        agent_name: one of {shotprompt, director}

    Returns:
        file contents or empty string if not found/invalid

    Raises:
        ValueError if agent_name is not in the whitelist
    """
    if agent_name not in {"shotprompt", "director"}:
        raise ValueError(f"agent_name must be 'shotprompt' or 'director', got {agent_name}")

    soul_path = REPO_ROOT / "openclaw" / "agents" / agent_name / "SOUL.md"
    if not soul_path.exists():
        return ""

    try:
        return soul_path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _call_claude_bridge(prompt: str) -> tuple[bool, str]:
    """
    POST a prompt to Claude bridge and return (ok: bool, result_or_error: str).

    Returns:
        (True, result_text) on success
        (False, error_msg) on failure
    """
    try:
        resp = httpx.post(
            f"{CLAUDE_BRIDGE_URL}/run",
            json={"prompt": prompt, "frames": [], "model": "claude-sonnet-4-6"},
            timeout=httpx.Timeout(connect=10.0, read=200.0, write=10.0, pool=5.0),
        )
    except Exception as e:
        return False, f"bridge connection error: {e}"

    try:
        data = resp.json()
    except Exception as e:
        return False, f"bridge response parse error: {e}"

    if not data.get("ok"):
        return False, data.get("error", "bridge failed with unknown error")

    result = data.get("result", "")
    return True, result


# ── MCP tools (require DB or network) ──────────────────────────────────

@server.tool()
def list_sources(limit: int = 25) -> dict:
    """
    List recent sources from the database.

    Args:
        limit: number of sources to return (clamped to 1–100)

    Returns:
        {"sources": [{"id", "title", "niche", "platform", "youtube_url", "status"}, ...], "count": int}
    """
    limit = _clamp_limit(limit)

    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured", "sources": [], "count": 0}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}", "sources": [], "count": 0}

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, niche, platform, youtube_url, status FROM sources "
                "ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            cols = [c.name for c in cur.description] if cur.description else []
            rows = cur.fetchall()
            sources = [_source_row_to_dict(row, cols) for row in rows]
        return {"sources": sources, "count": len(sources)}
    except Exception as e:
        return {"error": f"query failed: {e}", "sources": [], "count": 0}
    finally:
        conn.close()


@server.tool()
def get_analysis(youtube_url: str) -> dict:
    """
    Get the latest video_analysis for a YouTube URL.

    Args:
        youtube_url: the YouTube URL

    Returns:
        {"analysis": {dict with hook, structure, retention, retention_score, tags, model, cost_usd}}
        or {"error": "...", "analysis": {}} if not found
    """
    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured", "analysis": {}}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}", "analysis": {}}

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT youtube_url, hook, structure, retention, retention_score, tags, model, cost_usd "
                "FROM video_analysis WHERE youtube_url = %s ORDER BY created_at DESC LIMIT 1",
                (youtube_url,)
            )
            row = cur.fetchone()
            if not row:
                return {"error": "analysis not found", "analysis": {}}
            cols = [c.name for c in cur.description]
            analysis = _analysis_row_to_dict(row, cols)
        return {"analysis": analysis}
    except Exception as e:
        return {"error": f"query failed: {e}", "analysis": {}}
    finally:
        conn.close()


@server.tool()
def get_segments(source_id: int) -> dict:
    """
    Get video_segments for a source.

    Args:
        source_id: the source ID

    Returns:
        {"source_id": int, "segments": [dicts with clip_index, start_sec, end_sec, ...], "count": int}
        or {"error": "...", "segments": []}
    """
    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured", "segments": [], "count": 0}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}", "segments": [], "count": 0}

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT clip_index, start_sec, end_sec, credit_handle, original_url, "
                "origin_status, confidence, segment_path FROM video_segments "
                "WHERE source_id = %s ORDER BY clip_index ASC",
                (source_id,)
            )
            cols = [c.name for c in cur.description] if cur.description else []
            rows = cur.fetchall()
            segments = [_segment_row_to_dict(row, cols) for row in rows]
        return {"source_id": source_id, "segments": segments, "count": len(segments)}
    except Exception as e:
        return {"error": f"query failed: {e}", "segments": [], "count": 0}
    finally:
        conn.close()


@server.tool()
def generate_shot_prompts(script_text: str, style_note: str = "") -> dict:
    """
    Generate Gemini image→video prompts from a script.

    Reads shotprompt/SOUL.md, builds a prompt, calls Claude bridge.

    Args:
        script_text: the beat-by-beat script
        style_note: optional style/mood guidance

    Returns:
        {"prompts": str, "model": "claude-sonnet-4-6"} or {"error": "...", "prompts": ""}
    """
    try:
        soul = _read_soul("shotprompt")
    except ValueError as e:
        return {"error": f"invalid agent: {e}", "prompts": ""}

    if not soul:
        return {"error": "shotprompt/SOUL.md not found", "prompts": ""}

    # Build prompt
    style_section = f"STYLE NOTE: {style_note}\n\n" if style_note.strip() else ""
    prompt = (
        f"{soul}\n\n"
        f"---\n\n"
        f"{style_section}"
        f"SCRIPT:\n{script_text}\n\n"
        f"Produce the per-beat image→video prompts now."
    )

    ok, result = _call_claude_bridge(prompt)
    if not ok:
        return {"error": result, "prompts": ""}

    return {"prompts": result, "model": "claude-sonnet-4-6"}


@server.tool()
def make_brief(analysis_json: str, target: str = "") -> dict:
    """
    Generate a Production Brief from video analysis.

    Reads director/SOUL.md, builds a prompt with analysis + target, calls Claude bridge.

    Args:
        analysis_json: JSON string of video_analysis (hook, structure, tags, retention_score, etc.)
        target: optional target audience/niche/platform

    Returns:
        {"brief": str, "model": "claude-sonnet-4-6"} or {"error": "...", "brief": ""}
    """
    try:
        soul = _read_soul("director")
    except ValueError as e:
        return {"error": f"invalid agent: {e}", "brief": ""}

    if not soul:
        return {"error": "director/SOUL.md not found", "brief": ""}

    target_section = f"TARGET: {target}\n\n" if target.strip() else ""
    prompt = (
        f"{soul}\n\n"
        f"---\n\n"
        f"ANALYSIS:\n{analysis_json}\n\n"
        f"{target_section}"
        f"Produce the Production Brief now."
    )

    ok, result = _call_claude_bridge(prompt)
    if not ok:
        return {"error": result, "brief": ""}

    return {"brief": result, "model": "claude-sonnet-4-6"}


@server.tool()
def analyze(youtube_url: str, intent: str = "") -> dict:
    """
    Run a fresh Claude-vision analysis of a YouTube video and save it to the corpus DB.

    POSTs to the running pipeline-api /analyze/claude endpoint. Synchronous call;
    may take a minute or more (download + vision).

    Args:
        youtube_url: the YouTube video URL to analyze
        intent: optional intent/context for the analysis (e.g., "find viral hooks")

    Returns:
        {"hook", "structure", "retention", "retention_score", "tags", "model", "cost_usd", "cached"}
        or {"error": "<message>"} on failure
    """
    # Validate URL
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url"}

    try:
        resp = httpx.post(
            f"{PIPELINE_API_URL}/analyze/claude",
            json={"youtube_url": youtube_url, "intent": intent},
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=5.0),
        )
    except httpx.ConnectError as e:
        return {"error": f"pipeline-api unreachable: {e}"}
    except httpx.TimeoutException as e:
        return {"error": f"pipeline-api timeout (analysis may still be running): {e}"}
    except Exception as e:
        return {"error": f"request failed: {e}"}

    try:
        data = resp.json()
    except Exception as e:
        return {"error": f"response parse error: {e}"}

    # If HTTP error, return error from response body
    if resp.status_code >= 400:
        error_detail = data.get("detail", f"HTTP {resp.status_code}")
        return {"error": error_detail}

    # Return the full response (hook, structure, retention, retention_score, tags, model, cost_usd, cached)
    return data


# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    server.run()
