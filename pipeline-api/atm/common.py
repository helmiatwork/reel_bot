"""Shared ATM helpers. Call main.py helpers lazily (`import main` inside functions) to avoid an import cycle."""
import datetime as _dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

STATUSES = ("idea", "blueprint", "shoot", "edit", "review", "ready", "scheduled", "posted", "monitored")
LEGACY_STAGE_MAP = {"script": "blueprint", "prep": "shoot"}

ATM_MODEL = os.getenv("ATM_MODEL", "claude-sonnet-5-5")
ATM_LIGHT_MODEL = os.getenv("ATM_LIGHT_MODEL", "claude-haiku-5-5")
# Passed to `claude -p --effort`; empty = the model's own default.
ATM_EFFORT = os.getenv("ATM_EFFORT", "")
ATM_LIGHT_EFFORT = os.getenv("ATM_LIGHT_EFFORT", "")
# Draft + post evaluation (A/B-tested: haiku at high effort matches sonnet there).
ATM_EVAL_MODEL = os.getenv("ATM_EVAL_MODEL", "claude-haiku-5-5")
ATM_EVAL_EFFORT = os.getenv("ATM_EVAL_EFFORT", "high")

def effort_for(model: str) -> str:
    return ATM_LIGHT_EFFORT if model == ATM_LIGHT_MODEL else ATM_EFFORT


def is_youtube_host(url: str) -> bool:
    """Exact host match: youtu.be, youtube.com or a *.youtube.com subdomain (not youtube.com.evil.tld)."""
    host = (urlparse(url).hostname or "").lower()
    return host in ("youtu.be", "youtube.com") or host.endswith(".youtube.com")


def ytdlp_bin() -> str:
    """yt-dlp beside the running interpreter (venv) first; a stale ~/.local/bin copy gets HTTP 429."""
    beside = Path(sys.executable).with_name("yt-dlp")
    return str(beside) if beside.exists() else (shutil.which("yt-dlp") or "yt-dlp")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def run_claude(prompt: str, *, agent: str, model: str = ATM_MODEL, frames: list | None = None,
               subdir: str | None = None, timeout_s: int = 300, effort: str | None = None) -> str | None:
    """Ask claude-bridge; returns the result text, or None on transport error / ok:false."""
    import main
    payload = {"prompt": prompt, "frames": frames or [], "model": model, "timeout_s": timeout_s}
    if subdir:
        payload["subdir"] = subdir
    effort = effort if effort is not None else effort_for(model)
    if effort:
        payload["effort"] = effort
    try:
        resp = httpx.post(
            f"{main.CLAUDE_BRIDGE_URL}/run", json=payload,
            timeout=httpx.Timeout(connect=10.0, read=float(timeout_s) + 10, write=10.0, pool=5.0),
        )
        data = resp.json()
    except Exception as exc:
        print(f"[atm] claude bridge unreachable ({agent}): {exc}")
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        print(f"[atm] claude bridge error ({agent}): {data.get('error') if isinstance(data, dict) else data}")
        return None
    main._log_api_usage(agent, data.get("model", model), data.get("raw_usage") or {}, data.get("cost_usd"))
    return data.get("result")


def parse_json(text: str | None) -> dict | None:
    """First top-level JSON object in text (``` fences stripped); None if absent or invalid."""
    if not text:
        return None
    m = _FENCE_RE.search(text)
    body = m.group(1) if m else text
    start = body.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(body[start:])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def item_row(cur_description, row) -> dict:
    """Serialize a content_items row; datetimes become ISO strings, `status` mirrors `stage`."""
    d = dict(zip([c.name for c in cur_description], row))
    for k, v in d.items():
        if isinstance(v, (_dt.datetime, _dt.date)):
            d[k] = v.isoformat()
    if "stage" in d:
        d["status"] = d["stage"]
    return d
