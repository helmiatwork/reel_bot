<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import Pagination from '../lib/Pagination.svelte'

  // ── State ──────────────────────────────────────────────────────────────────
  let rows    = $state([])
  let total   = $state(0)
  let offset  = $state(0)
  let loading = $state(true)
  const limit = 25

  // Filter
  let filterTag  = $state('')
  let filterMood = $state('')

  // Import panel
  let showImport   = $state(false)
  let importFile   = $state(null)
  let importTitle  = $state('')
  let importMood   = $state('')
  let importGenre  = $state('')
  let importTags   = $state([])
  let importTagInput = $state('')
  let importing    = $state(false)
  let importResult = $state(null)  // {ok: bool, msg: str}

  // Editing tags on an existing row
  let editRowId    = $state(null)
  let editTags     = $state([])
  let editTagInput = $state('')
  let editSaving   = $state(false)

  const TAG_SUGGESTIONS = ['classic', 'piano', 'saxophone', 'jazz', 'lofi',
                           'acoustic', 'upbeat', 'cinematic', 'ambient', 'trap',
                           'hiphop', 'rock', 'electronic', 'chill', 'epic']

  // ── Formatters ─────────────────────────────────────────────────────────────
  function fmtDuration(sec) {
    if (sec == null || sec === '') return '—'
    const n = Number(sec)
    if (isNaN(n)) return '—'
    return `${Math.floor(n / 60)}:${(n % 60).toString().padStart(2, '0')}`
  }

  function fmtDate(s) {
    if (!s) return '—'
    const d = new Date(s)
    return isNaN(d.getTime()) ? '—'
      : d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  function fmtBpm(bpm) {
    if (bpm == null) return '—'
    return `${Math.round(Number(bpm))}`
  }

  function sourceLabel(src, url) {
    if (src === 'import') return 'import'
    if (url) { try { return new URL(url).hostname.replace('www.', '') } catch { /**/ } }
    return src || '—'
  }

  // ── Load ───────────────────────────────────────────────────────────────────
  async function load() {
    loading = true
    const data = await api.getSongs(limit, offset, filterTag.trim(), filterMood.trim())
    if (data?.songs) { rows = data.songs; total = data.total ?? rows.length }
    loading = false
  }

  onMount(load)

  function applyFilter() { offset = 0; load() }
  function prev() { offset = Math.max(0, offset - limit); load() }
  function next() { offset = offset + limit; load() }

  // ── Import tag chips ────────────────────────────────────────────────────────
  function addImportTag(t) {
    const tag = t.trim().toLowerCase()
    if (tag && !importTags.includes(tag)) importTags = [...importTags, tag]
  }
  function removeImportTag(t) { importTags = importTags.filter(x => x !== t) }
  function onImportTagKey(e) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault(); addImportTag(importTagInput); importTagInput = ''
    }
  }

  // ── Do import ──────────────────────────────────────────────────────────────
  async function doImport() {
    if (!importFile) return
    importing = true
    importResult = null
    const res = await api.songImport(importFile, {
      title: importTitle, tags: importTags, mood: importMood, genre: importGenre
    })
    importing = false
    if (res?.id) {
      importResult = { ok: true, msg: `Imported: ${res.title} (BPM ${fmtBpm(res.bpm)}, key ${res.music_key || '—'})` }
      importFile = null; importTitle = ''; importTags = []; importMood = ''; importGenre = ''
      showImport = false
      load()
    } else {
      importResult = { ok: false, msg: res?.detail || 'Import failed' }
    }
  }

  // ── Edit tags on existing song ─────────────────────────────────────────────
  function startEdit(row) {
    editRowId = row.id
    editTags = [...(row.tags || [])]
    editTagInput = ''
  }
  function cancelEdit() { editRowId = null; editTags = []; editTagInput = '' }

  function addEditTag(t) {
    const tag = t.trim().toLowerCase()
    if (tag && !editTags.includes(tag)) editTags = [...editTags, tag]
  }
  function removeEditTag(t) { editTags = editTags.filter(x => x !== t) }
  function onEditTagKey(e) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault(); addEditTag(editTagInput); editTagInput = ''
    }
  }

  async function saveEditTags() {
    editSaving = true
    const res = await api.songUpdate(editRowId, { tags: editTags })
    editSaving = false
    if (res?.id) {
      rows = rows.map(r => r.id === res.id ? { ...r, tags: res.tags } : r)
      cancelEdit()
    }
  }
</script>

<!-- ── Header ──────────────────────────────────────────────────────────────── -->
<div class="top">
  <div>
    <h1>{$_('songs.title')}</h1>
    <div class="sub">{$_('songs.subtitle')}</div>
  </div>
  <div style="display:flex;gap:0.5rem;align-items:center">
    <div class="pill">{$_('songs.song_count', { values: { count: total || rows.length } })}</div>
    <button class="btn-sm" onclick={() => { showImport = !showImport; importResult = null }}>
      {showImport ? $_('songs.close_btn') : $_('songs.import_btn')}
    </button>
  </div>
</div>

<!-- ── Import panel ────────────────────────────────────────────────────────── -->
{#if showImport}
<div class="card" style="margin-bottom:1rem">
  <div style="font-weight:600;margin-bottom:0.75rem">Import file audio atau video</div>

  <div class="form-row">
    <label>File audio (mp3 / wav / m4a / aac / ogg, maks 30 MB) atau video (mp4 / mov / webm / mkv / m4v, maks 200 MB)</label>
    <input type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg,video/*,.mp4,.mov,.webm,.mkv,.m4v"
      onchange={e => importFile = e.target.files?.[0] ?? null} />
  </div>

  <div class="form-row">
    <label>Judul (opsional — pakai nama file jika kosong)</label>
    <input type="text" placeholder="misal: Kopi Pagi Instrumental" bind:value={importTitle} />
  </div>

  <div class="form-row">
    <label>Tags — klik saran atau ketik + Enter</label>
    <div class="chip-area">
      {#each importTags as t}
        <span class="chip chip-active">{t}<button onclick={() => removeImportTag(t)}>×</button></span>
      {/each}
      <input class="chip-input" placeholder="ketik tag…" bind:value={importTagInput}
        onkeydown={onImportTagKey} />
    </div>
    <div class="chip-suggestions">
      {#each TAG_SUGGESTIONS as s}
        {#if !importTags.includes(s)}
          <span class="chip chip-sug" onclick={() => addImportTag(s)}>{s}</span>
        {/if}
      {/each}
    </div>
  </div>

  <div class="form-row form-row--2col">
    <div>
      <label>Mood (opsional)</label>
      <input type="text" placeholder="chill, energetic…" bind:value={importMood} />
    </div>
    <div>
      <label>Genre (opsional)</label>
      <input type="text" placeholder="jazz, lo-fi…" bind:value={importGenre} />
    </div>
  </div>

  <div style="display:flex;gap:0.5rem;align-items:center;margin-top:0.75rem">
    <button class="btn-primary" disabled={!importFile || importing} onclick={doImport}>
      {importing ? 'Menganalisis…' : 'Upload & Analisis'}
    </button>
    {#if importResult}
      <span class:ok={importResult.ok} class:err={!importResult.ok} class="import-msg">
        {importResult.msg}
      </span>
    {/if}
  </div>
</div>
{/if}

<!-- ── Filter bar ───────────────────────────────────────────────────────────── -->
<div class="filter-bar">
  <input type="text" placeholder="Filter tag (mis: jazz)" bind:value={filterTag}
    onkeydown={e => e.key === 'Enter' && applyFilter()} />
  <input type="text" placeholder="Filter mood" bind:value={filterMood}
    onkeydown={e => e.key === 'Enter' && applyFilter()} />
  <button class="btn-sm" onclick={applyFilter}>Terapkan</button>
  {#if filterTag || filterMood}
    <button class="btn-sm btn-ghost" onclick={() => { filterTag=''; filterMood=''; applyFilter() }}>Reset</button>
  {/if}
</div>

<!-- ── Table ───────────────────────────────────────────────────────────────── -->
<div class="card">
  <table>
    <thead>
      <tr>
        <th>Judul</th>
        <th class="num">BPM</th>
        <th>Key</th>
        <th>Tags</th>
        <th>Mood / Genre</th>
        <th>Source</th>
        <th class="num">Durasi</th>
        <th>Play / ⬇</th>
        <th>Tanggal</th>
      </tr>
    </thead>
    <tbody>
      {#each rows as r (r.id)}
        <tr>
          <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {r.title || '—'}
          </td>
          <td class="num">{fmtBpm(r.bpm)}</td>
          <td>{r.music_key || '—'}</td>

          <!-- Tags cell with inline edit -->
          <td>
            {#if editRowId === r.id}
              <div class="chip-area chip-area--inline">
                {#each editTags as t}
                  <span class="chip chip-active chip-sm">{t}<button onclick={() => removeEditTag(t)}>×</button></span>
                {/each}
                <input class="chip-input chip-input--sm" placeholder="tag…" bind:value={editTagInput}
                  onkeydown={onEditTagKey} />
              </div>
              <div class="chip-suggestions chip-suggestions--sm">
                {#each TAG_SUGGESTIONS as s}
                  {#if !editTags.includes(s)}
                    <span class="chip chip-sug chip-sug--sm" onclick={() => addEditTag(s)}>{s}</span>
                  {/if}
                {/each}
              </div>
              <div style="display:flex;gap:0.25rem;margin-top:0.25rem">
                <button class="btn-xs btn-primary" disabled={editSaving} onclick={saveEditTags}>
                  {editSaving ? '…' : 'Simpan'}
                </button>
                <button class="btn-xs btn-ghost" onclick={cancelEdit}>Batal</button>
              </div>
            {:else}
              <div class="tags-cell">
                {#each (r.tags || []) as t}
                  <span class="chip chip-tag">{t}</span>
                {/each}
                <button class="btn-tag-edit" title="Edit tags" onclick={() => startEdit(r)}>✎</button>
              </div>
            {/if}
          </td>

          <td class="mut" style="font-size:0.8rem">
            {[r.mood, r.genre].filter(Boolean).join(' / ') || '—'}
          </td>
          <td>
            <span class="badge badge-{r.source === 'import' ? 'import' : 'yt'}">
              {sourceLabel(r.source, r.youtube_url)}
            </span>
          </td>
          <td class="num">{fmtDuration(r.duration_sec)}</td>
          <td>
            <div style="display:flex;gap:0.4rem;align-items:center">
              <audio controls style="max-width:180px;height:26px">
                <source src="/songs/{r.id}/download" type="audio/mpeg" />
              </audio>
              <a href="/songs/{r.id}/download" download style="font-size:0.9rem">⬇</a>
            </div>
          </td>
          <td class="mut">{fmtDate(r.created_at)}</td>
        </tr>
      {/each}
      {#if !loading && !rows.length}
        <tr><td colspan="9" class="mut">Belum ada song.</td></tr>
      {/if}
      {#if loading}
        <tr><td colspan="9" class="mut">Memuat…</td></tr>
      {/if}
    </tbody>
  </table>
</div>

<Pagination {offset} {limit} {total} onprev={prev} onnext={next} />

<style>
  .btn-sm {
    padding: 0.3rem 0.75rem;
    border-radius: 6px;
    border: 1px solid var(--bs-border-color, #dee2e6);
    background: var(--bs-body-bg, #fff);
    cursor: pointer;
    font-size: 0.85rem;
  }
  .btn-primary {
    padding: 0.35rem 0.9rem;
    border-radius: 6px;
    border: none;
    background: var(--bs-primary, #405189);
    color: #fff;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .btn-primary:disabled { opacity: 0.6; cursor: default; }
  .btn-ghost { background: transparent; border-color: transparent; }
  .btn-xs {
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--bs-border-color, #dee2e6);
    background: var(--bs-body-bg, #fff);
    cursor: pointer;
    font-size: 0.75rem;
  }
  .btn-xs.btn-primary { border: none; }

  .filter-bar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.75rem;
    flex-wrap: wrap;
  }
  .filter-bar input {
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    border: 1px solid var(--bs-border-color, #dee2e6);
    background: var(--bs-body-bg, #fff);
    color: inherit;
    font-size: 0.85rem;
    width: 160px;
  }

  .form-row { margin-bottom: 0.6rem; }
  .form-row label { display: block; font-size: 0.8rem; color: var(--bs-secondary-color, #6c757d); margin-bottom: 0.2rem; }
  .form-row input[type="text"],
  .form-row input[type="file"] {
    width: 100%;
    padding: 0.35rem 0.6rem;
    border: 1px solid var(--bs-border-color, #dee2e6);
    border-radius: 6px;
    background: var(--bs-body-bg, #fff);
    color: inherit;
    font-size: 0.85rem;
  }
  .form-row--2col { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }

  .chip-area {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    padding: 0.3rem;
    border: 1px solid var(--bs-border-color, #dee2e6);
    border-radius: 6px;
    min-height: 36px;
    background: var(--bs-body-bg, #fff);
  }
  .chip-area--inline { border: none; padding: 0; background: transparent; }
  .chip { display: inline-flex; align-items: center; gap: 0.2rem;
    padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.78rem; }
  .chip button { background: none; border: none; cursor: pointer; padding: 0; line-height: 1;
    font-size: 0.9rem; opacity: 0.7; }
  .chip-active { background: var(--bs-primary, #405189); color: #fff; }
  .chip-tag { background: var(--bs-light, #f3f4f6); color: var(--bs-body-color, #212529); }
  .chip-sm { font-size: 0.72rem; padding: 0.1rem 0.4rem; }
  .chip-input {
    border: none; outline: none; background: transparent;
    font-size: 0.82rem; min-width: 80px; color: inherit;
  }
  .chip-input--sm { font-size: 0.75rem; min-width: 60px; }
  .chip-suggestions {
    display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.35rem;
  }
  .chip-suggestions--sm { gap: 0.2rem; margin-top: 0.2rem; }
  .chip-sug {
    background: var(--bs-light, #f3f4f6);
    border: 1px dashed var(--bs-border-color, #dee2e6);
    color: var(--bs-body-color, #495057);
    cursor: pointer;
    transition: background 0.1s;
  }
  .chip-sug:hover { background: var(--bs-primary-bg-subtle, #dce1f5); }
  .chip-sug--sm { font-size: 0.72rem; padding: 0.1rem 0.35rem; }

  .tags-cell { display: flex; flex-wrap: wrap; gap: 0.2rem; align-items: center; }
  .btn-tag-edit {
    background: none; border: none; cursor: pointer;
    color: var(--bs-secondary-color, #6c757d); font-size: 0.85rem;
    padding: 0 0.2rem;
    opacity: 0;
    transition: opacity 0.15s;
  }
  tr:hover .btn-tag-edit { opacity: 1; }

  .badge {
    display: inline-block; padding: 0.2rem 0.5rem; border-radius: 8px;
    font-size: 0.72rem; font-weight: 600;
  }
  .badge-import { background: #d1fae5; color: #065f46; }
  .badge-yt     { background: #fee2e2; color: #991b1b; }

  .import-msg { font-size: 0.82rem; }
  .ok  { color: #059669; }
  .err { color: #dc2626; }
</style>
