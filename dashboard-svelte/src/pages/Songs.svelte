<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import Pagination from '../lib/Pagination.svelte'

  let rows = $state([])
  let total = $state(0)
  let offset = $state(0)
  const limit = 25
  let loading = $state(true)

  function fmtDuration(sec) {
    if (sec == null || sec === '') return '—'
    const num = Number(sec)
    if (isNaN(num)) return '—'
    const min = Math.floor(num / 60)
    const s = num % 60
    return `${min}:${s.toString().padStart(2, '0')}`
  }

  function fmtDate(s) {
    if (!s) return '—'
    const d = new Date(s)
    if (isNaN(d.getTime())) return '—'
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  function youtubeLink(url) {
    if (!url) return '—'
    try {
      const u = new URL(url)
      return u.hostname.replace('www.', '')
    } catch {
      return '—'
    }
  }

  async function load() {
    loading = true
    const data = await api.getSongs(limit, offset)
    if (data && data.songs) {
      rows = data.songs
      total = data.total ?? rows.length
    }
    loading = false
  }

  onMount(load)

  function prev() { offset = Math.max(0, offset - limit); load() }
  function next() { offset = offset + limit; load() }
</script>

<div class="top">
  <div><h1>Songs</h1><div class="sub">Audio files extracted from analyzed videos</div></div>
  <div class="pill">{total || rows.length} song</div>
</div>

<div class="card">
  <table>
    <thead>
      <tr>
        <th>Title</th>
        <th>Source</th>
        <th class="num" style="text-align:right">Duration</th>
        <th>Play/Download</th>
        <th>Created</th>
      </tr>
    </thead>
    <tbody>
      {#each rows as r}
        <tr>
          <td>{r.title || '—'}</td>
          <td><a href={r.youtube_url} target="_blank" rel="noopener noreferrer">{youtubeLink(r.youtube_url)}</a></td>
          <td class="num" style="text-align:right">{fmtDuration(r.duration_sec)}</td>
          <td>
            <div style="display: flex; gap: 0.5rem; align-items: center;">
              <audio controls style="max-width: 200px; height: 28px;">
                <source src="/songs/{r.id}/download" type="audio/mpeg" />
                Your browser does not support the audio element.
              </audio>
              <a href="/songs/{r.id}/download" download style="font-size: 0.9rem;">⬇</a>
            </div>
          </td>
          <td>{fmtDate(r.created_at)}</td>
        </tr>
      {/each}
      {#if !loading && !rows.length}
        <tr><td colspan="5" class="mut">Belum ada song.</td></tr>
      {/if}
      {#if loading}
        <tr><td colspan="5" class="mut">Memuat…</td></tr>
      {/if}
    </tbody>
  </table>
</div>

<Pagination {offset} {limit} {total} onprev={prev} onnext={next} />
