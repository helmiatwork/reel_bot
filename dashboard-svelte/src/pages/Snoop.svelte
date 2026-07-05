<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'

  let targets = $state([])
  let results = $state([])
  let channel = $state('')
  let loading = $state(false)
  let error = $state(null)

  function latestResult(cid) {
    return results.find((r) => r.channel_id === cid) || null
  }
  function recommendedClip(clips) {
    if (!Array.isArray(clips) || !clips.length) return null
    return clips.find((c) => c.recommended) || clips[0]
  }
  function fmtTime(s) {
    const n = Number(s) || 0
    const m = Math.floor(n / 60)
    const x = Math.floor(n % 60)
    return `${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`
  }
  function fmtDate(iso) {
    if (!iso) return '-'
    try {
      return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: '2-digit', year: '2-digit' })
    } catch {
      return String(iso).slice(0, 10)
    }
  }

  async function load() {
    const t = await api.snoopTargets()
    targets = t?.targets || []
    const r = await api.snoopResults()
    results = r?.results || []
  }

  async function addTarget() {
    if (!channel.trim()) return
    loading = true
    error = null
    try {
      const res = await api.addSnoopTarget(channel.trim())
      if (!res) {
        error = 'Gagal menambah target — cek koneksi / service.'
        return
      }
      if (res.detail) {
        error = res.detail
        return
      }
      channel = ''
      await load()
    } finally {
      loading = false
    }
  }

  async function removeTarget(cid) {
    await api.removeSnoopTarget(cid)
    await load()
  }

  onMount(load)

  let today = $derived(new Date().toISOString().slice(0, 10))
  let newToday = $derived(results.filter((r) => String(r.created_at || '').slice(0, 10) === today).length)
  let clipTotal = $derived(results.reduce((n, r) => n + (Array.isArray(r.clips) ? r.clips.length : 0), 0))
</script>

<div class="top">
  <div>
    <h1>Snoop</h1>
    <p class="sub">Mengintip target channel — tiap ada upload baru, videonya otomatis di-clip.</p>
  </div>
  <div class="pill">{targets.length} target</div>
</div>

<div class="metrics">
  <div class="metric"><div class="ml">Target dipantau</div><div class="mv">{targets.length}</div></div>
  <div class="metric"><div class="ml">Upload baru hari ini</div><div class="mv">{newToday}</div></div>
  <div class="metric"><div class="ml">Clip dibuat</div><div class="mv">{clipTotal}</div></div>
</div>

<div class="input-group">
  <input
    type="text"
    placeholder="@channel atau URL YouTube…"
    bind:value={channel}
    disabled={loading}
    onkeydown={(e) => e.key === 'Enter' && addTarget()}
  />
  <button onclick={addTarget} disabled={loading || !channel.trim()}>
    {loading ? 'menambah…' : 'Tambah target'}
  </button>
</div>
<div class="schedule">Cek otomatis harian 08:00 (n8n) · videonya di-clip pakai Claude Sonnet</div>

{#if error}
  <div class="error-msg">{error}</div>
{/if}

<div class="list">
  {#if targets.length === 0}
    <div class="empty">
      <div class="empty-icon">🕵️</div>
      <div class="empty-text">Belum ada target. Tambah channel di atas buat mulai mengintip.</div>
    </div>
  {:else}
    {#each targets as t (t.channel_id)}
      {@const res = latestResult(t.channel_id)}
      {@const rec = res ? recommendedClip(res.clips) : null}
      <div class="card">
        <div class="row">
          <div class="who">
            <div class="avatar">{(t.handle || t.channel_id || '?').replace('@', '').slice(0, 2).toUpperCase()}</div>
            <div>
              <div class="name">{t.handle || t.channel_id}</div>
              <div class="meta">{t.runs || 0} run · {res ? `terakhir ${fmtDate(res.created_at)}` : 'belum ada upload terdeteksi'}</div>
            </div>
          </div>
          <div class="right">
            {#if res}
              <span class="badge ok">upload baru · {Array.isArray(res.clips) ? res.clips.length : 0} clip</span>
            {:else}
              <span class="badge wait">menunggu upload</span>
            {/if}
            <button class="icon" title="Hapus target" onclick={() => removeTarget(t.channel_id)}>✕</button>
          </div>
        </div>

        {#if res}
          <div class="video">▶ {res.video_title || res.video_id}</div>
          {#if rec}
            <div class="rec">
              <div class="rec-head">
                <span class="rec-badge">★ Recommended</span>
                <span class="rec-time">{fmtTime(rec.start_sec)} – {fmtTime(rec.end_sec)}</span>
              </div>
              <div class="rec-title">{rec.title || '(untitled clip)'}</div>
              {#if rec.why}<div class="rec-why">{rec.why}</div>{/if}
            </div>
            {#if Array.isArray(res.clips) && res.clips.length > 1}
              <div class="more">+ {res.clips.length - 1} clip lainnya</div>
            {/if}
          {/if}
        {/if}
      </div>
    {/each}
  {/if}
</div>

<style>
  .top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  h1 { margin: 0 0 6px 0; font-size: 28px; font-weight: 600; }
  .sub { font-size: 14px; color: #666; margin: 0; }
  .pill { background: #f0f0f0; border-radius: 20px; padding: 6px 16px; font-size: 13px; font-weight: 500; color: #333; white-space: nowrap; }
  .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
  .metric { background: #f7f7f5; border-radius: 8px; padding: 14px 16px; }
  .ml { font-size: 13px; color: #666; }
  .mv { font-size: 24px; font-weight: 600; color: #222; }
  .input-group { display: flex; gap: 8px; align-items: center; }
  input[type='text'] { flex: 1; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; font-family: inherit; }
  button { padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; white-space: nowrap; }
  button:hover:not(:disabled) { background: #1d4ed8; }
  button:disabled { background: #ccc; cursor: not-allowed; }
  .schedule { font-size: 12px; color: #999; margin: 8px 0 20px; }
  .error-msg { background: #fef3c7; border: 1px solid #f59e0b; color: #92400e; border-radius: 8px; padding: 12px 16px; font-size: 14px; margin-bottom: 16px; }
  .list { display: flex; flex-direction: column; gap: 12px; }
  .card { background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 16px 20px; }
  .row { display: flex; justify-content: space-between; align-items: center; }
  .who { display: flex; align-items: center; gap: 12px; }
  .avatar { width: 36px; height: 36px; border-radius: 50%; background: #e6f0ff; color: #2563eb; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 13px; }
  .name { font-weight: 600; font-size: 15px; color: #222; }
  .meta { font-size: 12px; color: #999; }
  .right { display: flex; align-items: center; gap: 10px; }
  .badge { font-size: 12px; padding: 3px 10px; border-radius: 999px; }
  .badge.ok { background: #dcfce7; color: #166534; }
  .badge.wait { background: #f0f0f0; color: #666; }
  .icon { background: none; color: #bbb; padding: 2px 6px; font-size: 14px; }
  .icon:hover:not(:disabled) { background: none; color: #ef4444; }
  .video { margin-top: 10px; font-size: 13px; color: #555; }
  .rec { margin-top: 10px; border: 2px solid #2563eb; border-radius: 8px; padding: 10px 12px; }
  .rec-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .rec-badge { background: #e6f0ff; color: #2563eb; font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 500; }
  .rec-time { font-size: 12px; color: #999; }
  .rec-title { font-weight: 600; font-size: 14px; color: #222; }
  .rec-why { font-size: 12px; color: #666; margin-top: 2px; }
  .more { margin-top: 8px; font-size: 12px; color: #2563eb; }
  .empty { text-align: center; padding: 48px 16px; }
  .empty-icon { font-size: 32px; }
  .empty-text { color: #999; font-size: 14px; margin-top: 8px; }
</style>
