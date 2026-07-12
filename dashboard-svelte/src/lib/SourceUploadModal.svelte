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

  // Set when the submitted URL is already in the library
  let existsSource = $state(null)

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
      error = null
      loading = false
      activeTab = 'url'
      existsSource = null
    }
  })

  function openExisting() {
    onAlreadyExists(existsSource)
    closeModal()
  }

  function closeModal() {
    isOpen = false
    setTimeout(() => triggerEl?.focus(), 50)
  }

  function onBackdropClick(e) {
    if (e.target === e.currentTarget) closeModal()
  }

  function onKey(e) {
    if (!isOpen) return
    if (e.key === 'Escape') closeModal()
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
    loading = true
    error = null
    existsSource = null
    try {
      const result = await api.analyzeClaudeAsync(urlInput.trim(), { intent: urlIntent, output_format: outputFormat })
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
      const result = await api.uploadSourceAsync(selectedFile, { intent: fileIntent, output_format: outputFormat })
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
    </div>

    <!-- Footer -->
    <div class="m-footer">
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

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
