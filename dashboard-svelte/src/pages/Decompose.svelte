<script>
  import { api } from '../lib/api.js'

  let url = $state('')
  let loading = $state(false)
  let stage = $state('')
  let segments = $state([])
  let error = $state(null)
  let timer = null

  const STAGE_LABELS = {
    started: 'Mulai…',
    downloading: 'Mengunduh video…',
    detecting: 'Mendeteksi scene…',
    grouping: 'Mengelompokkan shot…',
    finding: 'Mencari kredit…',
    splitting: 'Memotong segmen…',
    saving: 'Menyimpan…',
    done: 'Selesai',
    error: 'Error'
  }

  function stopPoll() {
    if (timer) { clearInterval(timer); timer = null }
  }

  async function pollStatus(run_id) {
    const res = await api.decomposeStatus(run_id)
    if (!res) return
    stage = res.current_stage || res.status
    if (res.status === 'done') {
      stopPoll()
      loading = false
      segments = res.segments || []
    } else if (res.status === 'error') {
      stopPoll()
      loading = false
      error = res.error || 'Terjadi kesalahan.'
    }
  }

  async function handleSubmit() {
    if (!url.trim()) return
    stopPoll()
    loading = true
    error = null
    segments = []
    stage = ''
    const res = await api.decompose(url.trim())
    if (!res || !res.run_id) {
      loading = false
      error = res?.detail || res?.error || 'Request gagal — cek koneksi / service.'
      return
    }
    stage = 'started'
    // Poll every 4.5s
    timer = setInterval(() => pollStatus(res.run_id), 4500)
    // Also poll immediately
    pollStatus(res.run_id)
  }

  function statusBadgeClass(s) {
    if (s === 'found') return 'badge-found'
    if (s === 'not_found') return 'badge-notfound'
    return 'badge-pending'
  }

  function fmtSec(s) {
    return typeof s === 'number' ? s.toFixed(1) : s
  }
</script>

<div class="top">
  <div><h1>Pecah Kompilasi</h1><div class="sub">Pecah video kompilasi YouTube menjadi segmen-segmen dengan kredit asli</div></div>
  {#if segments.length}<div class="pill">{segments.length} segmen</div>{/if}
</div>

<div class="filters">
  <div class="input-group">
    <input
      placeholder="YouTube URL kompilasi…"
      bind:value={url}
      disabled={loading}
      onkeydown={(e) => e.key === 'Enter' && handleSubmit()}
    />
    <button onclick={handleSubmit} disabled={loading || !url.trim()}>
      {loading ? 'Memproses…' : 'Pecah'}
    </button>
  </div>
</div>

{#if loading}
  <div class="card">
    <div class="loading-state">
      <div class="spinner"></div>
      <div class="loading-text">{STAGE_LABELS[stage] || stage || 'Memproses…'}</div>
      <div class="loading-sub">Proses ini bisa memakan beberapa menit. Sabar ya.</div>
    </div>
  </div>
{:else if error}
  <div class="card">
    <div class="error-msg">{error}</div>
  </div>
{:else if segments.length}
  <div class="card">
    <div class="seg-list">
      {#each segments as seg}
        <div class="seg-card">
          <div class="seg-header">
            <span class="seg-title">Klip {seg.clip_index}</span>
            <span class="seg-time">{fmtSec(seg.start_sec)}–{fmtSec(seg.end_sec)} dtk</span>
            <span class="badge {statusBadgeClass(seg.origin_status)}">{seg.origin_status}</span>
          </div>
          <div class="seg-meta">
            <span class="seg-credit">{seg.credit_handle || '—'}</span>
            {#if seg.original_url}
              <a href={seg.original_url} target="_blank" rel="noopener noreferrer">Lihat asli</a>
            {:else}
              <span class="mut">belum ketemu</span>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
{:else}
  <div class="card">
    <div class="empty">
      <div class="empty-text">Masukkan URL kompilasi di atas, lalu tekan Pecah.</div>
    </div>
  </div>
{/if}

<style>
  .top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }
  .top > div:first-child { flex: 1; }
  h1 { margin: 0 0 6px 0; font-size: 28px; font-weight: 600; }
  .sub { font-size: 14px; color: #666; margin: 0; }
  .pill {
    background: #f0f0f0; border-radius: 20px;
    padding: 6px 16px; font-size: 13px; font-weight: 500; color: #333; white-space: nowrap;
  }
  .filters { margin-bottom: 20px; }
  .input-group { display: flex; gap: 8px; align-items: center; }
  input {
    flex: 1; padding: 8px 12px; border: 1px solid #ddd;
    border-radius: 6px; font-size: 14px; font-family: inherit;
  }
  button {
    padding: 8px 16px; background: #2563eb; color: white; border: none;
    border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer;
    white-space: nowrap; transition: background 200ms;
  }
  button:hover:not(:disabled) { background: #1d4ed8; }
  button:disabled { background: #ccc; cursor: not-allowed; }
  .card {
    background: white; border: 1px solid #e0e0e0;
    border-radius: 8px; padding: 16px; overflow-x: auto;
  }
  .loading-state {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 48px 16px; gap: 12px;
  }
  .spinner {
    width: 32px; height: 32px;
    border: 3px solid rgba(37,99,235,0.15); border-top-color: #2563eb;
    border-radius: 50%; animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { font-weight: 600; color: #333; }
  .loading-sub { font-size: 12px; color: #999; }
  .error-msg {
    padding: 12px 16px; border-radius: 6px;
    background: #fff3cd; color: #92400e;
    border: 1px solid #fcd34d; font-size: 14px;
  }
  .empty { text-align: center; padding: 48px 20px; color: #999; }
  .empty-text { font-size: 15px; }
  .seg-list { display: flex; flex-direction: column; gap: 10px; }
  .seg-card {
    border: 1px solid #e0e0e0; border-radius: 6px;
    padding: 12px 14px; display: flex; flex-direction: column; gap: 6px;
  }
  .seg-header {
    display: flex; align-items: center; gap: 10px;
    font-size: 14px; font-weight: 600;
  }
  .seg-title { color: #222; }
  .seg-time { font-size: 12px; color: #666; font-weight: 400; margin-left: auto; }
  .badge {
    font-size: 11px; font-weight: 600; padding: 2px 8px;
    border-radius: 10px; text-transform: lowercase;
  }
  .badge-found { background: #dcfce7; color: #166534; }
  .badge-notfound { background: #f0f0f0; color: #666; }
  .badge-pending { background: #fef9c3; color: #854d0e; }
  .seg-meta { display: flex; align-items: center; gap: 12px; font-size: 13px; }
  .seg-credit { color: #444; }
  .mut { color: #aaa; }
  a { color: #2563eb; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
