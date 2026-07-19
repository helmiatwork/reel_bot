<script>
  import { fade, scale } from 'svelte/transition'
  import { cubicOut } from 'svelte/easing'
  import { api } from './api.js'

  // Props (runes mode — isOpen is bound by parent)
  let { isOpen = $bindable(false), onSuccess = () => {}, onAnalyzeStarted = (_runId, _label) => {}, onAlreadyExists = (_source) => {} } = $props()

  // Modal state
  let activeTab = $state('url')
  let loading = $state(false)
  let error = $state(null)
  let panelEl = $state(null)
  let triggerEl = $state(null)

  // URL tab state
  let urlInput = $state('')
  let urlIntent = $state('')

  // File tab state
  let fileInput = $state(null)
  let selectedFile = $state(null)
  let fileIntent = $state('')

  // Output format (shared across both tabs)
  let outputFormat = $state('none')

  // Analysis mode (gemini_mcp, gemini_manual, claude)
  let analysisMode = $state('gemini_mcp')

  // Gemini mode state
  let geminiBrief = $state('')
  let geminiBriefCopied = $state(false)
  let geminiPaste = $state('')
  let savingGemini = $state(false)
  let geminiError = $state(null)
  let storyboardPhase = $state('')  // 'clips' | 'brief' | 'analyzing' | 'ready'
  let storyboardReady = $state(false)
  let storyboardScenes = $state(0)
  let pollStoryboardInterval = null
  let pollStoryboardCount = $state(0)
  let prepStage = $state('')
  let prepPollCount = $state(0)
  let geminiStarted = $state(false)  // true once Gemini calls get_clips (status='working')

  // Audio analysis options
  let includeAudio = $state(false)
  let audioStart = $state('')
  let audioEnd = $state('')
  const PREP_STAGE_LABEL = {
    downloading: 'Mengunduh video…',
    saving_meta: 'Menyimpan atribut video…',
    detecting: 'Mendeteksi scene…',
    grouping: 'Mengelompokkan…',
    splitting: 'Memotong klip per menit…',
    finding: 'Menautkan klip…',
    saving: 'Menyimpan ke database…',
  }
  // Live step checklist for the prep phase (like the analyze stepper).
  // order = how far the pipeline has progressed; each stage maps to a step.
  const PREP_STEPS = [
    { key: 'saving_meta', label: 'Menyimpan atribut video' },
    { key: 'downloading', label: 'Mengunduh video' },
    { key: 'splitting', label: 'Memotong klip per menit' },
    { key: 'saving', label: 'Menyimpan atribut klip ke database' },
  ]
  const PREP_STAGE_ORDER = { saving_meta: 0, downloading: 1, detecting: 2, grouping: 2, splitting: 2, finding: 3, saving: 3, done: 4 }
  // Status of a step given the current prepStage: done | active | pending
  function prepStepStatus(stepKey) {
    const cur = PREP_STAGE_ORDER[prepStage] ?? 0
    const idx = PREP_STEPS.findIndex(s => s.key === stepKey)
    if (cur > idx) return 'done'
    if (cur === idx) return 'active'
    return 'pending'
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  // Walk the prep checklist forward from wherever it stopped up to 'done', dwelling on
  // each step so the ✓s animate in sequence instead of snapping (prep is near-instant).
  async function animatePrepToDone() {
    const order = ['saving_meta', 'downloading', 'splitting', 'saving', 'done']
    let i = order.indexOf(prepStage)
    if (i < 0) i = 0
    for (; i < order.length; i++) {
      prepStage = order[i]
      await sleep(650)
    }
  }

  // Set when the submitted URL is already in the library
  let existsSource = $state(null)
  let dupConfirm = $state(null)   // pre-submit "URL sudah ada, timpa?" confirm
  let dupResolve = null           // resolver for the confirm promise (non-reactive)

  // Reset all form state whenever modal opens — fixes stale stepper bug
  // (parent sets isOpen directly, bypassing the old openModal() call)
  $effect(() => {
    if (isOpen) {
      triggerEl = document.activeElement
      urlInput = ''
      urlIntent = ''
      selectedFile = null
      fileIntent = ''
      outputFormat = 'none'
      analysisMode = 'gemini_mcp'
      geminiBrief = ''
      geminiBriefCopied = false
      geminiPaste = ''
      savingGemini = false
      geminiError = null
      error = null
      loading = false
      activeTab = 'url'
      existsSource = null
      includeAudio = false
      audioStart = ''
      audioEnd = ''
      storyboardPhase = ''
      storyboardReady = false
      storyboardScenes = 0
      prepStage = ''
      prepPollCount = 0
      geminiStarted = false
      dupConfirm = null
      dupResolve = null
    }
  })

  function openExisting() {
    onAlreadyExists(existsSource)
    closeModal()
  }

  // Before a URL analyze/decompose, check if the same video (canonical key,
  // so youtu.be/X == watch?v=X) already exists. If so, ask yes/no. Returns a
  // promise: true = proceed (old one deleted on override), false = cancelled.
  async function ensureNotDuplicate(url) {
    try {
      const ex = await api.sourceExists(url)
      if (ex?.exists) {
        dupConfirm = ex
        return await new Promise((resolve) => { dupResolve = resolve })
      }
    } catch (e) { /* non-fatal — allow the submit through */ }
    return true
  }
  async function overrideExisting() {
    const ex = dupConfirm
    dupConfirm = null
    if (ex?.id) { try { await api.deleteSource(ex.id) } catch (e) { /* proceed anyway */ } }
    if (dupResolve) { const r = dupResolve; dupResolve = null; r(true) }
  }
  function cancelDup() {
    dupConfirm = null
    if (dupResolve) { const r = dupResolve; dupResolve = null; r(false) }
  }

  function closeModal() {
    stopStoryboardPolling()
    if (dupResolve) cancelDup()  // M1: settle dangling coroutine before close
    isOpen = false
    setTimeout(() => triggerEl?.focus(), 50)
  }

  function onBackdropClick(e) {
    if (e.target === e.currentTarget) closeModal()
  }

  function onKey(e) {
    if (!isOpen) return
    if (e.key === 'Escape') {
      if (dupConfirm) { cancelDup(); return }
      closeModal()
    }
  }

  function trapFocus(e) {
    if (!panelEl || e.key !== 'Tab') return
    const focusable = panelEl.querySelectorAll(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last?.focus() }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first?.focus() }
    }
  }

  async function submitUrl() {
    if (!urlInput.trim()) {
      error = 'URL tidak boleh kosong'
      return
    }
    if (!(await ensureNotDuplicate(urlInput.trim()))) return
    loading = true
    error = null
    existsSource = null
    try {
      const options = {
        intent: urlIntent,
        output_format: outputFormat,
        include_audio: includeAudio,
      }
      // Only include audio_start/audio_end if they're filled in
      if (audioStart.trim()) {
        options.audio_start = parseFloat(audioStart)
      }
      if (audioEnd.trim()) {
        options.audio_end = parseFloat(audioEnd)
      }
      const result = await api.analyzeClaudeAsync(urlInput.trim(), options)
      if (result?.already_exists) {
        existsSource = result.source
        loading = false
        return
      }
      if (!result?.run_id) {
        error = result?.message || 'Gagal memulai analisis'
        loading = false
        return
      }
      onAnalyzeStarted(result.run_id, urlInput.trim())
      closeModal()
    } catch (e) {
      error = `Error: ${e.message}`
      loading = false
    }
  }

  async function submitFile() {
    if (!selectedFile) {
      error = 'Pilih file terlebih dahulu'
      return
    }
    loading = true
    error = null
    try {
      const options = {
        intent: fileIntent,
        output_format: outputFormat,
        include_audio: includeAudio,
      }
      // Only include audio_start/audio_end if they're filled in
      if (audioStart.trim()) {
        options.audio_start = parseFloat(audioStart)
      }
      if (audioEnd.trim()) {
        options.audio_end = parseFloat(audioEnd)
      }
      const result = await api.uploadSourceAsync(selectedFile, options)
      if (!result?.run_id) {
        error = result?.message || 'Gagal memulai analisis'
        loading = false
        return
      }
      onAnalyzeStarted(result.run_id, selectedFile?.name || 'Upload file')
      closeModal()
    } catch (e) {
      error = `Error: ${e.message}`
      loading = false
    }
  }

  function handleFileSelect(e) {
    selectedFile = e.target.files?.[0] || null
    if (selectedFile && selectedFile.size > 200 * 1024 * 1024) {
      error = 'File terlalu besar (max 200 MB)'
      selectedFile = null
    }
  }

  function stopStoryboardPolling() {
    if (pollStoryboardInterval) {
      clearInterval(pollStoryboardInterval)
      pollStoryboardInterval = null
    }
    storyboardPhase = ''
    storyboardReady = false
    pollStoryboardCount = 0
  }

  async function fetchGeminiBrief() {
    if (!urlInput.trim()) {
      geminiError = 'URL tidak boleh kosong'
      return
    }
    if (!(await ensureNotDuplicate(urlInput.trim()))) return
    loading = true
    geminiError = null
    geminiBrief = ''
    storyboardPhase = ''
    storyboardReady = false
    storyboardScenes = 0
    stopStoryboardPolling()

    try {
      // Phase A: Prepare clips with per-minute interval (fixed 60s windows)
      storyboardPhase = 'clips'
      const decomposeResult = await api.decomposePerMinute(urlInput.trim())
      if (!decomposeResult?.run_id) {
        geminiError = decomposeResult?.error || 'Gagal memulai persiapan klip'
        loading = false
        storyboardPhase = ''
        return
      }

      // Poll for decompose completion
      let done = false
      let pollCount = 0
      const maxPolls = 600
      prepStage = 'saving_meta'
      prepPollCount = 0
      while (!done && pollCount < maxPolls) {
        await new Promise(resolve => setTimeout(resolve, 1000))
        const statusResult = await api.decomposeStatus(decomposeResult.run_id)
        prepPollCount = pollCount + 1
        if (statusResult?.status && statusResult.status !== 'done') {
          prepStage = statusResult.status
        }
        if (statusResult?.status === 'done') {
          done = true
        } else if (statusResult?.status === 'error') {
          geminiError = statusResult?.error || 'Persiapan klip gagal'
          loading = false
          storyboardPhase = ''
          return
        }
        pollCount++
      }

      if (!done) {
        geminiError = 'Timeout menunggu persiapan klip'
        loading = false
        storyboardPhase = ''
        return
      }

      // Stream-copy makes prep near-instant, so the checklist would snap straight to
      // the brief. Walk the remaining steps forward with a small dwell so each ✓ ticks
      // over smoothly before the prompt appears.
      await animatePrepToDone()

      // Phase B: Fetch Gemini brief & start monitoring.
      // Gemini writes BOTH analysis and storyboard (save_analysis + save_storyboard).
      // Claude is only a manual fallback via the Re-analyze button in the drawer.
      // If audio_start/audio_end provided: generates Suno prompt instruction instead.
      storyboardPhase = 'brief'
      // When Suno is checked, ALWAYS send audio params so the backend serves the
      // Suno brief — not the decompose brief. A blank start/end defaults to a
      // 30s window from 0 (enough for music analysis) instead of silently
      // falling back to the video-decompose flow, which confused Gemini.
      const briefOptions = {}
      if (includeAudio) {
        briefOptions.audio_start = audioStart.trim() ? parseFloat(audioStart) : 0
        briefOptions.audio_end = audioEnd.trim()
          ? parseFloat(audioEnd)
          : briefOptions.audio_start + 30
      }
      const result = await api.getGeminiBrief(urlInput.trim(), briefOptions)
      if (result?.instruction) {
        geminiBrief = result.instruction
      } else {
        geminiError = result?.error || 'Gagal mengambil instruksi'
        loading = false
        storyboardPhase = ''
        return
      }

      // Phase C: Auto-poll storyboard status (user runs Gemini in Antigravity)
      storyboardPhase = 'analyzing'
      geminiStarted = false
      pollStoryboardCount = 0
      pollStoryboardInterval = setInterval(async () => {
        pollStoryboardCount++
        const statusResult = await api.storyboardStatus(urlInput.trim())
        // status flips processing → working (Gemini called get_clips) → analyzed (done)
        geminiStarted = statusResult?.status === 'working'
        if (statusResult?.ready) {
          storyboardReady = true
          storyboardScenes = statusResult.scenes || 0
          stopStoryboardPolling()
          storyboardPhase = 'ready'
        } else if (pollStoryboardCount >= 200) {
          // Cap at ~200 polls (10 min at 3s interval)
          stopStoryboardPolling()
          geminiError = 'Timeout menunggu Gemini analisa'
        }
      }, 3000)
    } catch (e) {
      geminiError = `Error: ${e.message}`
      storyboardPhase = ''
    } finally {
      loading = false
    }
  }

  function copyGeminiBrief() {
    navigator.clipboard.writeText(geminiBrief)
    geminiBriefCopied = true
    setTimeout(() => { geminiBriefCopied = false }, 2000)
  }

  async function saveGeminiStoryboard() {
    if (!urlInput.trim()) {
      geminiError = 'URL tidak boleh kosong'
      return
    }
    if (!geminiPaste.trim()) {
      geminiError = 'Tempel hasil Gemini (JSON) terlebih dahulu'
      return
    }
    savingGemini = true
    geminiError = null
    try {
      const result = await api.importStoryboard(urlInput.trim(), geminiPaste.trim())
      if (result?.ok) {
        onSuccess()
        closeModal()
      } else {
        geminiError = result?.error || 'Gagal menyimpan storyboard'
      }
    } catch (e) {
      geminiError = `Error: ${e.message}`
    } finally {
      savingGemini = false
    }
  }
</script>

<svelte:window onkeydown={onKey} />

{#if isOpen}
  <!-- Backdrop -->
  <div
    class="backdrop"
    transition:fade={{ duration: 200 }}
    onclick={onBackdropClick}
    aria-hidden="true"
  ></div>

  <!-- Modal Panel -->
  <div
    class="modal-panel"
    bind:this={panelEl}
    role="dialog"
    aria-modal="true"
    aria-label="Tambah source"
    tabindex="-1"
    transition:scale={{ duration: 230, start: 0.94, easing: cubicOut }}
    onkeydown={trapFocus}
  >
    <!-- Header -->
    <div class="m-head">
      <span class="m-title">Tambah Source</span>
      <button class="m-close" onclick={closeModal} aria-label="Tutup modal">
        <svg class="ic"><use href="#i-x"/></svg>
      </button>
    </div>

    <!-- Body -->
    <div class="m-body">
      <!-- Analysis Mode Selector -->
      <div class="analysis-mode-selector">
        <label class="field">
          <span class="field-label">Metode Analisis</span>
          <div class="mode-options">
            <label class="mode-option">
              <input type="radio" name="analysisMode" value="gemini_mcp" bind:group={analysisMode} disabled={loading || savingGemini} />
              <span class="mode-label">Gemini (Antigravity)</span>
            </label>
            <label class="mode-option">
              <input type="radio" name="analysisMode" value="gemini_manual" bind:group={analysisMode} disabled={loading || savingGemini} />
              <span class="mode-label">Gemini (manual)</span>
            </label>
            <label class="mode-option">
              <input type="radio" name="analysisMode" value="claude" bind:group={analysisMode} disabled={loading || savingGemini} />
              <span class="mode-label">Claude (auto)</span>
            </label>
          </div>
        </label>
      </div>

      <!-- Conditional content based on analysis mode -->
      {#if analysisMode === 'gemini_mcp' || analysisMode === 'gemini_manual'}
        <!-- Gemini mode (both MCP and manual) -->
        <div class="gemini-section" transition:fade={{ duration: 150 }}>
          <label class="field">
            <span class="field-label">YouTube / TikTok / Instagram URL</span>
            <input
              class="inp"
              type="text"
              placeholder="https://youtube.com/watch?v=..."
              bind:value={urlInput}
              disabled={loading || savingGemini}
            />
          </label>

          {#if analysisMode === 'gemini_mcp'}
            <!-- Audio/Suno option for MCP mode -->
            <label class="field">
              <span class="field-label">Bikin prompt Suno (analisa audio) <span class="opt">(opsional)</span></span>
              <label class="checkbox-label">
                <input
                  type="checkbox"
                  bind:checked={includeAudio}
                  disabled={loading}
                />
                <span>Clip audio → analisa → output Suno prompt</span>
              </label>
            </label>

            {#if includeAudio}
              <div class="audio-segment-container" transition:fade={{ duration: 150 }}>
                <label class="field">
                  <span class="field-label">Segmen audio yang dipotong <span class="opt">(opsional — kosongkan = full)</span></span>
                  <div class="audio-segment-inputs">
                    <input
                      class="inp inp-time"
                      type="number"
                      placeholder="Mulai (detik)"
                      bind:value={audioStart}
                      disabled={loading}
                      min="0"
                      step="0.1"
                    />
                    <span class="segment-dash">–</span>
                    <input
                      class="inp inp-time"
                      type="number"
                      placeholder="Akhir (detik)"
                      bind:value={audioEnd}
                      disabled={loading}
                      min="0"
                      step="0.1"
                    />
                  </div>
                </label>
              </div>
            {/if}
          {/if}

          {#if analysisMode === 'gemini_mcp'}
            <!-- MCP mode: show instruction + polling -->
            {#if !storyboardPhase}
              <button
                class="btn-fetch-brief"
                onclick={fetchGeminiBrief}
                disabled={loading || !urlInput.trim()}
              >
                {#if loading}
                  <span class="spinner-sm"></span>
                  Ambil instruksi…
                {:else}
                  Ambil instruksi Gemini
                {/if}
              </button>
            {:else if storyboardPhase === 'clips'}
              <div class="prep-stepper" transition:fade={{ duration: 150 }}>
                <div class="prep-hd">
                  <span class="prep-title">Menyiapkan clip</span>
                  <span class="prep-elapsed">{prepPollCount}s</span>
                </div>
                {#each PREP_STEPS as step}
                  {@const st = prepStepStatus(step.key)}
                  <div class="prep-step {st}">
                    <span class="prep-icon">
                      {#if st === 'done'}✓{:else if st === 'active'}<span class="spinner-sm"></span>{:else}○{/if}
                    </span>
                    <span class="prep-label">{step.label}</span>
                  </div>
                {/each}
              </div>
            {:else if storyboardPhase === 'brief' || storyboardPhase === 'analyzing'}
              <div class="brief-box" transition:fade={{ duration: 150 }}>
                <textarea
                  class="inp inp-brief"
                  readonly
                  placeholder="Mengambil instruksi… (mengunduh potongan audio)"
                  value={geminiBrief}
                ></textarea>
                <button
                  class="btn-copy"
                  onclick={copyGeminiBrief}
                >
                  {geminiBriefCopied ? '✓ Tersalin' : 'Salin'}
                </button>
                <div class="brief-note">Tempel instruksi ini ke Antigravity. Gemini menonton klip lewat reelbot MCP, lalu menyimpan analisa + storyboard sekaligus. (Claude hanya cadangan manual via tombol Re-analyze kalau Gemini bermasalah.)</div>

                {#if storyboardPhase === 'analyzing'}
                  <div class="analyzing-box {geminiStarted ? 'working' : ''}" transition:fade={{ duration: 150 }}>
                    <span class="spinner-sm"></span>
                    {#if geminiStarted}
                      <span>Gemini (Antigravity) sedang bekerja…</span>
                    {:else}
                      <span>Menunggu Gemini mulai (tempel instruksi di Antigravity)…</span>
                    {/if}
                    <button class="btn-cancel" onclick={stopStoryboardPolling}>Batal</button>
                  </div>
                {/if}
              </div>
            {:else if storyboardPhase === 'ready' && storyboardReady}
              <div class="ready-box" transition:fade={{ duration: 150 }}>
                <div class="ready-msg">✅ Storyboard siap: {storyboardScenes} scene</div>
                <button
                  class="btn-primary"
                  onclick={closeModal}
                >
                  Tutup
                </button>
              </div>
            {/if}
          {:else}
            <!-- Manual mode: show paste box -->
            <label class="field">
              <span class="field-label">Tempel hasil Gemini (JSON)</span>
              <textarea
                class="inp inp-mono"
                placeholder="Paste hasil JSON dari Gemini di sini"
                bind:value={geminiPaste}
                disabled={savingGemini}
                rows="8"
              ></textarea>
            </label>
          {/if}

          {#if geminiError}
            <div class="error-msg" transition:fade={{ duration: 150 }}>
              {geminiError}
            </div>
          {/if}
        </div>
      {:else}
        <!-- Claude mode: show original upload flow -->
        <!-- Tabs -->
        <div class="tabs" role="tablist">
          <button
            class="tab"
            class:active={activeTab === 'url'}
            role="tab"
            aria-selected={activeTab === 'url'}
            onclick={() => { activeTab = 'url'; error = null; }}
          >
            URL
          </button>
          <button
            class="tab"
            class:active={activeTab === 'file'}
            role="tab"
            aria-selected={activeTab === 'file'}
            onclick={() => { activeTab = 'file'; error = null; }}
          >
            Upload File
          </button>
        </div>

        <!-- Error message -->
        {#if error}
          <div class="error-msg" transition:fade={{ duration: 150 }}>
            {error}
          </div>
        {/if}

      {#if existsSource}
        <div class="exists-msg" transition:fade={{ duration: 150 }}>
          <div class="exists-head">⚠ Source ini sudah ada di library</div>
          <div class="exists-url">{existsSource.youtube_url}</div>
          <button class="btn-primary exists-btn" onclick={openExisting}>Buka detail</button>
        </div>
      {/if}

      <!-- URL Tab -->
      {#if activeTab === 'url'}
        <div class="tab-content" role="tabpanel" transition:fade={{ duration: 150 }}>
          <label class="field">
            <span class="field-label">YouTube / TikTok / Instagram URL</span>
            <input
              class="inp"
              type="text"
              placeholder="https://youtube.com/watch?v=..."
              bind:value={urlInput}
              disabled={loading}
            />
          </label>

          <label class="field">
            <span class="field-label">Intent <span class="opt">(opsional)</span></span>
            <textarea
              class="inp inp-mono"
              placeholder="Instruksi analisis khusus (misal: fokus pada hook, retention)"
              bind:value={urlIntent}
              disabled={loading}
              rows="3"
            ></textarea>
          </label>

          <label class="field">
            <span class="field-label">Bikin prompt Suno (analisa audio) <span class="opt">(opsional)</span></span>
            <label class="checkbox-label">
              <input
                type="checkbox"
                bind:checked={includeAudio}
                disabled={loading}
              />
              <span>Clip audio → analisa → output Suno prompt</span>
            </label>
          </label>

          {#if includeAudio}
            <div class="audio-segment-container" transition:fade={{ duration: 150 }}>
              <label class="field">
                <span class="field-label">Segmen audio yang dipotong <span class="opt">(opsional — kosongkan = full)</span></span>
                <div class="audio-segment-inputs">
                  <input
                    class="inp inp-time"
                    type="number"
                    placeholder="Mulai (detik)"
                    bind:value={audioStart}
                    disabled={loading}
                    min="0"
                    step="0.1"
                  />
                  <span class="segment-dash">–</span>
                  <input
                    class="inp inp-time"
                    type="number"
                    placeholder="Akhir (detik)"
                    bind:value={audioEnd}
                    disabled={loading}
                    min="0"
                    step="0.1"
                  />
                </div>
              </label>
            </div>
          {/if}

          <label class="field">
            <span class="field-label">Output <span class="opt">(opsional)</span></span>
            <select
              class="inp"
              bind:value={outputFormat}
              disabled={loading}
            >
              <option value="none">None</option>
              <option value="prompt_video">Prompt video</option>
              <option value="prompt_json">Prompt JSON</option>
            </select>
          </label>
        </div>
      {/if}

      <!-- File Tab -->
      {#if activeTab === 'file'}
        <div class="tab-content" role="tabpanel" transition:fade={{ duration: 150 }}>
          <label class="field">
            <span class="field-label">Video File (mp4, mov, webm, mkv, m4v — max 200MB)</span>
            <input
              class="inp inp-file"
              type="file"
              accept="video/mp4, video/quicktime, video/webm, video/x-matroska, video/x-m4v, .mp4, .mov, .webm, .mkv, .m4v"
              onchange={handleFileSelect}
              disabled={loading}
              bind:this={fileInput}
            />
            {#if selectedFile}
              <div class="file-info">
                <span>{selectedFile.name}</span>
                <span class="file-size">{(selectedFile.size / 1024 / 1024).toFixed(1)} MB</span>
              </div>
            {/if}
          </label>

          <label class="field">
            <span class="field-label">Intent <span class="opt">(opsional)</span></span>
            <textarea
              class="inp inp-mono"
              placeholder="Instruksi analisis khusus"
              bind:value={fileIntent}
              disabled={loading}
              rows="3"
            ></textarea>
          </label>

          <label class="field">
            <span class="field-label">Bikin prompt Suno (analisa audio) <span class="opt">(opsional)</span></span>
            <label class="checkbox-label">
              <input
                type="checkbox"
                bind:checked={includeAudio}
                disabled={loading}
              />
              <span>Clip audio → analisa → output Suno prompt</span>
            </label>
          </label>

          {#if includeAudio}
            <div class="audio-segment-container" transition:fade={{ duration: 150 }}>
              <label class="field">
                <span class="field-label">Segmen audio yang dipotong <span class="opt">(opsional — kosongkan = full)</span></span>
                <div class="audio-segment-inputs">
                  <input
                    class="inp inp-time"
                    type="number"
                    placeholder="Mulai (detik)"
                    bind:value={audioStart}
                    disabled={loading}
                    min="0"
                    step="0.1"
                  />
                  <span class="segment-dash">–</span>
                  <input
                    class="inp inp-time"
                    type="number"
                    placeholder="Akhir (detik)"
                    bind:value={audioEnd}
                    disabled={loading}
                    min="0"
                    step="0.1"
                  />
                </div>
              </label>
            </div>
          {/if}

          <label class="field">
            <span class="field-label">Output <span class="opt">(opsional)</span></span>
            <select
              class="inp"
              bind:value={outputFormat}
              disabled={loading}
            >
              <option value="none">None</option>
              <option value="prompt_video">Prompt video</option>
              <option value="prompt_json">Prompt JSON</option>
            </select>
          </label>
        </div>
      {/if}
      {/if}
    </div>

    <!-- Footer -->
    <div class="m-footer">
      {#if analysisMode === 'gemini_mcp'}
        <span class="flow-label">Ambil instruksi → Tempel ke Antigravity</span>
        <button class="btn-cancel" onclick={closeModal} disabled={loading}>Batal</button>
      {:else if analysisMode === 'gemini_manual'}
        <span class="flow-label">Paste hasil Gemini → Simpan</span>
        <button class="btn-cancel" onclick={closeModal} disabled={savingGemini}>Batal</button>
        <button
          class="btn-primary"
          onclick={saveGeminiStoryboard}
          disabled={savingGemini || !geminiPaste.trim()}
        >
          {#if savingGemini}
            <span class="spinner"></span>
            Menyimpan…
          {:else}
            Simpan
          {/if}
        </button>
      {:else}
        <span class="flow-label">Input → Analyze{outputFormat === 'prompt_video' ? ' → Prompt video' : outputFormat === 'prompt_json' ? ' → Prompt JSON' : ''}</span>
        <button
          class="btn-cancel"
          onclick={closeModal}
          disabled={loading}
        >
          Batal
        </button>
        <button
          class="btn-primary"
          onclick={activeTab === 'url' ? submitUrl : submitFile}
          disabled={loading}
        >
          {#if loading}
            <span class="spinner"></span>
            Menganalisis...
          {:else}
            Analisis
          {/if}
        </button>
      {/if}
    </div>
  </div>

  <!-- Duplicate-URL confirm overlay — floats above the source modal -->
  {#if dupConfirm}
    <div
      class="dup-backdrop"
      transition:fade={{ duration: 150 }}
      onclick={cancelDup}
      aria-hidden="true"
    ></div>
    <div
      class="dup-card"
      role="alertdialog"
      aria-modal="true"
      aria-label="Konfirmasi duplikat"
      transition:scale={{ duration: 180, start: 0.95, easing: cubicOut }}
    >
      <div class="dup-head">⚠ Video ini sudah pernah dianalisa</div>
      <div class="dup-url">{dupConfirm.title || dupConfirm.youtube_url}</div>
      <div class="dup-actions">
        <button class="btn-primary" onclick={overrideExisting}>Timpa &amp; analisa ulang</button>
        <button class="btn-cancel" onclick={cancelDup}>Batal</button>
      </div>
    </div>
  {/if}
{/if}

<style>
  .backdrop {
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
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    z-index: 1000;
    max-width: 500px;
    width: 90%;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
  }

  .m-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border);
  }

  .m-title {
    font-weight: 600;
    font-size: 1.125rem;
  }

  .m-close {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--mut);
    transition: color 0.2s;
  }

  .m-close:hover {
    color: var(--fg);
  }

  .ic {
    width: 20px;
    height: 20px;
  }

  .m-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
  }

  .tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
  }

  .tab {
    background: none;
    border: none;
    padding: 0.75rem 1rem;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--mut);
    border-bottom: 2px solid transparent;
    transition: color 0.2s, border-color 0.2s;
    margin-bottom: -1px;
  }

  .tab:hover {
    color: var(--fg);
  }

  .tab.active {
    color: var(--fg);
    border-bottom-color: var(--accent);
  }

  .tab-content {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .error-msg {
    padding: 0.75rem 1rem;
    background: rgba(239, 68, 68, 0.1);
    color: #dc2626;
    border-radius: 4px;
    font-size: 0.875rem;
    margin-bottom: 1rem;
  }

  .exists-msg {
    padding: 0.75rem 1rem;
    background: rgba(64, 81, 137, 0.1);
    border: 1px solid rgba(64, 81, 137, 0.25);
    border-radius: 6px;
    margin-bottom: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .exists-head { font-weight: 600; font-size: 0.875rem; color: var(--accent); }
  .exists-url { font-size: 0.75rem; font-family: 'Monaco', monospace; word-break: break-all; opacity: 0.8; }
  .exists-btn { align-self: flex-start; }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .field-label {
    font-weight: 500;
    font-size: 0.875rem;
    color: var(--fg);
  }

  .opt {
    font-weight: normal;
    color: var(--mut);
  }

  .inp {
    padding: 0.625rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--fg);
    font-size: 0.875rem;
    font-family: inherit;
    transition: border-color 0.2s;
  }

  .inp:focus {
    outline: none;
    border-color: var(--accent);
  }

  .inp:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .inp-mono {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.8125rem;
  }

  .inp-file {
    cursor: pointer;
  }

  .file-info {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    background: rgba(59, 130, 246, 0.05);
    border-radius: 4px;
    font-size: 0.8125rem;
    color: var(--mut);
  }

  .file-size {
    color: var(--accent);
  }

  .flow-label {
    margin-right: auto;
    align-self: center;
    font-size: 0.75rem;
    color: var(--muted, #888);
    white-space: nowrap;
  }

  .m-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid var(--border);
    justify-content: flex-end;
  }

  .btn-cancel,
  .btn-primary {
    padding: 0.625rem 1rem;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
  }

  .btn-cancel {
    background: var(--bg-alt);
    color: var(--fg);
    border: 1px solid var(--border);
  }

  .btn-cancel:hover:not(:disabled) {
    background: var(--border);
  }

  .btn-primary {
    background: var(--accent);
    color: white;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .btn-primary:hover:not(:disabled) {
    opacity: 0.9;
  }

  .btn-cancel:disabled,
  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: white;
    animation: spin 0.6s linear infinite;
  }

  .spinner-sm {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 1.5px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: white;
    animation: spin 0.6s linear infinite;
    margin-right: 0.25rem;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .prep-stepper {
    display: flex; flex-direction: column; gap: 8px;
    padding: 14px 16px; background: var(--soft, #f1f5f9);
    border: 1px solid var(--line, #e2e8f0); border-radius: 8px;
  }
  .prep-hd { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
  .prep-title { font-size: 14px; font-weight: 600; }
  .prep-elapsed { font-size: 12px; color: var(--mut, #64748b); }
  .prep-step { display: flex; align-items: center; gap: 10px; font-size: 13px; }
  .prep-icon {
    width: 18px; height: 18px; flex-shrink: 0;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .prep-step.pending { color: var(--mut, #94a3b8); }
  .prep-step.pending .prep-icon { color: var(--mut, #cbd5e1); }
  .prep-step.active { color: var(--txt, #0f172a); font-weight: 600; }
  .prep-step.done { color: #16a34a; }
  .prep-step.done .prep-icon { color: #16a34a; font-weight: 700; }
  .prep-step .spinner-sm {
    width: 14px; height: 14px; border-width: 2px;
    border-color: rgba(107,70,193,.25); border-top-color: #6b46c1; margin: 0;
  }

  /* Analysis mode selector */
  .analysis-mode-selector {
    margin-bottom: 1.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
  }

  .mode-options {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .mode-option {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    padding: 0.5rem;
    border-radius: 4px;
    transition: background-color 0.2s;
  }

  .mode-option:hover {
    background-color: var(--bg-alt);
  }

  .mode-option input[type="radio"] {
    cursor: pointer;
  }

  .mode-option input[type="radio"]:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .mode-label {
    font-size: 0.875rem;
    color: var(--fg);
    font-weight: 500;
    cursor: pointer;
  }

  /* Gemini section */
  .gemini-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .btn-fetch-brief {
    padding: 0.625rem 1rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }

  .btn-fetch-brief:hover:not(:disabled) {
    opacity: 0.9;
  }

  .btn-fetch-brief:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .brief-box {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 1rem;
    background: var(--bg-alt);
    border-radius: 6px;
    border: 1px solid var(--border);
  }

  .inp-brief {
    min-height: 200px;
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.75rem;
    resize: vertical;
  }

  .btn-copy {
    padding: 0.5rem 0.75rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.2s;
    align-self: flex-start;
  }

  .btn-copy:hover {
    opacity: 0.9;
  }

  .brief-note {
    font-size: 0.75rem;
    color: var(--mut);
    line-height: 1.4;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.875rem;
  }

  .checkbox-label input[type="checkbox"] {
    cursor: pointer;
  }

  .checkbox-label span {
    cursor: pointer;
  }

  .audio-segment-container {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--bg-alt);
    border-radius: 4px;
  }

  .audio-segment-inputs {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .inp-time {
    flex: 1;
  }

  .segment-dash {
    color: var(--mut);
    font-size: 0.875rem;
  }

  /* Duplicate-URL confirm sub-overlay */
  .dup-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 1001;
  }

  .dup-card {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 1002;
    background: var(--bg);
    border-radius: 8px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
    padding: 1.5rem;
    max-width: 380px;
    width: 90%;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .dup-head {
    font-weight: 600;
    font-size: 0.9375rem;
    color: var(--accent);
  }

  .dup-url {
    font-size: 0.8125rem;
    font-family: 'Monaco', monospace;
    word-break: break-all;
    color: var(--mut);
    line-height: 1.4;
  }

  .dup-actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 0.25rem;
  }
</style>
