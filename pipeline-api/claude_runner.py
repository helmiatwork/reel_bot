"""
claude_runner.py - run the `claude` CLI in-process.

run(payload) takes the JSON body the old bridge accepted on POST /run and returns the
dict it answered with: {ok, result, model, cost_usd, raw_usage} or
{ok: False, error, error_type?}. Validation failures return ok:False, they never raise.

ENV VARS:
    CLAUDE_MAX_CONCURRENT  Max `claude` subprocesses at once on this host, shared by pipeline-api and MCP processes (default 2, min 1);
                                  extra callers wait for a slot.
    CLAUDE_BIN                    Path to the claude binary (default: `claude` on PATH).
    ANALYZE_FRAME_DIR             Directory where frame images live.

The host's logged-in `claude` CLI authenticates via the subscription, so
ANTHROPIC_API_KEY is intentionally NOT injected.
Frame names are basename-only and subprocess uses an argv list (shell=False).
"""

import contextlib
import fcntl
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

# Cap on concurrent `claude` subprocesses; requests beyond it wait for a slot.
MAX_CONCURRENT = max(1, int(os.environ.get("CLAUDE_MAX_CONCURRENT", 2)))
_RUN_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT)
# Slot lock files shared by every process that imports this module (pipeline-api, each MCP server).
SLOT_DIR = Path(os.environ.get("CLAUDE_SLOT_DIR") or Path(__file__).resolve().parents[1] / "tmp" / "claude-slots")


@contextlib.contextmanager
def _host_slot():
    """Cross-process cap: hold one of MAX_CONCURRENT flock'd slot files until the run ends."""
    SLOT_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        for i in range(MAX_CONCURRENT):
            f = open(SLOT_DIR / f"slot-{i}.lock", "w")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                continue
            try:
                yield
            finally:
                f.close()  # closing the fd releases the flock
            return
        time.sleep(0.2)
# PATH lookup first: a pinned nodenv path breaks on every node upgrade.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"
# .resolve() makes the dir absolute so resolved frame paths stay absolute even
# when ANALYZE_FRAME_DIR is passed as a relative path. claude runs in a clean
# temp cwd and reads frames via absolute path — a relative path would not resolve.
FRAME_DIR = Path(
    os.environ.get(
        "ANALYZE_FRAME_DIR",
        str(Path(__file__).resolve().parents[1] / "analyze-frames"),
    )
).resolve()
DEFAULT_MODEL = "claude-sonnet-5-5"
# Owner rule (2026-10-31): only the 5.5 generation, whatever a caller or .env asks for.
ALLOWED_MODELS = {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"}
# Owner rule (2026-10-31): Haiku runs at high effort, Sonnet at low (token saving),
# unless the caller asks for a specific effort.
DEFAULT_EFFORT = {"claude-haiku-5-5": "high", "claude-sonnet-5-5": "low"}
DEFAULT_TIMEOUT = 180

log = logging.getLogger("claude_runner")

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

_SAFE_SUBDIR_RE = re.compile(r'^[A-Za-z0-9_-]+$')


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

_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def _run_claude(prompt: str, frame_paths: list, model: str, timeout_s: int,
                effort: "str | None" = None) -> dict:
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

    # Prompts carry untrusted text (scraped titles, transcripts), so tools are
    # least-privilege: text-only jobs get no tools at all; frame jobs get Read
    # scoped to FRAME_DIR, and dontAsk denies anything else instead of hanging
    # on a permission prompt (no tty to approve).
    if frame_paths:
        tool_args = [
            "--tools", "Read",
            "--allowedTools", f"Read(/{FRAME_DIR}/**)",
            "--permission-mode", "dontAsk",
        ]
    else:
        tool_args = ["--tools", ""]
    # --tools only limits built-ins; without this the host's MCP servers and
    # claude.ai connectors (Gmail, Drive, …) load into every bridge job.
    tool_args.append("--strict-mcp-config")
    # Skip user/project settings: the host's allow rules ("Read", home in
    # additionalDirectories) would otherwise override the FRAME_DIR scope.
    tool_args += ["--setting-sources", ""]

    argv = [
        CLAUDE_BIN,
        "-p", final_prompt,
        "--model", model,
        *(["--effort", effort] if effort else []),
        *tool_args,
        # Isolate from the host user's Claude Code config so analysis output is
        # never polluted by interactive hooks (grammar-check, caveman, persona).
        # disableAllHooks kills all hook events; OAuth subscription auth still
        # works (unlike --bare, which breaks auth). exclude-dynamic trims the
        # per-machine cwd/env/memory/git sections to cut token overhead.
        "--settings", '{"disableAllHooks":true}',
        "--output-format", "json",
    ]

    # Use a clean temp dir as cwd to minimize context noise
    with tempfile.TemporaryDirectory(prefix="claude_run_") as cwd:
        log.info("running claude model=%s frames=%d timeout=%ds",
                 model, len(frame_paths), timeout_s)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=cwd,
                # Inherit pipeline-api's env (incl. .env) minus ANTHROPIC_*, so an API key, token or
                # base URL in .env never moves claude off the subscription login.
                env={k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")},
            )
        except subprocess.TimeoutExpired:
            log.error("claude timed out after %ds", timeout_s)
            return {"ok": False, "error": f"claude timed out after {timeout_s}s",
                    "error_type": "timeout"}
        except OSError as exc:  # e.g. FileNotFoundError when CLAUDE_BIN is missing
            log.error("could not start claude: %s", exc)
            return {"ok": False, "error": f"could not start claude: {exc}",
                    "error_type": "claude_error"}

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


# ── Entry point ───────────────────────────────────────────────────────────────

def run(payload: dict) -> dict:
    """Validate a /run-style payload and execute it; same result dict the old HTTP bridge returned."""
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt is required"}

    frames = payload.get("frames") or []
    model = payload.get("model") or DEFAULT_MODEL
    if model not in ALLOWED_MODELS:
        return {"ok": False, "error": "model must be one of " + ", ".join(sorted(ALLOWED_MODELS))}
    try:
        timeout_s = int(payload.get("timeout_s") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        return {"ok": False, "error": "timeout_s must be an integer"}
    effort = payload.get("effort") or DEFAULT_EFFORT.get(model)
    if effort is not None and effort not in _EFFORTS:
        return {"ok": False, "error": "effort must be one of " + ", ".join(sorted(_EFFORTS))}

    # Optional subdir: malformed is rejected here; frames missing under a valid subdir
    # are rejected below as frames_missing.
    subdir = payload.get("subdir") or None
    if subdir is not None and not isinstance(subdir, str):
        return {"ok": False, "error": "subdir must be a string"}
    if subdir is not None and not _validate_subdir(subdir):
        return {"ok": False, "error": "subdir must be a single safe path component ([A-Za-z0-9_-]+)"}

    frame_paths = _resolve_frames(frames, subdir=subdir)
    if frames and not frame_paths:
        # Never silently fall back to a text-only run: the caller expects vision.
        return {"ok": False, "error_type": "frames_missing",
                "error": "none of the requested frames exist"}
    with _RUN_SLOTS, _host_slot():  # only the claude subprocess waits for a slot
        return _run_claude(prompt, frame_paths, model, timeout_s, effort)
