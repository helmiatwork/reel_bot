"""
claude_bridge.py — Host-side HTTP bridge between Docker containers and the `claude` CLI.

HOW TO RUN (on the host machine):
    python3 scripts/claude_bridge.py

ENV VARS:
    CLAUDE_BRIDGE_PORT   Port to listen on (default: 9999). Binds 127.0.0.1 only.
    CLAUDE_BIN           Path to the claude binary
                         (default: /Users/ichigo/.nodenv/versions/24.14.1/bin/claude)
    ANALYZE_FRAME_DIR    Host directory where frame images live
                         (default: /Users/ichigo/Documents/repo/helmi/reelbot/analyze-frames)

IMPORTANT: This script MUST run on the HOST (not inside Docker). It uses the host's
logged-in `claude` CLI which authenticates via Claude Team plan subscription.
ANTHROPIC_API_KEY is intentionally NOT injected — subscription auth is on the host env.

ENDPOINTS:
    POST /run    — Execute a claude -p prompt, optionally with frame images.
    GET  /health — Liveness check.

SECURITY:
    - Listens on 127.0.0.1 only; Docker containers reach it via host.docker.internal.
    - Frame filenames are validated to be basename-only (no / or .. allowed).
    - subprocess is called with an argv list — shell=False always.
"""

import http.server
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

PORT = int(os.environ.get("CLAUDE_BRIDGE_PORT", 9999))
CLAUDE_BIN = os.environ.get(
    "CLAUDE_BIN",
    "/Users/ichigo/.nodenv/versions/24.14.1/bin/claude",
)
FRAME_DIR = Path(
    os.environ.get(
        "ANALYZE_FRAME_DIR",
        "/Users/ichigo/Documents/repo/helmi/reelbot/analyze-frames",
    )
)
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TIMEOUT = 180

logging.basicConfig(
    level=logging.INFO,
    format="[bridge] %(levelname)s %(message)s",
)
log = logging.getLogger("bridge")

# ── Rate-limit signal detection ───────────────────────────────────────────────

_RATE_LIMIT_PHRASES = (
    "usage limit",
    "rate limit",
    "ratelimit",
    "too many requests",
    "overloaded",
)


def _is_rate_limit(text: str) -> bool:
    """Return True if the text suggests a quota/rate-limit error from claude."""
    lower = text.lower()
    return any(p in lower for p in _RATE_LIMIT_PHRASES)


# ── Frame path resolution ─────────────────────────────────────────────────────

import re as _re

_SAFE_SUBDIR_RE = _re.compile(r'^[A-Za-z0-9_-]+$')


def _validate_subdir(subdir: str) -> bool:
    """
    Return True iff subdir is a safe single path component.
    Rejects anything containing '/', '\\', '..', or starting with '.'.
    Allows only [A-Za-z0-9_-]+.
    """
    if not subdir:
        return False
    if "/" in subdir or "\\" in subdir or ".." in subdir or subdir.startswith("."):
        return False
    return bool(_SAFE_SUBDIR_RE.match(subdir))


def _resolve_frames(frame_names: list, subdir: str = None) -> list:
    """
    Given a list of bare filenames, resolve each to an absolute path under
    FRAME_DIR (or FRAME_DIR/<subdir> when subdir is provided).

    Security guards:
    - subdir must be a single safe path component ([A-Za-z0-9_-]+); invalid
      subdir causes an empty list to be returned immediately (treated as
      no-frames / 400-style error).
    - Frame names must be basename-only — any name containing '/' or '..'
      is rejected outright (path traversal guard).

    Only files that actually exist on disk are included.
    Returns a list of absolute path strings.
    """
    # Validate and resolve the base directory
    if subdir is not None:
        if not _validate_subdir(subdir):
            log.warning("rejected invalid subdir: %r", subdir)
            return []
        base_dir = FRAME_DIR / subdir
    else:
        base_dir = FRAME_DIR

    resolved = []
    for name in frame_names or []:
        # Security: basename only — reject anything that looks like a path
        if "/" in name or ".." in name:
            log.warning("rejected frame name with traversal attempt: %r", name)
            continue
        abs_path = base_dir / name
        if abs_path.exists():
            resolved.append(str(abs_path))
        else:
            log.warning("frame not found, skipping: %s", abs_path)
    return resolved


# ── Claude runner ─────────────────────────────────────────────────────────────

def _run_claude(prompt: str, frame_paths: list, model: str, timeout_s: int) -> dict:
    """
    Run `claude -p <final_prompt> --model <model> --output-format json`
    as a subprocess (argv list, never shell=True).

    The final prompt appends resolved frame paths so claude's Read tool
    can ingest them as vision input.

    Returns a dict:
        {ok: bool, result: str, raw_usage: dict, cost_usd: float, model: str}
    or on failure:
        {ok: false, error: str, error_type: str}   (error_type="rate_limit" when detected)
    """
    # Build final prompt: append frame image paths so claude reads them
    final_prompt = prompt
    if frame_paths:
        final_prompt += "\n\nGambar untuk dianalisa:\n" + "\n".join(frame_paths)

    argv = [
        CLAUDE_BIN,
        "-p", final_prompt,
        "--model", model,
        # Isolate from the host user's Claude Code config so analysis output is
        # never polluted by interactive hooks (grammar-check, caveman, persona).
        # disableAllHooks kills all hook events; OAuth subscription auth still
        # works (unlike --bare, which breaks auth). exclude-dynamic trims the
        # per-machine cwd/env/memory/git sections to cut token overhead.
        "--settings", '{"disableAllHooks":true}',
        "--exclude-dynamic-system-prompt-sections",
        "--output-format", "json",
    ]

    # Use a clean temp dir as cwd to minimize context noise
    with tempfile.TemporaryDirectory(prefix="bridge_run_") as cwd:
        log.info("running claude model=%s frames=%d timeout=%ds",
                 model, len(frame_paths), timeout_s)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=cwd,
                # Inherit host env; do NOT override ANTHROPIC_API_KEY —
                # subscription auth depends on whatever the host session has.
            )
        except subprocess.TimeoutExpired:
            log.error("claude timed out after %ds", timeout_s)
            return {"ok": False, "error": f"claude timed out after {timeout_s}s",
                    "error_type": "timeout"}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    # Rate-limit detection (check both streams)
    combined = stdout + stderr
    if _is_rate_limit(combined):
        log.warning("rate limit detected in claude output")
        return {
            "ok": False,
            "error": "Claude usage/rate limit reached",
            "error_type": "rate_limit",
            "raw_stderr": stderr[:500],
        }

    if proc.returncode != 0:
        log.error("claude exited %d: %s", proc.returncode, stderr[:300])
        return {
            "ok": False,
            "error": f"claude exited {proc.returncode}: {stderr[:300]}",
            "error_type": "claude_error",
        }

    # Parse JSON output from claude --output-format json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        log.error("could not parse claude output as JSON: %s", exc)
        return {"ok": False, "error": f"JSON parse error: {exc}", "error_type": "parse_error"}

    if data.get("is_error"):
        log.error("claude returned is_error=true: %s", data.get("result", "")[:200])
        return {
            "ok": False,
            "error": data.get("result", "claude returned is_error=true"),
            "error_type": "claude_error",
        }

    return {
        "ok": True,
        "result": data.get("result", ""),
        "raw_usage": data.get("usage", {}),
        "cost_usd": data.get("total_cost_usd"),
        "model": model,
    }


# ── HTTP handler ──────────────────────────────────────────────────────────────

class BridgeHandler(http.server.BaseHTTPRequestHandler):
    """Minimal stdlib HTTP handler — POST /run and GET /health only."""

    def log_message(self, fmt, *args):  # silence default per-request logs
        log.debug(fmt, *args)

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True})
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return

        prompt = req.get("prompt", "").strip()
        if not prompt:
            self._send_json(400, {"ok": False, "error": "prompt is required"})
            return

        frames = req.get("frames") or []
        model = req.get("model") or DEFAULT_MODEL
        timeout_s = int(req.get("timeout_s") or DEFAULT_TIMEOUT)

        # Optional subdir: validated strictly inside _resolve_frames.
        # An invalid subdir (traversal attempt, dotfile, etc.) causes
        # _resolve_frames to return [] — the run proceeds with no frames,
        # matching the 400-style defensive behavior documented in the spec.
        subdir = req.get("subdir") or None
        if subdir is not None and not isinstance(subdir, str):
            self._send_json(400, {"ok": False, "error": "subdir must be a string"})
            return
        if subdir is not None and not _validate_subdir(subdir):
            self._send_json(400, {"ok": False, "error": "subdir must be a single safe path component ([A-Za-z0-9_-]+)"})
            return

        frame_paths = _resolve_frames(frames, subdir=subdir)
        result = _run_claude(prompt, frame_paths, model, timeout_s)

        status_code = 200 if result.get("ok") else 502
        if result.get("error_type") == "rate_limit":
            status_code = 429
        self._send_json(status_code, result)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    bind_addr = "127.0.0.1"
    server = http.server.HTTPServer((bind_addr, PORT), BridgeHandler)
    log.info("claude_bridge listening on %s:%d", bind_addr, PORT)
    log.info("claude binary: %s", CLAUDE_BIN)
    log.info("frame dir:     %s", FRAME_DIR)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")


if __name__ == "__main__":
    main()
