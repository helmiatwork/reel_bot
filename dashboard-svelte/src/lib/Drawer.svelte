<script>
  import { drawer, closeDrawer } from './stores.js'
  import { api } from './api.js'

  let d = $state(null)
  let frames = $state([])
  let framesLoading = $state(false)
  let segments = $state([])
  let analysis = $state({})

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
  <div class="scrim" onclick={closeDrawer} role="presentation"></div>
  <aside class="drawer">
    <span class="x" onclick={closeDrawer} role="button" tabindex="0">✕</span>

    {#if d.type === 'source'}
      {@const s = d.data}
      <h2>{s.title}</h2>
      <div class="mut" style="font-size:12px;margin-bottom:8px">{s.channel || '-'} · {s.id}</div>
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
      {#if s.youtube_url}
        <div class="kv"><span>URL</span><a href={s.youtube_url} target="_blank" rel="noopener noreferrer" style="color:#2563eb;text-decoration:underline;cursor:pointer">buka video ↗</a></div>
      {/if}
      <div class="kv"><span>Views</span><span class="num">{s.viewsLabel}</span></div>
      <div class="kv"><span>Niche</span><span>{s.niche}</span></div>
      <div class="kv"><span>Status</span><span>{s.status}</span></div>
      {#if analysis.hook}
        <div class="kv"><span>Hook</span><span style="text-align:right;max-width:60%">{analysis.hook}</span></div>
      {/if}
      {#if analysis.retention}
        <div class="kv"><span>Retention</span><span style="text-align:right;max-width:60%">{analysis.retention}{analysis.retention_score ? ` (${analysis.retention_score}/10)` : ''}</span></div>
      {/if}
      {#if analysis.structure}
        <div class="kv"><span>Struktur</span><span style="text-align:right;max-width:60%">{analysis.structure}</span></div>
      {/if}
      {#if analysis.summary}
        <div class="kv-text"><span>Ringkas</span><div class="ana-text">{analysis.summary}</div></div>
      {/if}
      {#if analysis.detail}
        <div class="kv-text"><span>Detail</span><div class="ana-text">{analysis.detail}</div></div>
      {/if}
      {#if analysis.tags?.length}
        <div class="kv"><span>Tags</span><span style="text-align:right;max-width:60%">{#each analysis.tags as t}<span class="tag">{t}</span>{/each}</span></div>
      {/if}

      <!-- Generated prompt section -->
      {#if analysis.gen_prompt}
        <h3 style="margin:16px 0 8px;font-size:13px;font-weight:600">Generated prompt</h3>
        <div class="gen-prompt-box">
          {#if analysis.gen_prompt_format === 'prompt_json'}
            <pre class="gen-prompt-json">{(() => {
              try {
                const parsed = JSON.parse(analysis.gen_prompt)
                return JSON.stringify(parsed, null, 2)
              } catch {
                return analysis.gen_prompt
              }
            })()}</pre>
          {:else}
            <div class="gen-prompt-text">{analysis.gen_prompt}</div>
          {/if}
        </div>
        <button class="copy-btn" onclick={() => copyPrompt(analysis.gen_prompt)}>
          {copiedPrompt ? '✓ Copied!' : 'Copy'}
        </button>
      {/if}

      <!-- Re-analyze button -->
      {#if s.youtube_url}
        <div class="reana-wrap">
          <button
            class="reana-btn"
            disabled={reanalyzeLoading}
            onclick={reanalyze}
            aria-label="Re-analyze this video"
          >
            {reanalyzeLoading ? '⏳ Analyzing…' : 'Re-analyze'}
          </button>
          {#if reanalyzeDone}
            <span class="reana-ok">done</span>
          {/if}
          {#if reanalyzeError}
            <span class="reana-err">{reanalyzeError}</span>
          {/if}
        </div>
      {/if}

      <!-- Pecah button -->
      {#if s.youtube_url}
        <div class="pecah-wrap">
          <button
            class="pecah-btn"
            disabled={decomposeRunning}
            onclick={startDecompose}
          >
            {decomposeRunning ? '⏳ Memecah…' : segments.length ? 'Pecah ulang' : 'Pecah kompilasi'}
          </button>
          {#if decomposeRunning && decomposeStage}
            <span class="pecah-stage">{decomposeStage}</span>
          {/if}
          {#if decomposeError}
            <span class="pecah-err">{decomposeError}</span>
          {/if}
        </div>
      {:else}
        <div class="mut" style="font-size:12px;margin-top:10px">youtube_url tidak ada — tidak bisa decompose.</div>
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
  </aside>
{/if}

<style>
  .kv-text {
    display: flex; flex-direction: column; gap: 4px;
    padding: 8px 0; border-bottom: 1px solid #eee;
  }
  .kv-text span { font-weight: 600; color: #333; font-size: 12px; }
  .ana-text {
    font-size: 12px; color: #555; line-height: 1.5;
    max-height: 120px; overflow-y: auto; padding: 6px; background: #f9f9f9;
    border-radius: 4px; white-space: pre-wrap; word-break: break-word;
  }
  .seg-list { display: flex; flex-direction: column; gap: 6px; }
  .seg-row {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    font-size: 12px; padding: 6px 8px;
    background: #f9f9f9; border-radius: 4px; border: 1px solid #eee;
  }
  .seg-idx { font-weight: 600; color: #333; }
  .seg-time { color: #666; }
  .seg-credit { color: #444; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .badge-sm {
    font-size: 10px; font-weight: 600; padding: 1px 6px;
    border-radius: 8px; text-transform: lowercase; white-space: nowrap;
  }
  .b-found { background: #dcfce7; color: #166534; }
  .b-grey { background: #f0f0f0; color: #666; }

  .reana-wrap {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line, #1f2937);
  }
  .reana-btn {
    font-size: 12px; font-weight: 600; padding: 5px 12px;
    border-radius: 6px; cursor: pointer;
    background: rgba(110,168,254,.12); color: #6ea8fe;
    border: 1px solid rgba(110,168,254,.3); transition: opacity .15s;
  }
  .reana-btn:disabled { opacity: .55; cursor: default; }
  .reana-btn:not(:disabled):hover { background: rgba(110,168,254,.22); }
  .reana-ok  { font-size: 11px; color: #34d399; }
  .reana-err { font-size: 11px; color: #f87171; }

  .pecah-wrap {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    margin-top: 12px;
  }
  .pecah-btn {
    font-size: 12px; font-weight: 600; padding: 5px 12px;
    border-radius: 6px; border: none; cursor: pointer;
    background: #2563eb; color: #fff; transition: opacity .15s;
  }
  .pecah-btn:disabled { opacity: .55; cursor: default; }
  .pecah-btn:not(:disabled):hover { opacity: .85; }
  .pecah-stage { font-size: 11px; color: #555; font-style: italic; }
  .pecah-err { font-size: 11px; color: #dc2626; }

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
    padding: 10px; background: #f9f9f9; border-radius: 4px; border: 1px solid #eee;
    margin-bottom: 8px; max-height: 200px; overflow-y: auto;
  }
  .gen-prompt-json {
    font-size: 11px; margin: 0; line-height: 1.4; font-family: monospace;
    color: #333; white-space: pre-wrap; word-break: break-word;
  }
  .gen-prompt-text {
    font-size: 12px; color: #555; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
  }
  .copy-btn {
    font-size: 11px; padding: 4px 10px; background: #f0f0f0; border: 1px solid #ddd;
    border-radius: 4px; cursor: pointer; color: #333; transition: background .15s;
  }
  .copy-btn:hover { background: #e0e0e0; }
</style>
