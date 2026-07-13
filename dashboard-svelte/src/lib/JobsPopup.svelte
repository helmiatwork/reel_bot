<script>
  import { fade, scale } from 'svelte/transition'
  import { cubicOut } from 'svelte/easing'
  import { untrack } from 'svelte'
  import { api } from './api.js'
  import { onDestroy } from 'svelte'
  import AnalyzeStepper from './AnalyzeStepper.svelte'

  // Props (runes mode — isOpen is bound by parent)
  // initialRunId: when set before open, auto-focuses the detail view for that run
  let { isOpen = $bindable(false), initialRunId = $bindable(null) } = $props()

  // Modal state
  let jobs = $state([])
  let selectedRunId = $state(null)
  let selectedJobDetail = $state(null)
  let pollListInterval = null
  let pollDetailInterval = null
  let panelEl = $state(null)
  let detailLoading = $state(false)

  $effect(() => {
    if (isOpen) {
      // Read initialRunId without tracking it — we only want this effect to
      // re-run on isOpen changes, not on every initialRunId change.
      const autoSelect = untrack(() => {
        const r = initialRunId
        initialRunId = null  // clear after use so next manual open is clean
        return r
      })
      openModal(autoSelect)
    } else {
      closeModal()
    }
  })

  // Clear polls if the component is destroyed while open (e.g. navigate away)
  onDestroy(() => {
    if (pollListInterval) clearInterval(pollListInterval)
    if (pollDetailInterval) clearInterval(pollDetailInterval)
  })

  function openModal(autoSelect = null) {
    selectedRunId = autoSelect
    selectedJobDetail = null
    jobs = []
    pollList()
    pollListInterval = setInterval(pollList, 2000)
    if (autoSelect) {
      detailLoading = true
      pollJobDetail()
      pollDetailInterval = setInterval(pollJobDetail, 1200)
    }
  }

  function closeModal() {
    if (pollListInterval) clearInterval(pollListInterval)
    if (pollDetailInterval) clearInterval(pollDetailInterval)
    isOpen = false
  }

  function onBackdropClick(e) {
    if (e.target === e.currentTarget) closeModal()
  }

  function onKey(e) {
    if (!isOpen) return
    if (e.key === 'Escape') closeModal()
  }

  async function pollList() {
    try {
      const [data, srcTable] = await Promise.all([
        api.analyzeRuns(20),
        api.table('sources', 50, 0).catch(() => null),
      ])
      // Map youtube_url → live source status so a decompose row keeps showing
      // "processing/working" until the source is fully analyzed (Gemini done),
      // instead of flipping to "done" the moment the fast clip-cut finishes.
      const statusByUrl = {}
      if (srcTable?.rows) for (const r of srcTable.rows) statusByUrl[r.youtube_url] = r.status
      if (data) jobs = data.map((j) => ({ ...j, sourceStatus: statusByUrl[j.url] || null }))
    } catch (e) {
      console.error('[pollList] error:', e)
    }
  }

  // Live label for a job: prefer the source's overall status (processing → working →
  // analyzed) over the transient run status. Returns null to fall back to run status.
  function jobLive(job) {
    const ss = job.sourceStatus
    if (!ss) return null
    if (ss === 'analyzed') return { text: 'Selesai', active: false }
    if (ss === 'working') return { text: 'Gemini (Antigravity) bekerja…', active: true }
    if (ss === 'processing') return { text: 'Sedang diproses…', active: true }
    return null
  }

  function selectJob(run) {
    selectedRunId = run.run_id
    selectedJobDetail = null
    detailLoading = true
    if (pollDetailInterval) clearInterval(pollDetailInterval)
    pollJobDetail()
    pollDetailInterval = setInterval(pollJobDetail, 1200)
  }

  async function pollJobDetail() {
    if (!selectedRunId) return
    try {
      const data = await api.analyzeClaudeStatus(selectedRunId)
      if (data) {
        selectedJobDetail = data
        detailLoading = false
      }
    } catch (e) {
      console.error('[pollDetail] error:', e)
    }
  }

  function getStatusColor(status) {
    if (status === 'running') return 'accent'
    if (status === 'done') return 'green'
    if (status === 'error') return 'red'
    return 'gray'
  }

  function getDecomposeStageLabel(stage) {
    const stageMap = {
      'downloading': 'Mengunduh video…',
      'detecting': 'Mendeteksi scene…',
      'grouping': 'Mengelompokkan…',
      'splitting': 'Memotong klip per menit…',
      'finding': 'Menautkan klip…',
      'saving': 'Menyimpan…',
      'done': 'Selesai',
      'error': 'Gagal'
    }
    return stageMap[stage] || stage
  }

  // Same prep checklist as the Add-Source form, so the detail view matches.
  const PREP_STEPS = [
    { key: 'saving_meta', label: 'Menyimpan atribut video' },
    { key: 'downloading', label: 'Mengunduh video' },
    { key: 'splitting', label: 'Memotong klip per menit' },
    { key: 'saving', label: 'Menyimpan atribut klip ke database' },
  ]
  const PREP_STAGE_ORDER = { saving_meta: 0, downloading: 1, detecting: 2, grouping: 2, splitting: 2, finding: 3, saving: 3, done: 4, analyzed: 4 }
  function prepStepStatus(cur, key) {
    const c = PREP_STAGE_ORDER[cur] ?? 0
    const idx = PREP_STEPS.findIndex((s) => s.key === key)
    if (c > idx) return 'done'
    if (c === idx) return 'active'
    return 'pending'
  }

  function truncateUrl(url) {
    if (!url) return '—'
    if (url.startsWith('file://')) return 'Uploaded file'
    if (url.length > 50) return url.substring(0, 47) + '…'
    return url
  }

  function formatRelativeTime(timestamp) {
    if (!timestamp) return ''
    const now = Date.now()
    const then = timestamp * 1000
    const diff = now - then
    const secs = Math.floor(diff / 1000)
    const mins = Math.floor(secs / 60)
    const hours = Math.floor(mins / 60)

    if (secs < 60) return `${secs}s ago`
    if (mins < 60) return `${mins}m ago`
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  function copyPrompt() {
    if (!selectedJobDetail?.result?.gen_prompt) return
    const text = JSON.stringify(selectedJobDetail.result.gen_prompt, null, 2)
    navigator.clipboard.writeText(text)
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
    aria-label="Proses"
    tabindex="-1"
    transition:scale={{ duration: 230, start: 0.94, easing: cubicOut }}
  >
    <!-- Header -->
    <div class="m-head">
      <span class="m-title">Proses</span>
      <button class="m-close" onclick={closeModal} aria-label="Tutup modal">
        <svg class="ic"><use href="#i-x"/></svg>
      </button>
    </div>

    <!-- Body: List + Detail split view -->
    <div class="m-body">
      {#if !selectedRunId}
        <!-- Jobs List View -->
        <div class="jobs-list" transition:fade={{ duration: 150 }}>
          {#if jobs.length > 0}
            {#each jobs as job (job.run_id)}
              <div
                class="job-row"
                onclick={() => selectJob(job)}
              >
                {#if job.kind === 'decompose'}
                  <!-- Decompose run: reflect the source's live status (processing → working → done) -->
                  {@const live = jobLive(job)}
                  <div class="job-main">
                    <div class="job-url">{job.title || truncateUrl(job.url)}</div>
                    <div class="job-meta">
                      <span class="decompose-stage">
                        {#if live?.active}<span class="spin"></span>{/if}
                        {live ? live.text : getDecomposeStageLabel(job.current_stage)}
                      </span>
                      <span class="time">{formatRelativeTime(job.created)}</span>
                    </div>
                  </div>
                {:else}
                  <!-- Analyze run: status badge + format -->
                  <div class="job-main">
                    <div class="job-url">{job.title || truncateUrl(job.url)}</div>
                    <div class="job-meta">
                      <span class={`status-chip status-${getStatusColor(job.status)}`}>
                        {job.status}
                      </span>
                      {#if job.output_format && job.output_format !== 'none'}
                        <span class={`format-badge format-${job.output_format}`}>
                          {job.output_format === 'prompt_json' ? 'JSON' : 'Text'}
                        </span>
                      {/if}
                      <span class="time">{formatRelativeTime(job.created)}</span>
                    </div>
                    <div class="job-msg">{job.last_msg}</div>
                  </div>
                {/if}
              </div>
            {/each}
          {:else}
            <div class="empty">Belum ada proses</div>
          {/if}
        </div>
      {:else}
        <!-- Job Detail View -->
        <div class="job-detail" transition:fade={{ duration: 150 }}>
          <!-- Back button + title -->
          <div class="detail-header">
            <button class="back-btn" onclick={() => { selectedRunId = null; if (pollDetailInterval) clearInterval(pollDetailInterval) }}>
              ← Kembali
            </button>
            <div class="detail-status">
              {#if selectedJobDetail?.kind === 'decompose'}
                <span class="decompose-stage">
                  {getDecomposeStageLabel(selectedJobDetail?.current_stage || 'unknown')}
                </span>
              {:else}
                <span class={`status-chip status-${getStatusColor(selectedJobDetail?.status || 'unknown')}`}>
                  {selectedJobDetail?.status || 'unknown'}
                </span>
              {/if}
            </div>
          </div>

          <!-- Analyze stepper (only for analyze_source runs) -->
          {#if selectedJobDetail?.kind !== 'decompose' && selectedJobDetail?.log}
            <AnalyzeStepper logs={selectedJobDetail.log} />
          {/if}

          <!-- Decompose stage info -->
          {#if selectedJobDetail?.kind === 'decompose'}
            <div class="decompose-detail">
              {@const cur = selectedJobDetail?.current_stage || 'saving_meta'}
              <div class="prep-stepper">
                {#each PREP_STEPS as step}
                  {@const st = prepStepStatus(cur, step.key)}
                  <div class="prep-step {st}">
                    <span class="prep-icon">
                      {#if st === 'done'}✓{:else if st === 'active'}<span class="spinner-sm"></span>{:else}○{/if}
                    </span>
                    <span class="prep-label">{step.label}</span>
                  </div>
                {/each}
              </div>
              {#if selectedJobDetail?.interval_sec}
                <div class="detail-section">
                  <span class="field-label">Interval</span>
                  <div class="field-value">{selectedJobDetail.interval_sec}s per clip</div>
                </div>
              {/if}
              {#if selectedJobDetail?.segments && selectedJobDetail.segments.length > 0}
                <div class="detail-section">
                  <span class="field-label">Clips Found</span>
                  <div class="field-value">{selectedJobDetail.segments.length}</div>
                </div>
              {/if}
            </div>
          {/if}

          <!-- Result display (if done) -->
          {#if selectedJobDetail?.result}
            <div class="result-section">
              <div class="result-title">Result</div>

              <!-- Summary fields -->
              {#if selectedJobDetail.result.hook}
                <div class="result-field">
                  <span class="field-label">Hook</span>
                  <div class="field-value">{selectedJobDetail.result.hook}</div>
                </div>
              {/if}

              {#if selectedJobDetail.result.tags && selectedJobDetail.result.tags.length > 0}
                <div class="result-field">
                  <span class="field-label">Tags</span>
                  <div class="tags">
                    {#each selectedJobDetail.result.tags as tag}
                      <span class="tag">{tag}</span>
                    {/each}
                  </div>
                </div>
              {/if}

              {#if selectedJobDetail.result.retention}
                <div class="result-field">
                  <span class="field-label">Retention</span>
                  <div class="field-value">{selectedJobDetail.result.retention}</div>
                </div>
              {/if}

              {#if selectedJobDetail.result.structure}
                <div class="result-field">
                  <span class="field-label">Structure</span>
                  <div class="field-value">{selectedJobDetail.result.structure}</div>
                </div>
              {/if}

              <!-- Gen prompt if present -->
              {#if selectedJobDetail.result.gen_prompt}
                <div class="result-field">
                  <div style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem">
                    <span class="field-label">Gen Prompt</span>
                    <button class="copy-btn" onclick={copyPrompt} title="Copy prompt">
                      <svg style="width: 14px; height: 14px"><use href="#i-copy"/></svg>
                    </button>
                  </div>
                  <pre class="prompt-display">{JSON.stringify(selectedJobDetail.result.gen_prompt, null, 2)}</pre>
                </div>
              {/if}

              <!-- Metadata -->
              <div class="result-meta">
                {#if selectedJobDetail.result.cost_usd}
                  <span class="meta-item">Cost: ${selectedJobDetail.result.cost_usd.toFixed(3)}</span>
                {/if}
                {#if selectedJobDetail.result.model}
                  <span class="meta-item">Model: {selectedJobDetail.result.model}</span>
                {/if}
              </div>
            </div>
          {/if}

          <!-- Error display -->
          {#if selectedJobDetail?.error}
            <div class="error-section">
              <div class="error-title">Error</div>
              <div class="error-text">{selectedJobDetail.error}</div>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Footer -->
    <div class="m-footer">
      <button class="btn-close" onclick={closeModal}>
        Tutup
      </button>
    </div>
  </div>
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
    max-width: 700px;
    width: 90%;
    max-height: 85vh;
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
    padding: 1rem;
    overflow-y: auto;
    flex: 1;
  }

  .jobs-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .job-row {
    padding: 0.875rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
  }

  .job-row:hover {
    background: var(--bg-alt);
    border-color: var(--accent);
  }

  .job-main {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .job-url {
    font-weight: 500;
    font-size: 0.9375rem;
    color: var(--fg);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .job-meta {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
    font-size: 0.8125rem;
  }

  .status-chip {
    padding: 0.25rem 0.625rem;
    border-radius: 3px;
    font-weight: 500;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .status-accent {
    background: rgba(59, 130, 246, 0.2);
    color: var(--accent);
  }

  .status-green {
    background: rgba(34, 197, 94, 0.2);
    color: #22c55e;
  }

  .status-red {
    background: rgba(239, 68, 68, 0.2);
    color: #ef4444;
  }

  .status-gray {
    background: rgba(107, 114, 128, 0.2);
    color: #6b7280;
  }

  .format-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .format-prompt_json {
    background: rgba(59, 130, 246, 0.1);
    color: var(--accent);
  }

  .format-prompt_video {
    background: rgba(168, 85, 247, 0.1);
    color: #a855f7;
  }

  .format-decompose {
    background: rgba(34, 197, 94, 0.1);
    color: #22c55e;
  }

  .decompose-stage {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 0.25rem 0.625rem;
    border-radius: 3px;
    font-weight: 500;
    font-size: 0.75rem;
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    white-space: nowrap;
  }
  .decompose-stage .spin {
    width: 9px;
    height: 9px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    display: inline-block;
    animation: spin 0.7s linear infinite;
  }
  .prep-stepper {
    display: flex; flex-direction: column; gap: 8px;
    padding: 14px 16px; background: var(--soft, #f1f5f9);
    border: 1px solid var(--line, #e2e8f0); border-radius: 8px; margin-bottom: 12px;
  }
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
    width: 14px; height: 14px; border: 2px solid rgba(107,70,193,.25);
    border-top-color: #6b46c1; border-radius: 50%; display: inline-block;
    animation: spin 0.8s linear infinite;
  }

  .time {
    color: var(--mut);
    margin-left: auto;
  }

  .job-msg {
    font-size: 0.8125rem;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .empty {
    padding: 2rem;
    text-align: center;
    color: var(--mut);
  }

  /* Detail view */
  .job-detail {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .detail-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
  }

  .back-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--accent);
    font-weight: 500;
    font-size: 0.875rem;
    transition: opacity 0.2s;
  }

  .back-btn:hover {
    opacity: 0.8;
  }

  .detail-status {
    margin-left: auto;
  }

  .result-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .result-title {
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--fg);
  }

  .result-field {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .field-label {
    font-weight: 500;
    font-size: 0.8125rem;
    color: var(--fg);
  }

  .field-value {
    font-size: 0.875rem;
    color: var(--fg);
    line-height: 1.5;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
  }

  .tag {
    display: inline-block;
    padding: 0.25rem 0.625rem;
    background: rgba(59, 130, 246, 0.1);
    color: var(--accent);
    border-radius: 3px;
    font-size: 0.75rem;
  }

  .prompt-display {
    max-height: 200px;
    overflow-y: auto;
    background: rgba(0, 0, 0, 0.3);
    color: #0f0;
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.75rem;
    padding: 0.75rem;
    border-radius: 4px;
    margin: 0;
    line-height: 1.4;
  }

  .copy-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--accent);
    padding: 0;
    display: flex;
    align-items: center;
    transition: opacity 0.2s;
  }

  .copy-btn:hover {
    opacity: 0.8;
  }

  .result-meta {
    display: flex;
    gap: 1.5rem;
    font-size: 0.8125rem;
    color: var(--mut);
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
  }

  .meta-item {
    display: flex;
    align-items: center;
  }

  .error-section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 1rem;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid #ef4444;
    border-radius: 4px;
  }

  .error-title {
    font-weight: 600;
    font-size: 0.875rem;
    color: #ef4444;
  }

  .error-text {
    font-size: 0.8125rem;
    color: #dc2626;
    line-height: 1.4;
  }

  .m-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid var(--border);
    justify-content: flex-end;
  }

  .btn-close {
    padding: 0.625rem 1rem;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    border: none;
    background: var(--bg-alt);
    color: var(--fg);
    border: 1px solid var(--border);
    transition: all 0.2s;
  }

  .btn-close:hover {
    background: var(--border);
  }

  .decompose-detail {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .detail-section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
</style>
