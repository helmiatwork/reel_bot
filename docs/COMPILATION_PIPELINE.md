# Compilation Reverse Pipeline — Design

**Status:** Draft for review (not yet built)
**Scope fit:** Reelbot = analyze + search + preparation only (the *brain*). This feature stays inside that scope — it decomposes, identifies, and finds sources. Editing/rendering the new compilation happens externally (CapCut / Opus Clip). See memory `reelbot-scope-analyze-only`.

## Vision

A viral Short is often a **compilation** of several separate source clips. Given such a Short, the user wants Reelbot to:

1. Break it into its individual clips (the distinct source videos 1, 2, 3, 4…).
2. Identify and **find the original full video** each clip came from.
3. Save all those originals as `sources`.

The payoff: the user can then **recreate the same style of compilation using fresh/original footage** — Reelbot hands them the raw ingredients, they assemble it in an editor.

Full loop:

```
compilation Short in
  → scene-cut (raw shots)
  → AI-group shots into distinct source clips (video 1/2/3/4)
  → per clip: read on-screen credit / reverse-search → find the ORIGINAL video
  → save originals as sources (+ segment metadata)
  → user recreates in CapCut/Opus Clip
```

## Pipeline stages

### Stage 1 — Ingest (reuse existing)
- Reuse `_download_source_video()` (main.py:2411) — the compilation is downloaded once and kept for the whole pipeline (currently the analyze flow already downloads for keyframes/audio).
- Reuse `analyze_claude` context: niche, tags, hook, structure for the compilation as a whole.

### Stage 2 — Scene-cut detection (new, cheap)
- Detect shot boundaries with **PySceneDetect** (content-aware, recommended for fast montages) or the ffmpeg `select='gt(scene,T)'` filter as a no-dep fallback.
- Output: ordered list of raw shots — `[{index, start_sec, end_sec}]`.
- Threshold tunable (default ~0.3). This is *mechanical* cut detection, not semantic.

### Stage 3 — AI grouping into distinct source clips (new, the hard part)
Raw shots ≠ source videos. A single source video inside the compilation may contain several internal cuts. Group consecutive shots that belong to the **same source clip**, and detect where a **new distinct video** begins.

- Sample one representative frame per shot, send to **claude-vision** with the ordered sequence.
- Boundary signals the model looks for:
  - Hard change in subject / location / people.
  - Change in quality / aspect ratio / resolution (different source).
  - **Change in on-screen `@handle` / username / watermark** ← strongest signal; compilations usually credit each clip.
  - Transition cards, on-screen counters ("1/2/3"), audio-track change.
- Output: grouped clips — `[{clip_index, start_sec, end_sec, shots:[...], credit_handle?, boundary_reason}]`.

**Honesty:** credited/cue-rich compilations group very accurately. Smooth uncredited montages are harder and may mis-group. Not 100%.

### Stage 4 — Find the original per clip (new; reliable vs best-effort)
This is the make-or-break stage. Two tiers:

**Tier A — Reliable (has an on-screen credit):**
- AI read the `@handle` from the clip (already captured in Stage 3).
- Look up that creator's uploads via `/youtube/channel/{channel_id}/uploads` (main.py:1703) or `/youtube/search` (main.py:1576) scoped to the handle.
- Match the clip to a specific upload (title/thumbnail/duration + a vision confirm on a frame).
- This works with tools Reelbot already has. **No new external dependency.**

**Tier B — Best-effort (no credit / smooth cut):**
- Reverse-image search on a keyframe via an external service (Google Vision *web detection* or SerpAPI) → candidate source posts/videos.
- Optional audio fingerprint (ACRCloud) if original audio is present.
- Fallback: AI describes the clip → keyword `/youtube/search` → "similar", not guaranteed the exact original.
- **Requires a paid external API + is not guaranteed** (TikTok/IG originals aren't always indexed).

Output per clip: `{status: found|best_effort|not_found, original_url?, confidence, method}`.

### Stage 5 — Persist
- Each found original → upsert into `sources` (dedup on `youtube_url UNIQUE`, already enforced).
- Segment metadata → new `video_segments` table (below).
- Optionally split the compilation into segment mp4s under `data/segments/<video_id>/seg_NN.mp4` (mirrors the existing `data/frames/` pattern) — **behind a flag** because of disk cost.

## Data model

New table, mirrors the `songs`/`sources` idiom:

```sql
CREATE TABLE IF NOT EXISTS video_segments (
    id             BIGSERIAL PRIMARY KEY,
    source_id      BIGINT REFERENCES sources(id),   -- the compilation
    clip_index     INTEGER,                          -- 1,2,3,4 (distinct source order)
    start_sec      NUMERIC(10,3),
    end_sec        NUMERIC(10,3),
    credit_handle  TEXT,                             -- @handle read from overlay, if any
    original_url   TEXT,                             -- resolved original, if found
    origin_status  TEXT,                             -- found | best_effort | not_found
    confidence     NUMERIC(4,3),
    segment_path   TEXT,                             -- data/segments/... if split saved
    created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS video_segments_source_idx ON video_segments (source_id, clip_index);
```

## API

- `POST /decompose` `{youtube_url, split_files?:bool, top_n_originals?:int}`
  → runs as a **background job** (run_id + poll), same pattern as `/pipeline/research` + `/pipeline/research/status/{run_id}` (main.py:1502).
- `GET /decompose/status/{run_id}` → `{status, current_stage, segments:[...]}`.
- `GET /sources/{id}/segments` → list segments for a compilation (feeds a dashboard drawer, like frames).

## Telegram trigger (SOUL)

New intent, distinct from analyze/discover:
- Bare compilation URL + phrase like *"pecah ini"* / *"cari source aslinya"* / *"decompose"* → decompose mode.
- Bot replies with: N clips found, each with credit handle (if any), original link (or best-effort/not-found), and a note that the user assembles the recreation in CapCut/Opus Clip.

## Reuse vs new

| Reused | New |
|--------|-----|
| `_download_source_video`, keyframe extraction | scene-cut (PySceneDetect/ffmpeg) |
| `analyze_claude` / claude-vision bridge | AI shot-grouping prompt |
| `/youtube/search`, `/youtube/channel/uploads` | original-finder (Tier A + B) |
| `sources` upsert, background-run pattern | `video_segments` table, `/decompose` endpoints |
| `data/frames/` storage idiom | `data/segments/` split files (flagged) |

## Cost & storage

- **Cheap:** download (once), scene-cut (ffmpeg/CPU).
- **Bounded AI:** 1 vision frame per shot (grouping) + Tier-A confirms. Cap shot count.
- **Paid/optional:** Tier-B reverse-search API — only when there is no credit.
- **Disk:** segment mp4s optional (flag). Keep metadata always; keep files only on request + add retention.

## Suggested phasing

- **Phase 1** — Stages 2–3 + `video_segments` + `/decompose` (scene-cut + AI-group + metadata). No original-finding yet. Immediately useful: "here are the N clips and their credits."
- **Phase 2** — Stage 4 Tier A (credit → channel lookup). Covers most real compilations with zero new deps.
- **Phase 3** — Stage 4 Tier B (reverse-search) + optional segment-file split. Only if Phase 2 isn't enough.

## Decisions (locked 2026-07-05)

1. **Trigger:** on-demand only (user says "pecah ini" / "cari source aslinya"). Not auto per ingest.
2. **Storage:** save segment mp4 files (`data/segments/<video_id>/seg_NN.mp4`) **and** metadata. Add retention later.
3. **Scene-cut engine:** PySceneDetect.
4. **Scope to build now:** Phase 1 (scene-cut + AI-group + `video_segments` + `/decompose`) + Phase 2 (Tier A credit→channel original-finder) + split-file saving + Telegram trigger.
5. **Tier B (reverse-search):** deferred. Leave a stubbed slot (`origin_status='not_found'` when no credit); wire a provider (Google Vision / SerpAPI / ACRCloud) later once an API key + egress consent are provided. No external image egress until then.
```
