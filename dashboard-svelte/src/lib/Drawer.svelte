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
  let sceneCount = $derived.by(() => {
    try {
      const o = JSON.parse(analysis?.gen_prompt || '{}')
      const sb = o.scene_order || o.gen_prompt_storyboard?.scene_order || []
      return Array.isArray(sb) ? sb.length : 0
    } catch { return 0 }
  })

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

  // copy state
  let copiedPrompt = $state(false)

  // tab state
  let activeTab = $state('analisa')
  // Display + copy share one string: pretty-printed JSON for prompt_json, raw otherwise
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

  function openLightbox(src) { lightboxSrc = src }
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
  <div
    class="lb-overlay"
    onclick={closeLightbox}
    onkeydown={onLightboxKey}
    role="dialog"
    aria-modal="true"
    aria-label="Preview gambar"
    tabindex="-1"
  >
    <button class="lb-close" onclick={closeLightbox} aria-label="Tutup">✕</button>
    <!-- ponytail: button wrapper keeps img non-interactive (a11y), stopPropagation prevents overlay close on img click -->
    <button class="lb-img-btn" onclick={(e) => e.stopPropagation()} aria-label="Gambar diperbesar">
      <img src={lightboxSrc} alt="preview besar" class="lb-img" />
    </button>
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
          <div class="mut" style="font-size:12px">{s.channel || '-'} · {s.id}</div>
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
            <div class="ana-card">
              <div class="ana-label">
                Retention
                {#if analysis.retention_score}<span class="score-badge">{analysis.retention_score}/10</span>{/if}
              </div>
              <div class="ana-body">{analysis.retention}</div>
            </div>
          {/if}
          {#if analysis.structure}
            <div class="ana-card">
              <div class="ana-label">Struktur</div>
              <div class="ana-body">{analysis.structure}</div>
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
              {#each frames as src}
                <button class="frame-thumb-btn" onclick={() => openLightbox(src)} title="Klik untuk perbesar" aria-label="Perbesar frame">
                  <img {src} alt="frame" loading="lazy" class="frame-thumb" />
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
  .lb-img {
    max-width: 90vw; max-height: 90vh;
    object-fit: contain; border-radius: 6px;
    box-shadow: 0 8px 40px rgba(0,0,0,.6);
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
