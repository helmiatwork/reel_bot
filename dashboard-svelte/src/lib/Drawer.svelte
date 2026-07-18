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
  // Convert "m:ss" or "m:ss.s" to seconds (preserve fractional seconds)
  function timeToSeconds(timeStr) {
    if (!timeStr) return 0
    const parts = timeStr.split(':')
    const m = parseInt(parts[0]) || 0
    const s = parseFloat(parts[1]) || 0
    return m * 60 + s
  }

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
  // Live status that overrides the row's status once polling detects a change.
  let liveStatus = $state(null)
  let curStatus = $derived(liveStatus ?? d?.data?.status)
  // While the source is still being prepared/analyzed, show a loading panel
  // instead of the (empty) tabs.
  let isProcessing = $derived(
    curStatus === 'processing' || curStatus === 'working' || curStatus === 'running'
  )

  // Live processing checklist (mirrors the Add-Source popup stepper)
  let procStage = $state('saving_meta')
  let procPoll = null
  const PROC_STEPS = [
    { key: 'saving_meta', label: 'Menyimpan atribut video' },
    { key: 'downloading', label: 'Mengunduh video' },
    { key: 'splitting', label: 'Memotong klip per menit' },
    { key: 'saving', label: 'Menyimpan atribut klip ke database' },
  ]
  const PROC_STAGE_ORDER = {
    saving_meta: 0, downloading: 1, detecting: 2, grouping: 2, splitting: 2,
    finding: 3, saving: 3, processing: 4, working: 4, done: 5, analyzed: 5,
  }
  function procStepStatus(stepKey) {
    const cur = PROC_STAGE_ORDER[procStage] ?? 0
    const idx = PROC_STEPS.findIndex(s => s.key === stepKey)
    if (cur > idx) return 'done'
    if (cur === idx) return 'active'
    return 'pending'
  }
  function stopProcPoll() { if (procPoll) { clearInterval(procPoll); procPoll = null } }
  // Signal that processing finished: short beep + transient banner.
  let justDone = $state(false)
  function notifyDone() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext
      const ctx = new Ctx()
      const o = ctx.createOscillator(), g = ctx.createGain()
      o.connect(g); g.connect(ctx.destination)
      o.frequency.value = 880; g.gain.value = 0.07
      o.start(); o.stop(ctx.currentTime + 0.18)
    } catch {}
    justDone = true
    setTimeout(() => { justDone = false }, 6000)
  }
  async function pollProcessing(youtubeUrl, sourceId) {
    // 1) if an active decompose run exists, use its granular stage
    let stage = null
    try {
      const runs = await api.analyzeRuns(20)
      const run = (runs || []).find(r => r.kind === 'decompose' && r.url === youtubeUrl && r.status !== 'done' && r.status !== 'error')
      if (run?.current_stage) stage = run.current_stage
    } catch {}
    // 2) otherwise fall back to the source status (processing/working/analyzed)
    try {
      const st = await api.storyboardStatus(youtubeUrl)
      if (st?.ready) {
        procStage = 'done'
        stopProcPoll()
        // reload full analysis + frames now that it's ready
        const [anaRes, frRes] = await Promise.all([
          api.sourceAnalysis(sourceId),
          youtubeUrl ? api.sourceFrames(youtubeUrl).catch(() => null) : Promise.resolve(null),
        ])
        analysis = anaRes ?? {}
        if (frRes?.frames) frames = frRes.frames
        // notify once, only on the processing → done transition
        if (liveStatus !== 'analyzed') { liveStatus = 'analyzed'; notifyDone() }
        return
      }
      if (!stage) stage = st?.status || 'processing'
    } catch {}
    procStage = stage || 'processing'
  }
  // Verify view state
  let showRawJson = $state(false)
  // Per-scene JSON popup (verify view)
  let sceneJsonModal = $state(null)
  let videoRef = $state(null)
  let anaVideoRef = $state(null)
  // Analisa sub-tab: 'hookret' (Hook & Retention) | 'overall' (Tags/Struktur/Ringkas/Detail)
  let anaSubTab = $state('hookret')

  // Extract video_id from youtube_url (handle v=, /shorts/, or last path segment)
  function extractVideoId(url) {
    if (!url) return null
    try {
      const u = new URL(url)
      if (u.hostname.includes('youtube.com')) {
        const v = u.searchParams.get('v')
        if (v) return v
      } else if (u.hostname.includes('youtu.be')) {
        return u.pathname.slice(1)
      } else if (u.hostname.includes('youtube.com') && u.pathname.includes('/shorts/')) {
        const m = u.pathname.match(/\/shorts\/([a-zA-Z0-9_-]+)/)
        if (m) return m[1]
      }
      return u.pathname.split('/').pop() || null
    } catch { return null }
  }

  // Play a scene: seek to start_sec and play until end_sec
  function playScene(startSec, endSec) {
    if (!videoRef) return
    videoRef.currentTime = startSec
    videoRef.play()
    // Stop playback at end_sec
    const checkEndTime = () => {
      if (videoRef.currentTime >= endSec) {
        videoRef.pause()
        videoRef.removeEventListener('timeupdate', checkEndTime)
      }
    }
    videoRef.addEventListener('timeupdate', checkEndTime)
  }

  // Stable per-tag hue from its text (same tag → same color every render)
  function tagHue(t) {
    let h = 0
    for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) % 360
    return h
  }

  // Seek to a scene's start and pause (preview the frame as a thumbnail)
  function seekScene(startSec) {
    if (!videoRef) return
    videoRef.pause()
    videoRef.currentTime = startSec
  }

  // Mirror of playScene but targets the Analisa tab video element
  function playAna(startSec, endSec) {
    if (!anaVideoRef) return
    anaVideoRef.currentTime = startSec
    anaVideoRef.play()
    const stop = () => { if (anaVideoRef.currentTime >= endSec) { anaVideoRef.pause(); anaVideoRef.removeEventListener('timeupdate', stop) } }
    anaVideoRef.addEventListener('timeupdate', stop)
  }

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

  // Gemini brief popup: the instruction the user pastes into Antigravity
  let geminiBriefModal = $state(null)
  let geminiBriefLoading = $state(false)
  let geminiBriefCopied = $state(false)
  // Auto-open the Gemini prompt popup once, the moment clips are ready.
  let briefAutoShown = $state(false)
  async function showGeminiBrief() {
    const url = d?.data?.youtube_url
    if (!url) return
    geminiBriefLoading = true
    geminiBriefModal = ''
    try {
      const res = await api.getGeminiBrief(url)
      geminiBriefModal = res?.instruction || res?.error || 'Gagal mengambil instruksi'
    } catch (e) {
      geminiBriefModal = `Error: ${e.message}`
    } finally {
      geminiBriefLoading = false
    }
  }
  function copyGeminiBrief() {
    navigator.clipboard.writeText(geminiBriefModal)
    geminiBriefCopied = true
    setTimeout(() => { geminiBriefCopied = false }, 2000)
  }

  function stopPoll() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
  }

  function openLightbox(src, i = 0) { lightboxSrc = src; lightboxIndex = i }
  function closeLightbox() { lightboxSrc = null }

  function onLightboxKey(e) {
    if (e.key === 'Escape') closeLightbox()
  }

  drawer.subscribe(async (v) => {
    stopPoll()
    stopProcPoll()
    liveStatus = null
    justDone = false
    briefAutoShown = false
    procStage = 'saving_meta'
    decomposeRunning = false
    decomposeStage = ''
    decomposeError = ''
    reanalyzeLoading = false
    reanalyzeError = ''
    reanalyzeDone = false
    lightboxSrc = null
    activeTab = 'analisa'
    anaSubTab = 'hookret'
    showRawJson = false
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
      // Live checklist while the source is still processing/working
      const st = v.data?.status
      if (st === 'processing' || st === 'working' || st === 'running') {
        pollProcessing(v.data.youtube_url, v.data.id)
        procPoll = setInterval(() => pollProcessing(v.data.youtube_url, v.data.id), 3000)
      }
    }
  })

  // Per-tab primary action: full re-analyze / redo frames+analysis / regenerate prompt only.
  let tabAction = $derived(
    activeTab === 'frames'
      ? { label: 'Re-generate frame', busy: '⏳ Frame…', stages: 'frames_only' }
      : activeTab === 'prompt'
      ? { label: 'Re-generate prompt', busy: '⏳ Prompt…', stages: 'prompt_only' }
      : { label: 'Re-analyze', busy: '⏳ Analyzing…', stages: 'full' }
  )

  async function runStage(stages) {
    const s = d?.data
    if (!s?.youtube_url) return
    reanalyzeLoading = true
    reanalyzeError = ''
    reanalyzeDone = false
    // Async endpoint → tracked in Proses popup + toast on done. Keep the source's
    // output format so the prompt regenerates the same kind; prompt_only needs a real one.
    let fmt = s.gen_prompt_format || analysis?.gen_prompt_format || 'none'
    if (stages === 'prompt_only' && fmt === 'none') fmt = 'prompt_json'
    const r = await api.analyzeClaudeAsync(s.youtube_url, { force: true, output_format: fmt, stages })
    reanalyzeLoading = false
    if (!r || r.error || r.detail || !r.run_id) {
      reanalyzeError = r?.error || r?.detail || 'Gagal.'
      return
    }
    reanalyzeDone = true
  }

  // Clear the action status line when switching tabs
  $effect(() => { activeTab; reanalyzeDone = false; reanalyzeError = '' })

  // Auto-open the Gemini prompt popup once, the moment clips are ready (all
  // processing steps done). Saves the user hunting for the "Tampilkan prompt
  // Gemini" button — the prompt they need to paste into Antigravity pops up here.
  $effect(() => {
    if (isProcessing && !briefAutoShown && procStepStatus('saving') === 'done' && d?.data?.youtube_url) {
      briefAutoShown = true
      showGeminiBrief()
    }
  })

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
      <img src={lightboxSrc} alt="frame diperbesar" class="lb-img" />
      <div class="lb-info">
        <div class="lb-frame-no">Frame {lightboxIndex + 1}{frames.length ? ` / ${frames.length}` : ''}</div>
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

<!-- Per-scene JSON popup -->
{#if sceneJsonModal}
  <div
    class="lb-overlay"
    onclick={() => sceneJsonModal = null}
    onkeydown={(e) => { if (e.key === 'Escape') sceneJsonModal = null }}
    role="dialog"
    aria-modal="true"
    aria-label="JSON scene"
    tabindex="-1"
  >
    <button class="lb-close" onclick={() => sceneJsonModal = null} aria-label="Tutup">✕</button>
    <div class="lb-card" onclick={(e) => e.stopPropagation()} role="document" style="max-width:640px">
      <div class="lb-info">
        <div class="lb-frame-no">Scene{sceneJsonModal.scene != null ? ` #${sceneJsonModal.scene}` : ''}{sceneJsonModal.start ? ` · ${sceneJsonModal.start}${sceneJsonModal.end ? '–' + sceneJsonModal.end : ''}` : ''}</div>
        <pre class="lb-json">{JSON.stringify(sceneJsonModal, null, 2)}</pre>
        <button class="copy-btn" onclick={() => copyPrompt(JSON.stringify(sceneJsonModal, null, 2))}>
          {copiedPrompt ? '✓ Tersalin' : 'Salin JSON'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Gemini brief popup: paste into Antigravity -->
{#if geminiBriefModal !== null}
  <div
    class="lb-overlay"
    onclick={() => geminiBriefModal = null}
    onkeydown={(e) => { if (e.key === 'Escape') geminiBriefModal = null }}
    role="dialog"
    aria-modal="true"
    aria-label="Prompt Gemini"
    tabindex="-1"
  >
    <button class="lb-close" onclick={() => geminiBriefModal = null} aria-label="Tutup">✕</button>
    <div class="lb-card" onclick={(e) => e.stopPropagation()} role="document" style="max-width:640px">
      <div class="lb-info">
        <div class="lb-frame-no">Prompt untuk Antigravity (Gemini)</div>
        {#if geminiBriefLoading}
          <div class="brief-loading"><span class="spin-sm"></span> Mengambil instruksi…</div>
        {:else}
          <pre class="lb-json">{geminiBriefModal}</pre>
          <button class="copy-btn" onclick={copyGeminiBrief}>
            {geminiBriefCopied ? '✓ Tersalin' : 'Salin prompt'}
          </button>
          <div class="brief-hint">Tempel ke Antigravity. Gemini akan panggil reelbot MCP, analisa klip, simpan hasil otomatis.</div>
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

    <!-- Tab Bar (for source type only; hidden while still processing) -->
    {#if d.type === 'source' && !isProcessing}
      <div class="tab-bar">
        <button
          class="tab-btn {activeTab === 'analisa' ? 'active' : ''}"
          onclick={() => activeTab = 'analisa'}
        >
          Analisa{#if curStatus}<span class="status-chip tab-chip {curStatus === 'analyzed' ? 'chip-green' : curStatus === 'working' ? 'chip-blue' : curStatus === 'processing' || curStatus === 'running' ? 'chip-amber' : curStatus === 'error' ? 'chip-red' : 'chip-mut'}">{curStatus}</span>{/if}
        </button>
        {#if frames.length}
          <button
            class="tab-btn {activeTab === 'frames' ? 'active' : ''}"
            onclick={() => activeTab = 'frames'}
          >
            Frames ({frames.length})
          </button>
        {/if}
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
            {#if s.niche && s.niche !== '-'}<span class="meta-chip">{s.niche}</span>{/if}
            <span class="meta-chip">{s.viewsLabel} views</span>
            <span class="meta-chip">Channel {s.channel || '-'}</span>
            <span class="meta-chip">ID {s.id}</span>
          </div>
        </div>
        {#if s.youtube_url}
          <div class="header-right">
            <div class="reana-wrap">
              <button
                class="reana-btn"
                disabled={reanalyzeLoading}
                onclick={() => runStage(tabAction.stages)}
                aria-label={tabAction.label}
              >
                {reanalyzeLoading ? tabAction.busy : tabAction.label}
              </button>
              {#if reanalyzeDone}<span class="reana-ok">✓ masuk antrean — lihat Proses</span>{/if}
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

      {#if justDone}
        <div class="done-banner" transition:fade={{ duration: 150 }}>✅ Selesai — analisa & storyboard sudah ke-load</div>
      {/if}

      <!-- Processing: analysis not ready yet — show loading instead of tabs -->
      {#if isProcessing}
        <div class="processing-panel">
          <div class="processing-title">Sedang diproses…</div>
          <div class="proc-steps">
            {#each PROC_STEPS as step}
              {@const ps = procStepStatus(step.key)}
              <div class="proc-step {ps}">
                <span class="proc-icon">
                  {#if ps === 'done'}✓{:else if ps === 'active'}<span class="spin-sm"></span>{:else}○{/if}
                </span>
                <span class="proc-label">{step.label}</span>
              </div>
            {/each}
          </div>
          <button class="proc-brief-btn" onclick={showGeminiBrief}>Tampilkan prompt Gemini</button>
          <div class="processing-sub">Klip siap. Analisa & storyboard Gemini dipantau di daftar Proses / status baris — hasil muncul di sini otomatis saat selesai.</div>
        </div>
      {/if}

      <!-- ANALISA TAB -->
      {#if !isProcessing && activeTab === 'analisa'}
        {@const anaVideoId = extractVideoId(d.data?.youtube_url)}
        <div class="tab-panel">
          <div class="verify-split">
            {#if anaVideoId}
              <div class="verify-left">
                <video bind:this={anaVideoRef} controls src={`/media/source/${anaVideoId}`} class="ana-video" />
              </div>
            {/if}
            <div class="verify-right">
              <div class="ana-subtabs">
                <button class="ana-subtab {anaSubTab === 'hookret' ? 'active' : ''}" onclick={() => anaSubTab = 'hookret'}>Hook &amp; Retention</button>
                <button class="ana-subtab {anaSubTab === 'overall' ? 'active' : ''}" onclick={() => anaSubTab = 'overall'}>Overall</button>
                <button class="ana-subtab {anaSubTab === 'karakter' ? 'active' : ''}" onclick={() => anaSubTab = 'karakter'}>Karakter{#if analysis.characters?.length} ({analysis.characters.length}){/if}</button>
              </div>

              {#if anaSubTab === 'hookret'}
                {#if analysis.hook}
                  {@const hookStart = analysis.hook_start || (scenes.length ? scenes[0].start : null)}
                  {@const hookEnd = analysis.hook_end || (scenes.length ? scenes[0].end : null)}
                  <div class="ana-card">
                    <div class="ana-label">
                      Hook
                      {#if hookStart && hookEnd}<span class="score-badge">{hookStart}–{hookEnd}</span>{/if}
                    </div>
                    <div class="ana-body">{analysis.hook}</div>
                    <div class="ana-btn-row">
                      {#if hookStart && hookEnd && anaVideoId}<button class="ana-play-btn" onclick={() => playAna(timeToSeconds(hookStart), timeToSeconds(hookEnd))}>▶ Putar hook</button>{/if}
                      <button class="ana-copy-btn" onclick={() => copyPrompt(analysis.hook)}>{copiedPrompt ? '✓ Tersalin' : 'Salin teks'}</button>
                    </div>
                  </div>
                {/if}
                {#if analysis.retention}
                  {@const rp = toPoints(analysis.retention)}
                  <div class="ana-card">
                    <div class="ana-label">
                      Retention
                      {#if analysis.retention_score}<span class="score-badge">{analysis.retention_score}/10</span>{/if}
                    </div>
                    {#if analysis.retention_points?.length}
                      {#each analysis.retention_points as p}
                        <div class="ana-rp-row">
                          <button class="ana-rp-btn" onclick={() => anaVideoId && playAna(timeToSeconds(p.start), timeToSeconds(p.end))} disabled={!anaVideoId} title={anaVideoId ? `Putar ${p.start}–${p.end}` : 'Video tidak tersedia'}>▶</button>
                          <span class="ana-rp-reason">{p.reason}</span>
                          <span class="ana-rp-time">{p.start}–{p.end}</span>
                        </div>
                      {/each}
                    {:else if rp}
                      {#if rp.lead}<div class="ana-lead">{rp.lead}</div>{/if}
                      <ol class="ana-points">{#each rp.items as it}<li>{it}</li>{/each}</ol>
                    {:else}
                      <div class="ana-body">{analysis.retention}</div>
                    {/if}
                    <div class="ana-btn-row">
                      {#if scenes.length && anaVideoId}<button class="ana-play-btn" onclick={() => playAna(timeToSeconds(scenes[0].start), timeToSeconds(scenes[scenes.length-1].end))}>▶ Putar full</button>{/if}
                      <button class="ana-copy-btn" onclick={() => copyPrompt(analysis.retention)}>{copiedPrompt ? '✓ Tersalin' : 'Salin teks'}</button>
                    </div>
                  </div>
                {/if}
                {#if !analysis.hook && !analysis.retention}
                  <div class="mut" style="font-size:12px;padding:8px 0">Belum ada data hook/retention. Re-analyze via Antigravity untuk mengisinya.</div>
                {/if}
              {/if}

              {#if anaSubTab === 'overall'}
                {#if analysis.tags?.length}
                  <div class="ana-card">
                    <div class="ana-label">Tags</div>
                    <div class="tags-row">
                      {#each analysis.tags as t}
                        <span class="tag" style="background: hsl({tagHue(t)} 70% 92%); color: hsl({tagHue(t)} 55% 32%); border-color: hsl({tagHue(t)} 55% 80%)">{t}</span>
                      {/each}
                    </div>
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
                {#if !analysis.tags?.length && !analysis.structure && !analysis.summary && !analysis.detail}
                  <div class="mut" style="font-size:12px;padding:8px 0">Belum ada data overall.</div>
                {/if}
              {/if}

              {#if anaSubTab === 'karakter'}
                {#if analysis.characters?.length}
                  {#each analysis.characters as c}
                    {@const attrs = [['build','Build'],['height','Tinggi'],['skin_tone','Kulit'],['face_shape','Bentuk wajah'],['eyebrows','Alis'],['eye_color','Mata'],['nose','Hidung'],['lips','Bibir'],['hair_color','Rambut'],['hairstyle','Gaya rambut'],['facial_hair','Kumis/janggut'],['glasses','Kacamata'],['expression','Ekspresi']]}
                    <div class="ana-card char-card">
                      <div class="char-head">
                        <span class="char-name">{c.name || 'Karakter'}</span>
                        {#if c.role}<span class="char-role">{c.role}</span>{/if}
                        {#if c.gender}<span class="score-badge">{c.gender}</span>{/if}
                        {#if c.age_range}<span class="score-badge">{c.age_range} th</span>{/if}
                      </div>
                      {#if attrs.some(([k]) => c[k])}
                        <table class="char-attr-table">
                          <tbody>
                            {#each attrs as [k, label]}
                              {#if c[k]}<tr><td class="attr-k">{label}</td><td class="attr-v">{c[k]}</td></tr>{/if}
                            {/each}
                          </tbody>
                        </table>
                      {/if}
                      {#each [['face','Wajah (detail)'],['distinguishing_features','Ciri khas'],['appearance','Penampilan'],['wardrobe','Wardrobe']] as [k, label]}
                        {#if c[k]}<div class="char-line"><span class="char-key">{label}</span><span class="char-val">{c[k]}</span></div>{/if}
                      {/each}
                      {#if c.recreation_prompt}
                        <div class="char-recreate">
                          <div class="char-key" style="flex:none;margin-bottom:4px">Prompt recreate (AI gen)</div>
                          <div class="char-recreate-body">{c.recreation_prompt}</div>
                          <button class="ana-copy-btn" style="margin-top:6px" onclick={() => copyPrompt(c.recreation_prompt)}>{copiedPrompt ? '✓ Tersalin' : 'Salin prompt recreate'}</button>
                        </div>
                      {/if}
                      <div class="ana-btn-row">
                        <button class="ana-copy-btn" onclick={() => copyPrompt([c.name, c.role, c.gender, c.age_range, c.build, c.height, c.skin_tone, c.face_shape, c.eyebrows, c.eye_color, c.nose, c.lips, c.hair_color, c.hairstyle, c.facial_hair, c.glasses, c.expression, c.face, c.distinguishing_features, c.appearance, c.wardrobe].filter(Boolean).join(' · '))}>{copiedPrompt ? '✓ Tersalin' : 'Salin semua'}</button>
                      </div>
                    </div>
                  {/each}
                {:else}
                  <div class="mut" style="font-size:12px;padding:8px 0">Belum ada data karakter. Re-analyze via Antigravity untuk mengisinya.</div>
                {/if}
              {/if}
            </div>
          </div>
        </div>
      {/if}

      <!-- FRAMES TAB -->
      {#if !isProcessing && activeTab === 'frames'}
        <div class="tab-panel">
          <div class="frames">
            {#if framesLoading}
              <div class="mut" style="font-size:12px;padding:8px 0">Memuat frames…</div>
            {:else if frames.length}
              {#each frames as f, i}
                <button class="frame-thumb-btn" onclick={() => openLightbox(f.url, i)} title={f.desc || 'Klik untuk detail'} aria-label="Detail frame">
                  <img src={f.url} alt={f.desc || 'frame'} loading="lazy" class="frame-thumb" />
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
      {#if !isProcessing && activeTab === 'prompt'}
        <div class="tab-panel verify-panel">
          {#if analysis.gen_prompt && analysis.gen_prompt_format === 'prompt_json'}
            {@const videoId = extractVideoId(d.data?.youtube_url)}
            {@const storyboard = (() => {
              try { return JSON.parse(analysis.gen_prompt) }
              catch { return {} }
            })()}

            <!-- Split: left video (sticky), right scene list (scroll) -->
            <div class="verify-split">
              {#if videoId}
                <div class="verify-left">
                  <video
                    bind:this={videoRef}
                    controls
                    src={`/media/source/${videoId}`}
                    style="background: #000; border-radius: 4px; width: 100%; display: block"
                  />
                </div>
              {/if}

              {#if storyboard.scene_order && Array.isArray(storyboard.scene_order)}
                <div class="verify-right">
                  {#each storyboard.scene_order as scene, si}
                    <div class="scene-row" class:is-hook={si === 0}>
                      <div class="scene-actions">
                        <button
                          class="scene-play"
                          onclick={() => playScene(timeToSeconds(scene.start), timeToSeconds(scene.end))}
                          title="Putar scene"
                          aria-label="Putar"
                        >
                          ▶
                        </button>
                        <button
                          class="scene-json-btn"
                          onclick={() => sceneJsonModal = scene}
                          title="Lihat JSON scene"
                          aria-label="JSON"
                        >
                          {'{ }'}
                        </button>
                      </div>
                      <div
                        class="scene-info"
                        onclick={() => seekScene(timeToSeconds(scene.start))}
                        onkeydown={(e) => { if (e.key === 'Enter') seekScene(timeToSeconds(scene.start)) }}
                        role="button"
                        tabindex="0"
                        title="Lihat frame (jeda di scene ini)"
                      >
                        <div class="scene-header">
                          #{scene.scene} · {scene.start}–{scene.end} · {scene.shot} · {scene.subject} · {scene.action}
                          {#if si === 0}<span class="hook-tag">hook</span>{/if}
                        </div>
                        {#if scene.image_prompt}
                          <div class="scene-prompt">{scene.image_prompt}</div>
                        {/if}
                      </div>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>

            <!-- JSON toggle -->
            <div class="verify-toggle">
              <button
                class="toggle-btn"
                onclick={() => showRawJson = !showRawJson}
              >
                {showRawJson ? 'Sembunyikan JSON' : 'Lihat JSON'}
              </button>
            </div>

            {#if showRawJson}
              <div class="gen-prompt-box" transition:fade={{ duration: 150 }}>
                <pre class="gen-prompt-json">{promptDisplay(analysis)}</pre>
                <button class="copy-btn" onclick={() => copyPrompt(promptDisplay(analysis))}>
                  {copiedPrompt ? '✓ Tersalin' : 'Salin'}
                </button>
              </div>
            {/if}
          {:else}
            <div class="mut" style="font-size:12px;padding:8px 0">
              {#if analysis.gen_prompt && analysis.gen_prompt_format !== 'prompt_json'}
                <div class="gen-prompt-box">
                  <div class="gen-prompt-text">{analysis.gen_prompt}</div>
                </div>
                <button class="copy-btn" onclick={() => copyPrompt(promptDisplay(analysis))}>
                  {copiedPrompt ? '✓ Copied!' : 'Copy'}
                </button>
              {:else}
                No generated prompt tersedia.
              {/if}
            </div>
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
  .tab-chip { margin-left: 6px; padding: 2px 8px; font-size: 10px; vertical-align: middle; }
  .chip-green { background: rgba(10,179,156,.12); color: var(--green); }
  .chip-red   { background: rgba(240,101,72,.12);  color: var(--red);   }
  .chip-amber { background: rgba(217,119,6,.12);   color: #d97706; }
  .chip-blue  { background: rgba(37,99,235,.12);    color: #2563eb; }

  .done-banner {
    margin: 0 0 12px; padding: 10px 14px; border-radius: 8px;
    background: rgba(22,163,74,.12); border: 1px solid rgba(22,163,74,.35);
    color: #16a34a; font-size: 13px; font-weight: 600; text-align: center;
  }
  .processing-panel {
    display: flex; flex-direction: column; align-items: center;
    gap: 14px; padding: 36px 20px; text-align: center;
  }
  .processing-title { font-size: 15px; font-weight: 600; }
  .processing-sub { font-size: 12px; color: var(--mut); max-width: 340px; }
  .proc-steps {
    display: flex; flex-direction: column; gap: 10px; text-align: left;
    padding: 16px 18px; background: var(--soft); border: 1px solid var(--line);
    border-radius: 8px; min-width: 280px;
  }
  .proc-step { display: flex; align-items: center; gap: 10px; font-size: 13px; }
  .proc-icon { width: 18px; height: 18px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; }
  .proc-step.pending { color: var(--mut); }
  .proc-step.active { color: var(--txt); font-weight: 600; }
  .proc-step.done { color: #16a34a; }
  .proc-step.done .proc-icon { color: #16a34a; font-weight: 700; }
  .proc-brief-btn { margin-left: auto; padding: 3px 10px; font-size: 12px; font-weight: 600; color: #fff; background: #6b46c1; border: none; border-radius: 6px; cursor: pointer; }
  .proc-brief-btn:hover { background: #5a3aa8; }
  .brief-loading { display: flex; align-items: center; gap: 8px; color: var(--mut); font-size: 13px; padding: 12px 0; }
  .brief-hint { margin-top: 10px; font-size: 12px; color: var(--mut); line-height: 1.5; }
  .spin-sm {
    width: 14px; height: 14px; border: 2px solid rgba(37,99,235,.25);
    border-top-color: #2563eb; border-radius: 50%; animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .chip-mut   { background: rgba(148,163,184,.16); color: var(--mut);   }

  /* Header: clickable title + inline meta (status / niche / views) */
  .src-title { margin: 0 0 6px; }
  .title-link { color: var(--txt); text-decoration: none; }
  .title-link:hover { color: var(--accent); text-decoration: underline; }
  .title-link .ext { color: var(--accent); font-size: 0.8em; }
  .header-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
  .hm-item, .meta-chip {
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
    display: flex; flex-direction: row; align-items: flex-start; gap: 16px;
    width: min(1120px, 94vw); max-height: 88vh; overflow: hidden;
    background: var(--bg); border: 1px solid var(--line); border-radius: 12px;
    padding: 14px; box-shadow: 0 12px 48px rgba(0,0,0,.5);
  }
  .lb-img {
    flex: 0 0 auto; width: auto; max-width: 44%; max-height: 82vh; object-fit: contain;
    border-radius: 8px; background: var(--soft);
  }
  .lb-info { text-align: left; flex: 1 1 auto; min-width: 0; max-height: 82vh; overflow-y: auto; }
  @media (max-width: 640px) {
    .lb-card { flex-direction: column; align-items: stretch; }
    .lb-img { max-width: 100%; max-height: 50vh; align-self: center; }
    .lb-info { max-height: none; overflow-y: visible; }
  }
  .lb-frame-no {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
    color: var(--mut); margin-bottom: 6px;
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

  /* Verify panel (Prompt tab with video + scenes) */
  .verify-panel {
    gap: 12px;
  }
  .verify-split {
    display: flex; gap: 14px; align-items: flex-start;
  }
  .verify-left {
    flex: 0 0 46%; position: sticky; top: 0; align-self: flex-start;
  }
  .verify-right {
    flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px;
    max-height: 72vh; overflow-y: auto;
  }
  @media (max-width: 720px) {
    .verify-split { flex-direction: column; }
    .verify-left { flex: none; width: 100%; position: static; }
    .verify-right { max-height: none; }
  }
  .scene-row {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 10px 12px; background: var(--soft); border: 1px solid var(--line);
    border-radius: 6px; font-size: 12px;
  }
  .scene-actions {
    flex-shrink: 0; display: flex; flex-direction: column; gap: 4px;
  }
  .scene-play {
    width: 28px; height: 28px; padding: 0;
    border: none; background: var(--accent); color: white;
    border-radius: 4px; cursor: pointer; font-size: 12px;
    transition: opacity .15s;
  }
  .scene-play:hover { opacity: .85; }
  .scene-json-btn {
    width: 28px; height: 28px; padding: 0;
    border: none; background: #6b46c1; color: white;
    border-radius: 4px; cursor: pointer; font-size: 11px; font-family: monospace;
    transition: opacity .15s;
  }
  .scene-json-btn:hover { opacity: .85; }
  .scene-info {
    flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px;
    cursor: pointer;
  }
  .scene-info:hover .scene-header { color: var(--accent); }
  .scene-header {
    font-size: 12px; color: var(--txt); font-weight: 500;
  }
  .scene-prompt {
    font-size: 11px; color: var(--mut); font-style: italic;
  }
  .verify-toggle {
    display: flex; justify-content: center;
  }
  .toggle-btn {
    font-size: 11px; padding: 6px 12px; background: var(--soft);
    border: 1px solid var(--line); border-radius: 4px; cursor: pointer;
    color: var(--mut); transition: all .15s;
  }
  .toggle-btn:hover { background: var(--border); color: var(--fg); }

  /* Hook highlight in Generated Prompt scene list */
  .scene-row.is-hook { background: rgba(10,179,156,.10); border-color: rgba(10,179,156,.45); }
  .hook-tag { display:inline-block; font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:#087f6b; background:rgba(10,179,156,.18); border-radius:4px; padding:1px 6px; margin-left:6px; vertical-align:middle; }

  /* Analisa tab video player */
  .ana-video { width:100%; border-radius:6px; background:#000; display:block; }
  .ana-subtabs { display:flex; gap:6px; margin-bottom:2px; }
  .ana-subtab {
    flex:1; padding:7px 10px; font-size:12px; font-weight:600; cursor:pointer;
    background:var(--soft); color:var(--mut); border:1px solid var(--line);
    border-radius:6px; transition:all .15s;
  }
  .ana-subtab:hover { color:var(--fg); }
  .ana-subtab.active { background:rgba(64,81,137,.12); color:var(--accent); border-color:rgba(64,81,137,.35); }
  .char-head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
  .char-name { font-size:14px; font-weight:700; color:var(--txt); }
  .char-role { font-size:11px; font-weight:600; padding:1px 8px; border-radius:8px; background:rgba(10,179,156,.14); color:var(--green); }
  .char-line { display:flex; gap:8px; font-size:12.5px; line-height:1.55; margin-bottom:5px; }
  .char-key { flex:0 0 80px; font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--mut); padding-top:2px; }
  .char-val { flex:1; color:var(--txt); word-break:break-word; }
  .char-attr-table { width:100%; border-collapse:collapse; margin-bottom:8px; font-size:12.5px; }
  .char-attr-table td { padding:5px 8px; border:1px solid var(--line); }
  .char-attr-table .attr-k { width:90px; font-weight:600; color:var(--mut); background:var(--soft); text-transform:capitalize; }
  .char-attr-table .attr-v { color:var(--txt); text-transform:capitalize; }
  .char-recreate { margin-top:8px; padding:10px; background:rgba(64,81,137,.06); border:1px solid rgba(64,81,137,.2); border-radius:6px; }
  .char-recreate-body { font-size:12.5px; line-height:1.55; color:var(--txt); word-break:break-word; }

  /* Analisa tab button rows */
  .ana-btn-row { display:flex; gap:8px; margin-top:10px; flex-wrap:wrap; }
  .ana-play-btn { font-size:12px; font-weight:600; padding:5px 12px; border-radius:6px; border:none; cursor:pointer; background:var(--accent); color:#fff; }
  .ana-play-btn:hover { opacity:.85; }
  .ana-copy-btn { font-size:12px; font-weight:600; padding:5px 12px; border-radius:6px; cursor:pointer; background:rgba(64,81,137,.1); color:var(--accent); border:1px solid rgba(64,81,137,.25); }
  .ana-copy-btn:hover { background:rgba(64,81,137,.18); }
  .ana-rp-row { display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid var(--border,rgba(0,0,0,.06)); }
  .ana-rp-row:last-child { border-bottom:none; }
  .ana-rp-btn { flex-shrink:0; width:26px; height:26px; border-radius:5px; border:none; cursor:pointer; background:var(--accent); color:#fff; font-size:10px; display:flex; align-items:center; justify-content:center; padding:0; }
  .ana-rp-btn:disabled { opacity:.4; cursor:default; }
  .ana-rp-btn:not(:disabled):hover { opacity:.85; }
  .ana-rp-reason { flex:1; font-size:12px; line-height:1.4; }
  .ana-rp-time { flex-shrink:0; font-size:11px; color:var(--mut); white-space:nowrap; }
</style>
