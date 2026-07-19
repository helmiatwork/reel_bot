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
- video_analysis: id, youtube_url, intent, hook, structure, retention, retention_score, tags (JSONB), raw_result, model, cost_usd, content_summary, content_detail, created_at
- video_segments: source_id, clip_index, start_sec, end_sec, credit_handle, original_url, origin_status, confidence, segment_path

STORYBOARD FLOW: get_clips → save_analysis (optional) → save_storyboard
"""

import json
import os
import sys
import hashlib
from pathlib import Path
from typing import Optional

# MCP
from mcp.server.fastmcp import FastMCP

# Database
import psycopg
from psycopg.types.json import Jsonb

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
        {"analysis": {dict with hook, structure, retention, retention_score, tags, model, cost_usd, content_summary, content_detail}}
        or {"error": "...", "analysis": {}} if not found
    """
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url", "analysis": {}}

    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured", "analysis": {}}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}", "analysis": {}}

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT youtube_url, hook, structure, retention, retention_score, tags, model, cost_usd, content_summary, content_detail "
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
    Not part of the Gemini storyboard flow (get_clips + save_storyboard). Only use if explicitly asked.

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
    Not part of the Gemini storyboard flow (get_clips + save_storyboard). Only use if explicitly asked.

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
    DO NOT USE for the Gemini storyboard flow. This runs the separate CLAUDE vision pipeline (downloads + Claude analysis) and will incur cost and ignore your work. For building a storyboard from decomposed clips, use get_clips + save_storyboard instead.

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


@server.tool()
def save_storyboard(youtube_url: str, storyboard_json: str) -> dict:
    """
    STORYBOARD FLOW STEP 2 (final). Call this after analyzing the clips to persist the per-scene storyboard JSON to the database. This is the ONLY correct way to save a Gemini-produced storyboard.

    Save a storyboard (scene-by-scene breakdown) to the sources table.

    Args:
        youtube_url: the YouTube URL to associate with the storyboard
        storyboard_json: JSON string or dict with {aspect_ratio, overall_style, music_mood, scene_order: []}

    Returns:
        {"ok": true, "youtube_url": ..., "scenes": N} on success
        {"error": "..."} on failure (invalid URL, bad JSON, empty scene_order)
    """
    # Validate URL
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url"}

    # Parse storyboard_json (accept string or dict)
    if isinstance(storyboard_json, str):
        try:
            storyboard_dict = json.loads(storyboard_json)
        except (json.JSONDecodeError, ValueError):
            return {"error": "storyboard_json is not valid JSON"}
    elif isinstance(storyboard_json, dict):
        storyboard_dict = storyboard_json
    else:
        return {"error": "storyboard_json must be a JSON string or dict"}

    # Validate scene_order
    scene_order = storyboard_dict.get("scene_order")
    if not isinstance(scene_order, list) or not scene_order:
        return {"error": "storyboard must contain a non-empty scene_order array"}

    # DB write: UPDATE or INSERT
    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured"}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}"}

    try:
        with conn.cursor() as cur:
            # Compact JSON string for storage
            gen_prompt_json = json.dumps(storyboard_dict, separators=(',', ':'))

            # Try UPDATE first
            cur.execute(
                "UPDATE sources SET gen_prompt=%s, gen_prompt_format='prompt_json', status='analyzed' "
                "WHERE youtube_url=%s",
                (gen_prompt_json, youtube_url)
            )
            rows_updated = cur.rowcount

            # If UPDATE didn't match, INSERT
            if rows_updated == 0:
                cur.execute(
                    "INSERT INTO sources (youtube_url, platform, status, gen_prompt, gen_prompt_format) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (youtube_url, "youtube", "analyzed", gen_prompt_json, "prompt_json")
                )

            conn.commit()
        return {"ok": True, "youtube_url": youtube_url, "scenes": len(scene_order)}
    except Exception as e:
        conn.rollback()
        return {"error": f"database error: {e}"}
    finally:
        conn.close()


@server.tool()
def save_analysis(youtube_url: str, analysis_json: str) -> dict:
    """
    STORYBOARD FLOW STEP 2 (optional companion). Call this after analyzing the clips to persist the video ANALYSIS (hook/retention/structure/summary/detail/tags) produced from the same clips. Use ONLY get_clips, save_analysis, save_storyboard in the Gemini flow.

    Save video analysis results to the database.

    Args:
        youtube_url: the YouTube URL to associate with the analysis
        analysis_json: JSON string or dict with {hook, hook_start, hook_end, retention, retention_score, retention_points, structure, summary, detail, tags, intent (optional)}

    Returns:
        {"ok": true, "youtube_url": ..., "saved": true} on success
        {"error": "..."} on failure (invalid URL, bad JSON, empty analysis)
    """
    # Validate URL
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url"}

    # Parse analysis_json (accept string or dict)
    if isinstance(analysis_json, str):
        try:
            analysis_dict = json.loads(analysis_json)
        except (json.JSONDecodeError, ValueError):
            return {"error": "analysis_json is not valid JSON"}
    elif isinstance(analysis_json, dict):
        analysis_dict = analysis_json
    else:
        return {"error": "analysis_json must be a JSON string or dict"}

    # Require at least one of the main fields
    required_fields = ["hook", "structure", "retention", "content_summary", "content_detail"]
    has_content = any(analysis_dict.get(field) for field in required_fields)
    if not has_content:
        return {"error": "analysis is empty; must contain at least one of: hook, structure, retention, content_summary, content_detail"}

    # Extract fields (map user names to DB column names)
    hook = analysis_dict.get("hook")
    structure = analysis_dict.get("structure")
    retention = analysis_dict.get("retention")
    retention_score = analysis_dict.get("retention_score")
    content_summary = analysis_dict.get("summary") or analysis_dict.get("content_summary")
    content_detail = analysis_dict.get("detail") or analysis_dict.get("content_detail")
    tags = analysis_dict.get("tags")
    intent = analysis_dict.get("intent")

    # Coerce retention_score to int if present
    if retention_score is not None:
        try:
            retention_score = int(retention_score)
        except (ValueError, TypeError):
            retention_score = None

    # Parse tags if present
    if tags is not None:
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)  # Parse string to list/dict
            except (json.JSONDecodeError, ValueError):
                tags = None
        # Wrap as JSONB for psycopg3 database insertion
        if not isinstance(tags, (list, dict)):
            tags = None
        tags_db = Jsonb(tags) if tags is not None else None

    # DB write: INSERT new row (no upsert)
    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured"}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}"}

    try:
        with conn.cursor() as cur:
            # Store compact JSON of full input in raw_result
            raw_result_json = json.dumps(analysis_dict, separators=(',', ':'))

            # INSERT new row
            cur.execute(
                "INSERT INTO video_analysis "
                "(youtube_url, intent, hook, structure, retention, retention_score, content_summary, content_detail, tags, raw_result, model, cost_usd) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    youtube_url,
                    intent,
                    hook,
                    structure,
                    retention,
                    retention_score,
                    content_summary,
                    content_detail,
                    tags_db,
                    raw_result_json,
                    "gemini-antigravity",
                    0  # cost_usd = 0 for Gemini (free)
                )
            )

            # Also ensure sources row exists with status='analyzed'
            cur.execute(
                "UPDATE sources SET status='analyzed' WHERE youtube_url=%s",
                (youtube_url,)
            )
            rows_updated = cur.rowcount

            # If UPDATE didn't match, INSERT minimal sources row
            if rows_updated == 0:
                cur.execute(
                    "INSERT INTO sources (youtube_url, platform, status) VALUES (%s, %s, %s)",
                    (youtube_url, "youtube", "analyzed")
                )

            conn.commit()
        return {"ok": True, "youtube_url": youtube_url, "saved": True}
    except Exception as e:
        conn.rollback()
        return {"error": f"database error: {e}"}
    finally:
        conn.close()


@server.tool()
def save_ideas(youtube_url: str, ideas_json: str) -> dict:
    """
    IDEA FLOW STEP 1 (final save). Call this after brainstorming candidate ideas to persist them to the database. This is the ONLY correct way to save candidates.

    Save candidate ideas to the source_ideas table.

    Args:
        youtube_url: the YouTube URL to associate with the ideas
        ideas_json: JSON string or list of candidate ideas, each with at least {title, description}. Must be non-empty.

    Returns:
        {"ok": true, "youtube_url": ..., "count": N} on success
        {"error": "..."} on failure (invalid URL, bad JSON, empty list)
    """
    # Validate URL
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url"}

    # Parse ideas_json (accept string or list)
    if isinstance(ideas_json, str):
        try:
            ideas_list = json.loads(ideas_json)
        except (json.JSONDecodeError, ValueError):
            return {"error": "ideas_json is not valid JSON"}
    elif isinstance(ideas_json, list):
        ideas_list = ideas_json
    else:
        return {"error": "ideas_json must be a JSON string or list"}

    # Require a non-empty list
    if not isinstance(ideas_list, list) or not ideas_list:
        return {"error": "ideas_json must be a non-empty list"}

    # Lenient validation: each item should be a dict-like object (require at least one field)
    # Don't hard-fail on missing optional keys, but reject if not iterable as dicts
    for idea in ideas_list:
        if not isinstance(idea, dict):
            return {"error": "each idea must be a dict/object"}

    # DB write: UPSERT into source_ideas
    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured"}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}"}

    try:
        with conn.cursor() as cur:
            ideas_jsonb = Jsonb(ideas_list)

            # Look up source_id by youtube_url (may be NULL if no source row yet)
            cur.execute("SELECT id FROM sources WHERE youtube_url = %s", (youtube_url,))
            source_row = cur.fetchone()
            source_id = source_row[0] if source_row else None

            # UPSERT: insert or update candidates, resetting selected_index and detail
            cur.execute(
                """INSERT INTO source_ideas (source_id, youtube_url, candidates, candidates_at, selected_index, detail, updated_at)
                   VALUES (%s, %s, %s, now(), NULL, NULL, now())
                   ON CONFLICT (youtube_url) DO UPDATE SET
                     candidates = EXCLUDED.candidates,
                     candidates_at = now(),
                     selected_index = NULL,
                     detail = NULL,
                     updated_at = now()""",
                (source_id, youtube_url, ideas_jsonb)
            )

            conn.commit()
        return {"ok": True, "youtube_url": youtube_url, "count": len(ideas_list)}
    except Exception as e:
        conn.rollback()
        return {"error": f"database error: {e}"}
    finally:
        conn.close()


@server.tool()
def save_idea_detail(youtube_url: str, detail_json: str) -> dict:
    """
    IDEA FLOW STEP 2 (final). Call this after expanding the selected idea to persist the full production package. This is the final save for the idea generator flow.

    Save expanded idea detail to the source_ideas table.

    Args:
        youtube_url: the YouTube URL to associate with the detail
        detail_json: JSON string or dict with {naskah, edit_cues, caption, hashtags, ...}. Must be a non-empty object.

    Returns:
        {"ok": true, "youtube_url": ...} on success
        {"error": "..."} on failure (invalid URL, bad JSON, no candidates saved yet)
    """
    # Validate URL
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url"}

    # Parse detail_json (accept string or dict)
    if isinstance(detail_json, str):
        try:
            detail_dict = json.loads(detail_json)
        except (json.JSONDecodeError, ValueError):
            return {"error": "detail_json is not valid JSON"}
    elif isinstance(detail_json, dict):
        detail_dict = detail_json
    else:
        return {"error": "detail_json must be a JSON string or dict"}

    # Require a non-empty object
    if not isinstance(detail_dict, dict) or not detail_dict:
        return {"error": "detail_json must be a non-empty object"}

    # DB write: UPDATE source_ideas
    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured"}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}"}

    try:
        with conn.cursor() as cur:
            # Wrap detail as JSONB
            detail_jsonb = Jsonb(detail_dict)

            # UPDATE source_ideas — fail if no row (candidates must be saved first)
            cur.execute(
                """UPDATE source_ideas SET detail = %s, detail_at = now(), updated_at = now()
                   WHERE youtube_url = %s""",
                (detail_jsonb, youtube_url)
            )

            if cur.rowcount == 0:
                return {"error": "no idea candidates saved yet for this url — run save_ideas first"}

            conn.commit()
        return {"ok": True, "youtube_url": youtube_url}
    except Exception as e:
        conn.rollback()
        return {"error": f"database error: {e}"}
    finally:
        conn.close()


@server.tool()
def get_clips(youtube_url: str) -> dict:
    """
    STORYBOARD FLOW STEP 1. Use this to fetch the local video clip files (seg_NN.mp4) for a decomposed video. This is the FIRST tool to call when building a Gemini storyboard.

    Get decomposed video clips (segments) for a source by youtube_url.

    Convenience wrapper: resolves source_id from youtube_url, then returns all video_segments.

    Args:
        youtube_url: the YouTube URL to look up

    Returns:
        {"youtube_url": ..., "source_id": ..., "clips": [...], "count": N}
        or {"error": "clips not ready yet — the pipeline is still preparing them; wait and call get_clips again"}
    """
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url"}

    if not DATABASE_URL:
        return {"error": "DATABASE_URL not configured"}

    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception as e:
        return {"error": f"database connection failed: {e}"}

    try:
        with conn.cursor() as cur:
            # Resolve source_id from youtube_url
            cur.execute("SELECT id FROM sources WHERE youtube_url=%s", (youtube_url,))
            source_row = cur.fetchone()
            if not source_row:
                return {"error": "clips not ready yet — the pipeline is still preparing them; wait and call get_clips again"}

            source_id = source_row[0]

            # Get all segments for this source
            cur.execute(
                "SELECT clip_index, start_sec, end_sec, credit_handle, segment_path FROM video_segments "
                "WHERE source_id=%s ORDER BY clip_index ASC",
                (source_id,)
            )
            cols = [c.name for c in cur.description] if cur.description else []
            rows = cur.fetchall()
            clips = [_segment_row_to_dict(row, cols) for row in rows]

            # Signal that Gemini has started working: flip status processing → working
            # (not if already analyzed). The dashboard's storyboard-status poll reads this
            # so the "Menunggu Gemini" loading flips to "Gemini sedang bekerja" in real time.
            if clips:
                cur.execute(
                    "UPDATE sources SET status='working' WHERE id=%s AND status <> 'analyzed'",
                    (source_id,)
                )
                conn.commit()

        return {
            "youtube_url": youtube_url,
            "source_id": source_id,
            "clips": clips,
            "count": len(clips)
        }
    except Exception as e:
        return {"error": f"query failed: {e}"}
    finally:
        conn.close()


def _suno_audio_path(youtube_url: str) -> str:
    """
    Compute a deterministic path for Suno audio clips keyed by youtube_url.

    IMPORTANT: This path computation MUST match the identical function in pipeline-api/main.py.
    If you modify this, update the main.py version as well so both can find the file.

    Args:
        youtube_url: YouTube URL (may contain query params)

    Returns:
        Absolute path: <repo_root>/output/suno_audio/<sha1_hash>.mp3
    """
    # Normalize URL by removing trailing whitespace
    normalized = youtube_url.strip()
    # Create SHA1 hash of the URL (includes params, so different clips get different files)
    url_hash = hashlib.sha1(normalized.encode()).hexdigest()
    # Return deterministic path: output/suno_audio/<hash>.mp3
    suno_dir = REPO_ROOT / "output" / "suno_audio"
    return str(suno_dir / f"{url_hash}.mp3")


@server.tool()
def get_audio_for_suno(youtube_url: str) -> dict:
    """
    SUNO FLOW STEP 1. Use this to fetch the clipped audio file for Suno music generation.

    Get the local audio file that was prepared for Suno music creation (already clipped to the specified time range).

    Args:
        youtube_url: the YouTube URL to look up (must match the url passed to /analyze/gemini-brief)

    Returns:
        {"youtube_url": ..., "audio_path": <abs path>, "exists": true}
        or {"error": "audio not ready yet — reelbot is still clipping it; wait and call get_audio_for_suno again"}
    """
    if not _valid_url(youtube_url):
        return {"error": "invalid youtube_url"}

    # Compute the deterministic path where the audio should be
    audio_path = _suno_audio_path(youtube_url)

    # Check if the audio file exists and is non-empty
    try:
        audio_file = Path(audio_path)
        if not audio_file.exists():
            return {"error": "audio not ready yet — reelbot is still clipping it; wait and call get_audio_for_suno again"}

        # Check file size to ensure it's not empty/truncated
        file_size = audio_file.stat().st_size
        if file_size == 0:
            return {"error": "audio not ready yet — reelbot is still clipping it; wait and call get_audio_for_suno again"}

        return {
            "youtube_url": youtube_url,
            "audio_path": str(audio_path),
            "exists": True,
            "file_size_bytes": file_size
        }
    except Exception as e:
        return {"error": f"failed to check audio file: {e}"}


# ── Keywords (Google Ads Keyword Planner) ──────────────────────────────────

@server.tool()
def keyword_ideas(
    seeds: list,
    geo: str = "ID",
    lang: str = "id"
) -> dict:
    """
    Generate keyword ideas from seed terms via Google Ads API.

    Calls the pipeline API /keywords/ideas endpoint, which in turn uses
    Google Ads KeywordPlanIdeaService to find related keywords.

    Args:
        seeds: list of seed keywords (e.g. ["video editing", "adobe premiere"])
        geo: geo code (default "ID" = Indonesia; also supports "US")
        lang: language code (default "id" = Indonesian; also supports "en")

    Returns:
        {"keywords": [{"keyword", "avg_monthly_searches", "competition", "score", ...}, ...]}
        or {"error": "..."} if API call fails or is not configured
    """
    if not PIPELINE_API_URL:
        return {"error": "PIPELINE_API_URL not configured"}

    if not seeds or not isinstance(seeds, list):
        return {"error": "seeds must be a non-empty list of strings"}

    # Call the pipeline API
    try:
        response = httpx.post(
            f"{PIPELINE_API_URL}/keywords/ideas",
            json={"seeds": seeds, "geo": geo, "lang": lang},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"keyword_ideas API call failed: {e}"}


@server.tool()
def query_keywords(
    niche: str = None,
    source: str = None,
    min_volume: int = None,
    region: str = None,
    limit: int = 50
) -> dict:
    """
    Query keywords from the database.

    Filters by niche, source, minimum search volume, and region.
    Returns results ordered by composite score (highest first).

    Args:
        niche: filter by niche slug (optional, e.g. "restoration")
        source: filter by source ("google_ads" or "youtube_suggest")
        min_volume: minimum average monthly searches (optional)
        region: filter by region code (optional, e.g. "ID:id", "US:en")
        limit: max results (default 50, clamped to 1-100)

    Returns:
        {"keywords": [{"keyword", "avg_monthly_searches", "competition", "score", ...}, ...]}
        or {"error": "..."} if query fails
    """
    if not PIPELINE_API_URL:
        return {"error": "PIPELINE_API_URL not configured"}

    params = {
        "limit": _clamp_limit(limit),
    }
    if niche:
        params["niche"] = niche
    if source:
        params["source"] = source
    if min_volume is not None:
        params["min_volume"] = int(min_volume)
    if region:
        params["region"] = region

    try:
        response = httpx.get(
            f"{PIPELINE_API_URL}/keywords",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"query_keywords API call failed: {e}"}


# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    server.run()
