<script>
  import { fade, scale } from 'svelte/transition'
  import { cubicOut } from 'svelte/easing'
  import { drawer, closeDrawer } from './stores.js'
  import { api } from './api.js'

  let d = $state(null)
  let frames = $state([])
  let framesLoading = $state(false)
  let segments = $state([])
  let analysis = $state({})

  // Total scenes in the generated storyboard (prompt_json), for the tab label
  let scenes = $derived.by(() => {
    try {
      const o = JSON.parse(analysis?.gen_prompt || '{}')
      const sb = o.scene_order || o.gen_prompt_storyboard?.scene_order || []
      return Array.isArray(sb) ? sb : []
    } catch { return [] }
  })
  let sceneCount = $derived(scenes.length)
  // Map a frame index to its best-matching storyboard scene:
  // 1: exact timestamp match if frame has .t and scenes have start/end
  // 2: 1:1 when counts match (fallback)
  // 3: proportional by position (fallback for old sources with no .t)
  function matchedScene(i) {
    if (!scenes.length || !frames.length) return null

    // Try exact timestamp match (frames have .t, scenes have start/end)
    const frame = frames[i]
    if (frame && typeof frame === 'object' && frame.t != null && scenes.length > 0) {
      // Parse scene times (format "m:ss") to seconds
      for (const scene of scenes) {
        if (scene.start && scene.end) {
          const start_s = timeToSeconds(scene.start)
          const end_s = timeToSeconds(scene.end)
          if (frame.t >= start_s && frame.t < end_s) {
            return scene
          }
        }
      }
      // No exact match: find nearest scene by time
      const nearest = scenes.reduce((best, curr) => {
        const curr_start = timeToSeconds(curr.start || '0:00')
        const best_start = timeToSeconds(best.start || '0:00')
        return Math.abs(frame.t - curr_start) < Math.abs(frame.t - best_start) ? curr : best
      })
      if (nearest) return nearest
    }

    // Fallback: proportional (for old sources without .t)
    if (scenes.length === frames.length) return scenes[i]
    const idx = frames.length > 1 ? Math.round((i / (frames.length - 1)) * (scenes.length - 1)) : 0
    return scenes[Math.min(Math.max(idx, 0), scenes.length - 1)]
  }

  // Convert "m:ss" to seconds
  function timeToSeconds(timeStr) {
    if (!timeStr) return 0
    const parts = timeStr.split(':')
    const m = parseInt(parts[0]) || 0
    const s = parseInt(parts[1]) || 0
    return m * 60 + s
  }

  // decompose state
  let decomposeRunning = $state(false)
  let decomposeStage = $state('')
  let decomposeError = $state('')
  let pollInterval = null

  // re-analyze state
  let reanalyzeLoading = $state(false)
  let reanalyzeError = $state('')
  let reanalyzeDone = $state(false)

  // lightbox state
  let lightboxSrc = $state(null)
  let lightboxIndex = $state(0)

  // copy state
  let copiedPrompt = $state(false)

  // tab state
  let activeTab = $state('analisa')
  // Display + copy share one string: pretty-printed JSON for prompt_json, raw otherwise
  // Split a prose string with "(1)… (2)…" markers into a lead + bullet points.
  // Returns null when there are no numbered markers (render as prose instead).
  function toPoints(text) {
    if (!text) return null
    const t = String(text)
    if (!/\(\d+\)/.test(t)) return null
    const first = t.search(/\(\d+\)/)
    const lead = t.slice(0, first).replace(/[\s:；;–—-]+$/, '').trim()
    const items = t.slice(first)
      .split(/\(\d+\)/)
      .map((s) => s.replace(/^[\s.]+/, '').replace(/[\s;；→\-–—]+$/, '').trim())
      .filter(Boolean)
    return items.length ? { lead, items } : null
  }

  function promptDisplay(a) {
    if (a?.gen_prompt_format === 'prompt_json') {
      try { return JSON.stringify(JSON.parse(a.gen_prompt), null, 2) } catch { return a.gen_prompt }
    }
    return a?.gen_prompt ?? ''
  }
  function copyPrompt(text) {
    navigator.clipboard.writeText(text).then(() => {
      copiedPrompt = true
      setTimeout(() => { copiedPrompt = false }, 2000)
    })
  }

  function stopPoll() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
  }

  function openLightbox(frame, i = 0) {
    // frame can be string (legacy) or object with .url
    lightboxSrc = typeof frame === 'string' ? frame : (frame?.url || '')
    lightboxIndex = i
  }
  function closeLightbox() { lightboxSrc = null }

  function onLightboxKey(e) {
    if (e.key === 'Escape') closeLightbox()
  }

  drawer.subscribe(async (v) => {
    stopPoll()
    decomposeRunning = false
    decomposeStage = ''
    decomposeError = ''
    reanalyzeLoading = false
    reanalyzeError = ''
    reanalyzeDone = false
    lightboxSrc = null
    activeTab = 'analisa'
    d = v
    frames = []
    segments = []
    analysis = {}
    if (v?.type === 'source') {
      if (v.data?.youtube_url) {
        framesLoading = true
        const res = await api.sourceFrames(v.data.youtube_url)
        frames = res?.frames ?? []
        framesLoading = false
      }
      // ponytail: non-fatal — segments missing = silently empty
      if (v.data?.id) {
        const segRes = await api.sourceSegments(v.data.id)
        segments = segRes?.segments ?? []
        // Fetch real analysis data from backend
        const anaRes = await api.sourceAnalysis(v.data.id)
        analysis = anaRes ?? {}
      }
    }
  })

  async function reanalyze() {
    const s = d?.data
    if (!s?.youtube_url) return
    reanalyzeLoading = true
    reanalyzeError = ''
    reanalyzeDone = false
    const r = await api.analyzeClaude(s.youtube_url, { force: true })
    reanalyzeLoading = false
    if (!r || r.error || r.detail) {
      reanalyzeError = r?.error || r?.detail || 'Re-analyze failed.'
      return
    }
    // refresh analysis display from canonical source
    if (s.id) {
      const fresh = await api.sourceAnalysis(s.id)
      if (fresh) analysis = fresh
    }
    reanalyzeDone = true
  }

  async function startDecompose() {
    const s = d?.data
    if (!s?.youtube_url) return
    decomposeRunning = true
    decomposeError = ''
    decomposeStage = 'memulai…'

    const resp = await api.decompose(s.youtube_url)
    if (!resp?.run_id) {
      decomposeError = resp?.error || 'Gagal memulai decompose.'
      decomposeRunning = false
      return
    }

    const run_id = resp.run_id
    // ponytail: poll every 4s, stop on done/error
    pollInterval = setInterval(async () => {
      const st = await api.decomposeStatus(run_id)
      if (!st) return
      decomposeStage = st.current_stage || decomposeStage

      if (st.status === 'done') {
        stopPoll()
        decomposeRunning = false
        // prefer segments from status response, fallback to re-fetch
        if (st.segments?.length) {
          segments = st.segments
        } else if (st.source_id) {
          const res = await api.sourceSegments(st.source_id)
          segments = res?.segments ?? []
        } else if (s.id) {
          const res = await api.sourceSegments(s.id)
          segments = res?.segments ?? []
        }
      } else if (st.status === 'error') {
        stopPoll()
        decomposeRunning = false
        decomposeError = st.error || 'Terjadi kesalahan.'
      }
    }, 4000)
  }
</script>

<!-- Lightbox overlay -->
{#if lightboxSrc}
  {@const sc = matchedScene(lightboxIndex)}
  {@const frameObj = typeof frames[lightboxIndex] === 'object' ? frames[lightboxIndex] : null}
  <div
    class="lb-overlay"
    onclick={closeLightbox}
    onkeydown={onLightboxKey}
    role="dialog"
    aria-modal="true"
    aria-label="Detail frame"
    tabindex="-1"
  >
    <button class="lb-close" onclick={closeLightbox} aria-label="Tutup">✕</button>
    <!-- ponytail: stopPropagation on the card keeps clicks inside from closing the overlay -->
    <div class="lb-card" onclick={(e) => e.stopPropagation()} role="document">
      <div class="lb-img-col">
        <img src={lightboxSrc} alt="frame diperbesar" class="lb-img" />
      </div>
      <div class="lb-info-col">
        <div class="lb-frame-no">Frame {lightboxIndex + 1}{frames.length ? ` / ${frames.length}` : ''}</div>
        {#if frameObj?.desc}
          <div class="lb-frame-desc">{frameObj.desc}</div>
        {/if}
        {#if sc}
          {#if sc.description || sc.action}
            <div class="lb-desc">{sc.description || sc.action}</div>
          {/if}
          <div class="lb-scene-cap">
            Scene cocok (dari Generated Prompt){sc.scene != null ? ` · #${sc.scene}` : ''}{sc.start ? ` · ${sc.start}${sc.end ? '–' + sc.end : ''}` : ''}
          </div>
          <pre class="lb-json">{JSON.stringify(sc, null, 2)}</pre>
        {:else}
          <div class="mut" style="font-size:12px">Belum ada storyboard buat dicocokkan — jalankan analisa dengan output Prompt JSON dulu.</div>
        {/if}
      </div>
    </div>
  </div>
{/if}

{#if d}
  <!-- Backdrop -->
  <div
    class="scrim"
    transition:fade={{ duration: 200 }}
    onclick={closeDrawer}
    aria-hidden="true"
  ></div>

  <!-- Modal Panel -->
  <div
    class="modal-panel"
    role="dialog"
    aria-modal="true"
    transition:scale={{ duration: 230, start: 0.94, easing: cubicOut }}
  >
    <!-- Header -->
    <div class="modal-header">
      <span class="x" onclick={closeDrawer} role="button" tabindex="0" aria-label="Tutup">✕</span>
    </div>

    <!-- Tab Bar (for source type only) -->
    {#if d.type === 'source'}
      <div class="tab-bar">
        <button
          class="tab-btn {activeTab === 'analisa' ? 'active' : ''}"
          onclick={() => activeTab = 'analisa'}
        >
          Analisa
        </button>
        <button
          class="tab-btn {activeTab === 'frames' ? 'active' : ''}"
          onclick={() => activeTab = 'frames'}
        >
          Frames{frames.length ? ` (${frames.length})` : ''}
        </button>
        <button
          class="tab-btn {activeTab === 'prompt' ? 'active' : ''}"
          onclick={() => activeTab = 'prompt'}
        >
          Generated Prompt{sceneCount ? ` (${sceneCount})` : ''}
        </button>
      </div>
    {/if}

    <!-- Content Container (scrollable) -->
    <div class="modal-content">
      {#if d.type === 'source'}
      {@const s = d.data}
      <div class="header-row">
        <div class="header-left">
          <h2 class="src-title">
            {#if s.youtube_url}
              <a href={s.youtube_url} target="_blank" rel="noopener noreferrer" class="title-link">{s.title} <span class="ext">↗</span></a>
            {:else}{s.title}{/if}
          </h2>
          <div class="header-meta">
            <span class="status-chip {s.status === 'analyzed' ? 'chip-green' : s.status === 'error' ? 'chip-red' : 'chip-mut'}">{s.status}</span>
            {#if s.niche && s.niche !== '-'}<span class="hm-item">{s.niche}</span>{/if}
            <span class="hm-item num">{s.viewsLabel} views</span>
          </div>
          <div class="mut" style="font-size:12px"><span class="sub-cap">Channel</span> {s.channel || '-'} <span class="sub-sep">·</span> <span class="sub-cap">ID</span> {s.id}</div>
        </div>
        {#if s.youtube_url}
          <div class="header-right">
            <div class="reana-wrap">
              <button
                class="reana-btn"
                disabled={reanalyzeLoading}
                onclick={reanalyze}
                aria-label="Re-analyze this video"
              >
                {reanalyzeLoading ? '⏳ Analyzing…' : 'Re-analyze'}
              </button>
              {#if reanalyzeDone}<span class="reana-ok">done</span>{/if}
              {#if reanalyzeError}<span class="reana-err">{reanalyzeError}</span>{/if}
            </div>
            <div class="pecah-wrap">
              <button
                class="pecah-btn"
                disabled={decomposeRunning}
                onclick={startDecompose}
              >
                {decomposeRunning ? '⏳ Memecah…' : segments.length ? 'Pecah ulang' : 'Pecah kompilasi'}
              </button>
              {#if decomposeRunning && decomposeStage}<span class="pecah-stage">{decomposeStage}</span>{/if}
              {#if decomposeError}<span class="pecah-err">{decomposeError}</span>{/if}
            </div>
          </div>
        {/if}
      </div>

      <!-- ANALISA TAB -->
      {#if activeTab === 'analisa'}
        <div class="tab-panel">
          <!-- Analysis section cards -->
          {#if analysis.hook}
            <div class="ana-card">
              <div class="ana-label">Hook</div>
              <div class="ana-body">{analysis.hook}</div>
            </div>
          {/if}
          {#if analysis.retention}
            {@const rp = toPoints(analysis.retention)}
            <div class="ana-card">
              <div class="ana-label">
                Retention
                {#if analysis.retention_score}<span class="score-badge">{analysis.retention_score}/10</span>{/if}
              </div>
              {#if rp}
                {#if rp.lead}<div class="ana-lead">{rp.lead}</div>{/if}
                <ol class="ana-points">{#each rp.items as it}<li>{it}</li>{/each}</ol>
              {:else}
                <div class="ana-body">{analysis.retention}</div>
              {/if}
            </div>
          {/if}
          {#if analysis.structure}
            {@const sp = toPoints(analysis.structure)}
            <div class="ana-card">
              <div class="ana-label">Struktur</div>
              {#if sp}
                {#if sp.lead}<div class="ana-lead">{sp.lead}</div>{/if}
                <ol class="ana-points">{#each sp.items as it}<li>{it}</li>{/each}</ol>
              {:else}
                <div class="ana-body">{analysis.structure}</div>
              {/if}
            </div>
          {/if}
          {#if analysis.summary}
            <div class="ana-card">
              <div class="ana-label">Ringkas</div>
              <div class="ana-body">{analysis.summary}</div>
            </div>
          {/if}
          {#if analysis.detail}
            <div class="ana-card">
              <div class="ana-label">Detail</div>
              <div class="ana-body">{analysis.detail}</div>
            </div>
          {/if}
          {#if analysis.tags?.length}
            <div class="tags-row">
              {#each analysis.tags as t}<span class="tag">{t}</span>{/each}
            </div>
          {/if}

          {#if segments.length}
            <h3 style="margin:16px 0 8px;font-size:13px;font-weight:600">Segmen</h3>
            <div class="seg-list">
              {#each segments as seg}
                <div class="seg-row">
                  <span class="seg-idx">Klip {seg.clip_index}</span>
                  <span class="seg-time">{seg.start_sec?.toFixed(1)}–{seg.end_sec?.toFixed(1)} dtk</span>
                  <span class="badge-sm {seg.origin_status === 'found' ? 'b-found' : 'b-grey'}">{seg.origin_status}</span>
                  <span class="seg-credit">{seg.credit_handle || '—'}</span>
                  {#if seg.original_url}
                    <a href={seg.original_url} target="_blank" rel="noopener noreferrer" style="font-size:12px">asli</a>
                  {:else}
                    <span class="mut" style="font-size:12px">belum ketemu</span>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/if}

      <!-- FRAMES TAB -->
      {#if activeTab === 'frames'}
        <div class="tab-panel">
          <div class="frames">
            {#if framesLoading}
              <div class="mut" style="font-size:12px;padding:8px 0">Memuat frames…</div>
            {:else if frames.length}
              {#each frames as frame, i}
                {@const frameUrl = typeof frame === 'string' ? frame : (frame?.url || '')}
                <button class="frame-thumb-btn" onclick={() => openLightbox(frame, i)} title="Klik untuk detail" aria-label="Detail frame">
                  <img src={frameUrl} alt="frame" loading="lazy" class="frame-thumb" />
                  <span class="frame-no">{i + 1}</span>
                </button>
              {/each}
            {:else if s.youtube_url}
              <div class="mut" style="font-size:12px;padding:8px 0">No frames tersimpan untuk video ini.</div>
            {:else}
              <div class="mut" style="font-size:12px;padding:8px 0">youtube_url tidak tersedia di baris ini — frames tidak dapat dimuat. (Lihat blocker note di kode.)</div>
            {/if}
          </div>
        </div>
      {/if}

      <!-- GENERATED PROMPT TAB -->
      {#if activeTab === 'prompt'}
        <div class="tab-panel">
          {#if analysis.gen_prompt}
            <div class="gen-prompt-box">
              {#if analysis.gen_prompt_format === 'prompt_json'}
                <pre class="gen-prompt-json">{promptDisplay(analysis)}</pre>
              {:else}
                <div class="gen-prompt-text">{analysis.gen_prompt}</div>
              {/if}
            </div>
            <button class="copy-btn" onclick={() => copyPrompt(promptDisplay(analysis))}>
              {copiedPrompt ? '✓ Copied!' : 'Copy'}
            </button>
          {:else}
            <div class="mut" style="font-size:12px;padding:8px 0">No generated prompt tersedia.</div>
          {/if}
        </div>
      {/if}

    {:else if d.type === 'agent'}
      {@const a = d.data}
      <h2>{a.name}</h2>
      <div class="meta" style="margin:8px 0">
        {#each a.model as m, i}<span class="m-chip {a.cls[i]}">{m}</span>{/each}
      </div>
      <div class="kv"><span>Peran</span><span style="text-align:right;max-width:62%">{a.role}</span></div>
      <div class="kv"><span>Model</span><span style="text-align:right;max-width:62%">{a.modelId || '-'}</span></div>
      <div class="kv"><span>Trigger</span><span style="text-align:right;max-width:62%">{a.trig}</span></div>
      <p class="mut" style="font-size:12.5px;margin-top:12px">{a.detail}</p>

    {:else if d.type === 'formula'}
      {@const f = d.data}
      <h2>{f.slug}</h2>
      <div class="meta" style="margin:8px 0">
        {#if f.db}<span class="m-chip s-active">sudah di DB</span>{:else}<span class="m-chip s-mod">usulan baru</span>{/if}
        <span class="m-chip m-cheap">{f.face}</span>
      </div>
      <div class="kv"><span>Best for</span><span style="text-align:right;max-width:60%">{f.best}</span></div>
      <h3 style="margin:14px 0 6px;font-size:13px">Struktur</h3>
      <p style="font-size:12.5px"><code style="display:block;padding:10px;line-height:1.6">{f.struct}</code></p>
      <div class="kv"><span>Hook</span><span style="text-align:right;max-width:60%">{f.hook}</span></div>
      <div class="kv"><span>Retensi</span><span style="text-align:right;max-width:60%">{f.ret}</span></div>
      <div class="kv"><span>Contoh</span><span style="text-align:right;max-width:60%">{f.ex}</span></div>

    {:else if d.type === 'piece'}
      {@const p = d.data}
      <h2>{p.title}</h2>
      <div class="mut" style="font-size:12px;margin-bottom:8px">{p.kind} · {p.niche}</div>
      <div class="kv"><span>Status</span><span>{p.status}</span></div>
      <div class="kv"><span>QC</span><span>{p.qc}</span></div>
      <h3 style="margin:14px 0 6px;font-size:13px">Assets</h3>
      {#each p.assets as x}
        <div class="kv"><span>{x.split(' ')[0]}</span><span>{#if x.includes('✓')}<span class="up">✓</span>{:else if x.includes('⏳')}<span class="mut">⏳</span>{:else}<span class="mut">✗</span>{/if}</span></div>
      {/each}
      <p class="mut" style="font-size:12.5px;margin-top:12px">{p.note}</p>
    {/if}
    </div>
  </div>
{/if}

<style>
  /* Centered modal overlay and backdrop */
  .scrim {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999;
  }

  .modal-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    z-index: 1000;
    width: 80vw;
    height: 80vh;
    max-width: 80vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .x {
    cursor: pointer;
    font-size: 20px;
    color: var(--mut);
    transition: color 0.15s;
    padding: 0.25rem;
    user-select: none;
  }

  .x:hover {
    color: var(--fg);
  }

  .modal-content {
    overflow-y: auto;
    overflow-x: hidden;
    flex: 1;
    padding: 1.5rem;
  }

  /* Responsive fallback for mobile/narrow screens */
  @media (max-width: 768px) {
    .modal-panel {
      width: 95vw;
      height: 90vh;
      max-width: 95vw;
      max-height: 90vh;
    }
  }

  /* Local .kv — global .drawer .kv doesn't reach .modal-panel; define here for agent/formula/piece types */
  .kv {
    display: flex; justify-content: space-between; align-items: flex-start;
    padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 13px; gap: 12px;
  }
  .kv span:first-child { color: var(--mut); flex-shrink: 0; }

  /* Meta block (source Analisa tab) */
  .meta-block {
    background: var(--soft); border: 1px solid var(--line);
    border-radius: 8px; overflow: hidden; margin-bottom: 12px;
  }
  .meta-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; padding: 9px 14px; border-bottom: 1px solid var(--line); font-size: 13px;
  }
  .meta-row:last-child { border-bottom: none; }
  .meta-label {
    font-size: 10.5px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--mut); flex-shrink: 0;
  }
  .meta-val { color: var(--txt); }
  .meta-link { color: var(--accent); text-decoration: underline; font-size: 13px; }

  /* Status chip */
  .status-chip { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 20px; }
  .chip-green { background: rgba(10,179,156,.12); color: var(--green); }
  .chip-red   { background: rgba(240,101,72,.12);  color: var(--red);   }
  .chip-mut   { background: rgba(148,163,184,.16); color: var(--mut);   }

  /* Header: clickable title + inline meta (status / niche / views) */
  .src-title { margin: 0 0 6px; }
  .title-link { color: var(--txt); text-decoration: none; }
  .title-link:hover { color: var(--accent); text-decoration: underline; }
  .title-link .ext { color: var(--accent); font-size: 0.8em; }
  .header-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
  .hm-item {
    font-size: 12px; color: var(--mut); font-weight: 500;
    padding: 2px 9px; background: var(--soft); border: 1px solid var(--line); border-radius: 20px;
  }

  .sub-cap { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--mut); opacity: 0.75; }
  .sub-sep { opacity: 0.5; margin: 0 2px; }

  /* Header 80/20: title+meta left, action buttons right */
  .header-row { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 12px; }
  .header-left { flex: 1 1 80%; min-width: 0; }
  .header-right { flex: 0 0 20%; display: flex; flex-direction: column; gap: 8px; }
  .header-right .reana-wrap,
  .header-right .pecah-wrap {
    margin-top: 0; padding-top: 0; border-top: none;
    flex-direction: column; align-items: stretch; gap: 4px;
  }
  .header-right .reana-btn, .header-right .pecah-btn { width: 100%; text-align: center; }
  @media (max-width: 768px) {
    .header-row { flex-direction: column; }
    .header-right { flex-basis: auto; width: 100%; flex-direction: row; }
    .header-right .reana-wrap, .header-right .pecah-wrap { flex: 1; }
  }

  /* Analysis section cards */
  .ana-card {
    background: var(--soft); border: 1px solid var(--line);
    border-radius: 8px; padding: 12px 14px;
  }
  .ana-label {
    font-size: 10.5px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--mut);
    margin-bottom: 6px; display: flex; align-items: center; gap: 8px;
  }
  .ana-body {
    font-size: 13px; color: var(--txt); line-height: 1.65;
    white-space: pre-wrap; word-break: break-word;
  }
  .ana-lead {
    font-size: 13px; color: var(--txt); line-height: 1.6; margin-bottom: 8px;
  }
  .ana-points {
    margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px;
  }
  .ana-points li {
    font-size: 13px; color: var(--txt); line-height: 1.55; word-break: break-word;
  }
  .ana-points li::marker { color: var(--mut); font-weight: 600; }
  .score-badge {
    font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 8px;
    background: rgba(64,81,137,.12); color: var(--accent);
    text-transform: none; letter-spacing: 0;
  }
  .tags-row { display: flex; flex-wrap: wrap; gap: 4px; }
  .seg-list { display: flex; flex-direction: column; gap: 6px; }
  .seg-row {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    font-size: 12px; padding: 6px 10px;
    background: var(--soft); border-radius: 6px; border: 1px solid var(--line);
  }
  .seg-idx { font-weight: 600; color: var(--txt); }
  .seg-time { color: var(--mut); }
  .seg-credit { color: var(--txt); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .badge-sm {
    font-size: 10px; font-weight: 600; padding: 1px 6px;
    border-radius: 8px; text-transform: lowercase; white-space: nowrap;
  }
  .b-found { background: rgba(10,179,156,.12); color: var(--green); }
  .b-grey  { background: rgba(148,163,184,.14); color: var(--mut); }

  .top-actions {
    display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 14px;
  }
  .top-actions .reana-wrap,
  .top-actions .pecah-wrap {
    margin-top: 0; padding-top: 0; border-top: none;
  }
  .reana-wrap {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line);
  }
  .reana-btn {
    font-size: 12px; font-weight: 600; padding: 5px 12px;
    border-radius: 6px; cursor: pointer;
    background: rgba(64,81,137,.1); color: var(--accent);
    border: 1px solid rgba(64,81,137,.25); transition: opacity .15s;
  }
  .reana-btn:disabled { opacity: .55; cursor: default; }
  .reana-btn:not(:disabled):hover { background: rgba(64,81,137,.18); }
  .reana-ok  { font-size: 11px; color: var(--green); }
  .reana-err { font-size: 11px; color: var(--red); }

  .pecah-wrap {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    margin-top: 8px;
  }
  .pecah-btn {
    font-size: 12px; font-weight: 600; padding: 5px 12px;
    border-radius: 6px; border: none; cursor: pointer;
    background: var(--accent); color: #fff; transition: opacity .15s;
  }
  .pecah-btn:disabled { opacity: .55; cursor: default; }
  .pecah-btn:not(:disabled):hover { opacity: .85; }
  .pecah-stage { font-size: 11px; color: var(--mut); font-style: italic; }
  .pecah-err   { font-size: 11px; color: var(--red); }

  /* frame thumbnails — clickable zoom cue */
  .frame-thumb-btn {
    position: relative;
    display: block; width: 100%; padding: 0; border: none; background: none;
    cursor: zoom-in; border-radius: 4px; transition: opacity .15s;
  }
  .frame-thumb-btn:hover { opacity: .85; }
  .frame-thumb { width: 100%; border-radius: 4px; object-fit: cover; display: block; }

  /* lightbox */
  .lb-overlay {
    position: fixed; inset: 0; z-index: 9999;
    background: rgba(0,0,0,.82);
    display: flex; align-items: center; justify-content: center;
  }
  .lb-card {
    display: flex; flex-direction: row; gap: 12px;
    width: min(900px, 92vw); max-height: 88vh;
    background: var(--bg); border: 1px solid var(--line); border-radius: 12px;
    padding: 14px; box-shadow: 0 12px 48px rgba(0,0,0,.5);
  }
  .lb-img-col {
    flex: 0 0 50%;
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
  }
  .lb-img {
    width: 100%; max-height: 78vh; object-fit: contain;
    border-radius: 8px; background: var(--soft);
  }
  .lb-info-col {
    flex: 0 0 50%;
    display: flex; flex-direction: column; gap: 12px;
    overflow-y: auto;
    padding-right: 8px;
  }
  .lb-info { text-align: left; }
  .lb-frame-no {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
    color: var(--mut); margin-bottom: 6px;
  }
  .lb-frame-desc {
    font-size: 13px; color: var(--txt); line-height: 1.6;
    padding: 10px; background: var(--soft); border-radius: 6px;
    border-left: 3px solid var(--accent);
  }
  .lb-desc { font-size: 14px; color: var(--txt); line-height: 1.6; margin-bottom: 8px; }
  .lb-scene-cap { font-size: 11px; color: var(--mut); margin-bottom: 8px; }
  .lb-json {
    font-size: 12px; margin: 0; font-family: monospace; line-height: 1.5;
    background: var(--soft); border: 1px solid var(--line); border-radius: 8px;
    padding: 10px; color: var(--txt); white-space: pre; overflow-x: auto;
    max-height: 300px; overflow-y: auto;
  }
  .frame-no {
    position: absolute; top: 4px; left: 4px;
    font-size: 10px; font-weight: 700; color: #fff;
    background: rgba(0,0,0,.6); border-radius: 4px; padding: 1px 6px; line-height: 1.4;
  }
  .lb-close {
    position: absolute; top: 16px; right: 20px;
    background: rgba(255,255,255,.15); border: none; color: #fff;
    font-size: 18px; line-height: 1; width: 32px; height: 32px;
    border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center;
    transition: background .15s;
  }
  .lb-close:hover { background: rgba(255,255,255,.3); }
  .lb-img-btn {
    padding: 0; border: none; background: none; cursor: default;
    display: flex; align-items: center; justify-content: center;
  }

  /* Responsive lightbox: collapse to column on mobile */
  @media (max-width: 768px) {
    .lb-card {
      flex-direction: column;
      width: min(90vw, 500px);
    }
    .lb-img-col {
      flex: 0 0 auto;
    }
    .lb-info-col {
      flex: 1;
      padding-right: 0;
    }
  }

  .gen-prompt-box {
    padding: 12px 14px; background: var(--soft); border-radius: 8px; border: 1px solid var(--line);
    margin-bottom: 10px; max-height: 420px; overflow-y: auto; overflow-x: auto;
    min-width: 0; word-break: break-word;
  }
  .gen-prompt-json {
    font-size: 11px; margin: 0; line-height: 1.5; font-family: monospace;
    color: var(--txt); white-space: pre-wrap; word-break: break-word; min-width: 0;
  }
  .gen-prompt-text {
    font-size: 13px; color: var(--txt); line-height: 1.65; white-space: pre-wrap; word-break: break-word; min-width: 0;
  }
  .copy-btn {
    font-size: 11px; padding: 4px 10px; background: #f0f0f0; border: 1px solid #ddd;
    border-radius: 4px; cursor: pointer; color: #333; transition: background .15s;
  }
  .copy-btn:hover { background: #e0e0e0; }

  /* Tab bar */
  .tab-bar {
    display: flex; gap: 0; border-bottom: 1px solid var(--border);
    flex-shrink: 0; background: var(--bg); padding: 0;
  }
  .tab-btn {
    flex: 1; padding: 10px 12px; border: none; background: transparent;
    color: var(--mut); font-size: 13px; font-weight: 500; cursor: pointer;
    border-bottom: 2px solid transparent; transition: all .15s;
    position: relative; bottom: -1px; white-space: nowrap;
  }
  .tab-btn:hover { color: var(--fg); }
  .tab-btn.active {
    color: var(--accent); border-bottom-color: var(--accent);
  }

  /* Tab panel */
  .tab-panel {
    display: flex; flex-direction: column; gap: 10px;
  }
</style>
