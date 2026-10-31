"""Production package: one ZIP per item with the blueprint (readable + JSON), thumbnail prompts, upload text and audio."""
import io
import json
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter()


def _lines(v, indent=0) -> list[str]:
    """Generic readable rendering for leftovers: dicts become '**Key**: value' lines, lists become bullets."""
    pad = "  " * indent
    if isinstance(v, dict):
        out = []
        for k, x in v.items():
            if isinstance(x, (dict, list)) and x:
                out += [f"{pad}- **{k}**:"] + _lines(x, indent + 1)
            elif x not in (None, "", [], {}):
                out.append(f"{pad}- **{k}**: {x}")
        return out
    if isinstance(v, list):
        out = []
        for x in v:
            if isinstance(x, (dict, list)):
                out += _lines(x, indent)
            elif x not in (None, ""):
                out.append(f"{pad}- {x}")
        return out
    return [f"{pad}{v}"] if v not in (None, "") else []


def _cell(v) -> str:
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def _table(headers, rows) -> list[str]:
    if not rows:
        return []
    return ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)] + \
        ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]


def _numbered(items) -> list[str]:
    return [f"{i}. {x}" for i, x in enumerate([x for x in items if x not in (None, "")], 1)] if isinstance(items, list) else []


def _dicts(v) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _rest(d, known) -> list[str]:
    return _lines({k: x for k, x in d.items() if k not in known}) if isinstance(d, dict) else _lines(d)


def _md_atm(a):
    if not isinstance(a, dict):
        return _lines(a), []
    out = []
    for key, label in (("tiru", "Tiru (struktur yang ditiru)"), ("modifikasi", "Modifikasi (sudut baru)"),
                       ("checklist_orisinalitas", "Checklist orisinalitas")):
        if _numbered(a.get(key)):
            out += [f"**{label}**", ""] + _numbered(a[key]) + [""]
    return out, _rest(a, ("tiru", "modifikasi", "checklist_orisinalitas"))


def _md_hook(h):
    if not isinstance(h, dict):
        return _lines(h), []
    out = [f"**Kalimat hook:** {h['line']}", ""] if h.get("line") else []
    out += [f"**Visual pembuka:** {h['visual']}", ""] if h.get("visual") else []
    return out, _rest(h, ("line", "visual"))


def _md_narration(n):
    if not isinstance(n, dict):
        return _lines(n), []
    out = [f"**Gaya bicara:** {n['style']}", ""] if n.get("style") else []
    out += _table(["Waktu", "Kalimat VO", "Catatan"], [(b.get("t"), b.get("vo"), b.get("note")) for b in _dicts(n.get("beats"))])
    return out, _rest(n, ("style", "beats"))


_SHOT_KEYS = ("n", "duration_s", "record", "framing", "camera", "on_screen_text", "transition")


def _md_shots(shots):
    if not isinstance(shots, list):
        return _lines(shots), []
    rows = [(s.get("n", i), f"{s['duration_s']} dtk" if s.get("duration_s") else "", s.get("record"),
             " / ".join(str(x) for x in (s.get("framing"), s.get("camera")) if x), s.get("on_screen_text"), s.get("transition"))
            for i, s in enumerate(_dicts(shots), 1)]
    out = _table(["#", "Durasi", "Yang direkam", "Framing / kamera", "Teks layar", "Transisi"], rows)
    return out, [line for s in _dicts(shots) for line in _rest(s, _SHOT_KEYS)]


def _md_audio(a):
    if not isinstance(a, dict):
        return _lines(a), []
    out = []
    if a.get("bgm_reason") or a.get("bgm_song_id"):
        bgm = a.get("bgm_name") or (f"lagu #{a['bgm_song_id']}" if a.get("bgm_song_id") else "")
        out += [f"**BGM:** {bgm}" + (f" - {a['bgm_reason']}" if a.get("bgm_reason") else ""), ""]
    if _dicts(a.get("sfx")):
        out += ["**SFX**", ""] + _table(["Momen", "SFX"], [(x.get("moment"), x.get("sfx")) for x in _dicts(a["sfx"])]) + [""]
    return out, _rest(a, ("bgm_song_id", "bgm_name", "bgm_reason", "sfx"))


def _md_assets(a):
    if not isinstance(a, dict):
        return _lines(a), []
    have = [x.get("label") or x.get("song_id") if isinstance(x, dict) else x for x in (a.get("have") or [])]
    out = []
    for label, items in (("Sudah punya", have), ("Harus disiapkan", a.get("need") or [])):
        items = [x for x in items if x not in (None, "")]
        if items:
            out += [f"**{label}**", ""] + [f"- [ ] {x}" for x in items] + [""]
    return out, _rest(a, ("have", "need"))


def _md_thumbnail(t):
    if not isinstance(t, dict):
        return _lines(t), []
    out = []
    for i, c in enumerate(_dicts(t.get("concepts")), 1):
        out += [f"### Konsep {i}", "", f"- **Prompt gambar:** {c.get('prompt', '')}",
                f"- **Teks overlay:** {c.get('overlay_text', '')}", f"- **Alasan CTR:** {c.get('why_ctr', '')}", ""]
    cf = t.get("cover_frame")
    if isinstance(cf, dict) and cf:
        out += ["### Cover frame (di dalam aplikasi)", "", f"- **Shot nomor:** {cf.get('shot', '')}",
                f"- **Momen:** {cf.get('moment', '')}", f"- **Teks overlay:** {cf.get('overlay_text', '')}", ""]
    if _numbered(t.get("rules")):
        out += ["**Aturan thumbnail**", ""] + _numbered(t["rules"]) + [""]
    return out, _rest(t, ("concepts", "cover_frame", "rules"))


def _md_upload(u):
    if not isinstance(u, dict):
        return _lines(u), []
    out = []
    for key, label in (("description", "Deskripsi"), ("pinned_comment", "Komentar pin"), ("playlist", "Playlist"), ("end_screen", "End screen")):
        if u.get(key):
            out += [f"**{label}:** {u[key]}", ""]
    if u.get("tags"):
        out += [f"**Tag:** {', '.join(map(str, u['tags']))}", ""]
    if u.get("hashtags"):
        out += [f"**Hashtag:** {' '.join(map(str, u['hashtags']))}", ""]
    if _numbered(u.get("checklist")):
        out += ["**Checklist upload**", ""] + [f"- [ ] {x}" for x in u["checklist"] if x] + [""]
    return out, _rest(u, ("description", "pinned_comment", "playlist", "end_screen", "tags", "hashtags", "checklist"))


def _md_numbered(v):
    return (_numbered(v), []) if isinstance(v, list) else (_lines(v), [])


_SECTIONS = (
    ("atm", "ATM: Tiru, Modifikasi, Orisinalitas", _md_atm),
    ("titles", "Pilihan Judul", _md_numbered), ("hook", "Hook", _md_hook),
    ("narration", "Narasi per Beat", _md_narration), ("shots", "Daftar Shot", _md_shots),
    ("audio", "Audio", _md_audio), ("assets", "Aset", _md_assets),
    ("capcut_steps", "Langkah Edit CapCut", _md_numbered), ("thumbnail", "Thumbnail", _md_thumbnail),
    ("upload", "Kit Upload", _md_upload), ("recording_tips", "Tips Rekaman", lambda v: ([f"- {x}" for x in v if x] if isinstance(v, list) else _lines(v), [])),
)


def blueprint_markdown(title: str, bp: dict) -> str:
    parts, extra = [f"# Blueprint: {title}\n"], []
    for key, label, render in _SECTIONS:
        if bp.get(key):
            body, leftover = render(bp[key])
            if body:
                parts.append(f"## {label}\n\n" + "\n".join(body).rstrip() + "\n")
            if leftover:
                extra += [f"**{label}**", ""] + leftover + [""]
    known = {k for k, _, _ in _SECTIONS}
    other = {k: v for k, v in bp.items() if k not in known}
    extra += _lines(other) if other else []
    if extra:
        parts.append("## Lainnya\n\n" + "\n".join(extra).rstrip() + "\n")
    return "\n".join(parts)


def thumbnail_prompts(bp: dict) -> str:
    concepts = (bp.get("thumbnail") or {}).get("concepts") or []
    return "\n\n".join(f"Konsep {i}\nPrompt: {c.get('prompt', '')}\nTeks overlay: {c.get('overlay_text', '')}\n"
                       f"Alasan CTR: {c.get('why_ctr', '')}" for i, c in enumerate(concepts, 1) if isinstance(c, dict))


def upload_text(bp: dict) -> str:
    up = bp.get("upload") or {}
    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(bp.get("titles") or [], 1))
    return (f"PILIHAN JUDUL\n{titles}\n\nDESKRIPSI\n{up.get('description', '')}\n\n"
            f"TAG\n{', '.join(map(str, up.get('tags') or []))}\n\n"
            f"HASHTAG\n{' '.join(map(str, up.get('hashtags') or []))}\n\nKOMENTAR PIN\n{up.get('pinned_comment', '')}\n")


def _text(v) -> str:
    """Untrusted value as plain text: strings and numbers only, anything else becomes ''."""
    return str(v) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _flat(d) -> dict:
    return {str(k): _text(x) for k, x in d.items() if _text(x)} if isinstance(d, dict) else {}


def _rekam_data(title, bp: dict) -> dict:
    hook, narration, thumb, tips = bp.get("hook"), bp.get("narration"), bp.get("thumbnail"), bp.get("recording_tips")
    return {
        "title": _text(title),
        "hook": _text(hook.get("line") if isinstance(hook, dict) else hook),
        "tips": [t for t in map(_text, tips) if t] if isinstance(tips, list) else [],
        "shots": [_flat(s) for s in _dicts(bp.get("shots"))],
        "beats": [_flat(b) for b in _dicts(narration.get("beats"))] if isinstance(narration, dict) else [],
        "cover": _flat(thumb.get("cover_frame")) if isinstance(thumb, dict) else {},
    }


def _json_for_html(obj) -> str:
    """JSON that cannot close the <script> block or start a tag; JS parses it back to the same values."""
    s = json.dumps(obj, ensure_ascii=False)
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026") \
        .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


_REKAM_PAGE = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mode Rekam</title>
<style>
*{box-sizing:border-box}
html,body{margin:0;background:#000;color:#fff;font:18px/1.45 system-ui,-apple-system,sans-serif}
#screen{max-width:640px;margin:0 auto;padding:16px 16px 104px;overflow-wrap:anywhere}
h1{font-size:30px;margin:8px 0 16px;line-height:1.25}
h2{font-size:24px;margin:24px 0 8px;color:#ffd60a}
.hook{font-size:28px;font-weight:700;margin:12px 0}
.meta{font-size:20px;font-weight:700;color:#ffd60a;margin:4px 0}
.narasi{font-size:32px;font-weight:700;line-height:1.35;margin:16px 0}
.kv{font-size:20px;color:#e6e6e6;margin:6px 0}
.ok{color:#7CFC8A;font-weight:700}
.check{display:flex;align-items:center;gap:12px;min-height:48px;font-size:22px;font-weight:700;background:#1c1c1c;border-radius:10px;padding:10px 14px;margin:20px 0}
.check input{width:28px;height:28px;flex:none}
.nav{position:fixed;left:0;right:0;bottom:0;display:flex;gap:8px;padding:8px;background:#000;border-top:1px solid #333}
.nav button{flex:1;min-height:56px;font-size:22px;font-weight:700;border:0;border-radius:10px;background:#ffd60a;color:#000}
.nav button:disabled{background:#333;color:#999}
</style>
</head>
<body>
<main id="screen"></main>
<nav class="nav"><button id="prev" type="button">Sebelumnya</button><button id="next" type="button">Berikutnya</button></nav>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("data").textContent);
  var shots = data.shots, beats = data.beats;
  // beat i narrates shot i only when the counts match; otherwise beats live on the start screen
  var matched = beats.length === shots.length;
  var total = shots.length, last = total + 1; // 0 = start, 1..total = shots, last = summary
  var key = "rekam|" + data.title + "|";
  var done = shots.map(function (_, i) {
    try { return localStorage.getItem(key + i) === "1"; } catch (e) { return false; }
  });
  var screen = document.getElementById("screen");
  var prev = document.getElementById("prev"), next = document.getElementById("next");
  var pos = 0;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function setDone(i, v) {
    done[i] = v;
    try { localStorage.setItem(key + i, v ? "1" : "0"); } catch (e) {}
  }
  function beatNode(b) {
    var box = el("div", "");
    if (b.t) box.appendChild(el("div", "meta", b.t));
    box.appendChild(el("div", "narasi", b.vo || ""));
    if (b.note) box.appendChild(el("div", "kv", "Catatan: " + b.note));
    return box;
  }
  function startScreen() {
    screen.appendChild(el("h1", "", data.title || "Mode Rekam"));
    if (data.hook) screen.appendChild(el("p", "hook", data.hook));
    screen.appendChild(el("div", "meta", "Total shot: " + total));
    if (data.tips.length) {
      screen.appendChild(el("h2", "", "Tips rekaman"));
      var ul = el("ul", "kv");
      data.tips.forEach(function (t) { ul.appendChild(el("li", "", t)); });
      screen.appendChild(ul);
    }
    if (!matched && beats.length) {
      screen.appendChild(el("h2", "", "Narasi per beat"));
      beats.forEach(function (b) { screen.appendChild(beatNode(b)); });
    }
  }
  function shotScreen(i) {
    var s = shots[i];
    screen.appendChild(el("div", "meta", "Shot " + (i + 1) + " / " + total));
    if (s.duration_s) screen.appendChild(el("div", "meta", s.duration_s + " dtk"));
    if (matched) screen.appendChild(beatNode(beats[i]));
    Object.keys(s).forEach(function (k) {
      if (k !== "n" && k !== "duration_s") screen.appendChild(el("div", "kv", k + ": " + s[k]));
    });
    var label = el("label", "check"), box = el("input");
    box.type = "checkbox";
    box.checked = done[i];
    box.addEventListener("change", function () { setDone(i, box.checked); });
    label.appendChild(box);
    label.appendChild(el("span", "", "Sudah direkam"));
    screen.appendChild(label);
  }
  function summaryScreen() {
    var n = done.filter(Boolean).length;
    screen.appendChild(el("h1", "", "Ringkasan: " + n + " dari " + total + " shot sudah direkam"));
    shots.forEach(function (_, i) {
      screen.appendChild(el("div", done[i] ? "kv ok" : "kv", "Shot " + (i + 1) + ": " + (done[i] ? "Sudah direkam" : "Belum")));
    });
    var cover = data.cover, keys = Object.keys(cover);
    if (keys.length) {
      screen.appendChild(el("h2", "", "Cover frame (di dalam aplikasi)"));
      keys.forEach(function (k) { screen.appendChild(el("div", "kv", k + ": " + cover[k])); });
    }
  }
  function render() {
    while (screen.firstChild) screen.removeChild(screen.firstChild);
    if (pos === 0) startScreen();
    else if (pos === last) summaryScreen();
    else shotScreen(pos - 1);
    prev.disabled = pos === 0;
    next.disabled = pos === last;
    window.scrollTo(0, 0);
  }
  function go(d) {
    var np = Math.min(last, Math.max(0, pos + d));
    if (np !== pos) { pos = np; render(); }
  }
  prev.addEventListener("click", function () { go(-1); });
  next.addEventListener("click", function () { go(1); });
  var sx = null;
  document.addEventListener("touchstart", function (e) {
    sx = e.touches.length ? e.touches[0].clientX : null;
  }, { passive: true });
  document.addEventListener("touchend", function (e) {
    if (sx === null || !e.changedTouches.length) return;
    var dx = e.changedTouches[0].clientX - sx;
    sx = null;
    if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
  }, { passive: true });
  document.title = data.title ? "Mode Rekam - " + data.title : "Mode Rekam";
  render();
})();
</script>
</body>
</html>
"""


def rekam_html(title: str, bp: dict) -> str:
    """Offline phone page: one screen per shot. Blueprint text is untrusted, so it only reaches the page as JSON data."""
    return _REKAM_PAGE.replace("__DATA__", _json_for_html(_rekam_data(title, bp)))


def _inside_data(path_str, data_dir: Path):
    """Resolved Path when it is an existing file under data/, else None."""
    if not path_str:
        return None
    p = Path(path_str).resolve()
    return p if p.is_file() and p.is_relative_to(data_dir) else None


@router.get("/items/{item_id}/package")
def item_package(item_id: int):
    import main
    data_dir = (Path(main._REPO_ROOT) / "data").resolve()
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT title, blueprint FROM content_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="item not found")
            title, bp = row
            if not isinstance(bp, dict) or not bp:
                raise HTTPException(status_code=409, detail="Blueprint belum dibuat")
            # voiceover files live in data/songs/voiceover/<item_id>/ and are tagged item:<item_id>
            cur.execute("SELECT audio_path FROM songs WHERE kind = 'voiceover' AND audio_path LIKE %s ORDER BY id",
                        (f"%/voiceover/{item_id}/%",))
            audio = [("voiceover/" + Path(r[0]).name, r[0]) for r in cur.fetchall()]
            bgm_id = (bp.get("audio") or {}).get("bgm_song_id")
            if isinstance(bgm_id, int) and not isinstance(bgm_id, bool):
                cur.execute("SELECT audio_path FROM songs WHERE id = %s", (bgm_id,))
                r = cur.fetchone()
                if r and r[0]:
                    audio.append(("bgm/" + Path(r[0]).name, r[0]))
    finally:
        conn.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("blueprint.md", blueprint_markdown(title, bp))
        z.writestr("rekam.html", rekam_html(title, bp))
        z.writestr("blueprint.json", json.dumps(bp, ensure_ascii=False, indent=2))
        z.writestr("thumbnail_prompts.txt", thumbnail_prompts(bp))
        z.writestr("upload.txt", upload_text(bp))
        for arcname, path_str in audio:
            p = _inside_data(path_str, data_dir)
            if p:
                z.write(p, arcname)
            else:
                print(f"[atm] package {item_id}: skipped audio outside data/ or missing")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:40] or "konten"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="atm-{item_id}-{slug}.zip"'})
