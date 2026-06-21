<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'

  let rows = $state([])
  let url = $state('')
  let maxClips = $state(8)
  let loading = $state(false)
  let expanded = $state({}) // { [rowId]: true/false }

  // Format cost as currency with 4 decimals
  function fmtCost(n) {
    return '$' + (Number(n) || 0).toFixed(4)
  }

  // Format date as short locale string
  function fmtDate(iso) {
    if (!iso) return '-'
    try {
      const d = new Date(iso)
      return d.toLocaleDateString('id-ID', { year: '2-digit', month: '2-digit', day: '2-digit' })
    } catch {
      return iso
    }
  }

  // Format seconds to mm:ss
  function fmtTime(seconds) {
    if (typeof seconds !== 'number') return '-'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  // Truncate URL to ~50 chars for display
  function truncateUrl(url) {
    if (!url) return '-'
    if (url.length > 50) return url.substring(0, 47) + '…'
    return url
  }

  // Truncate text to N chars
  function truncate(text, len = 60) {
    if (!text) return '-'
    if (text.length > len) return text.substring(0, len - 1) + '…'
    return text
  }

  function toggleExpand(id) {
    expanded[id] = !expanded[id]
  }

  async function handleFindClips() {
    if (!url.trim()) return
    loading = true
    const result = await api.findClips(url, maxClips)
    loading = false
    if (result && result.clips) {
      // Prepend new find to list
      rows = [
        {
          id: Math.random(),
          youtube_url: result.youtube_url,
          clips: result.clips,
          model: result.model,
          cost_usd: result.cost_usd,
          created_at: new Date().toISOString(),
        },
        ...rows,
      ]
      url = ''
    }
  }

  onMount(async () => {
    const data = await api.clipFinds()
    if (data && data.rows) {
      rows = data.rows
    }
  })
</script>

<div class="top">
  <div><h1>Clipper</h1><div class="sub">Cari momen viral dari transkrip — podcast/video panjang → short-form clips</div></div>
  <div class="pill">{rows.length} hasil</div>
</div>

<div class="filters">
  <div class="input-group">
    <input
      placeholder="YouTube URL…"
      bind:value={url}
      disabled={loading}
      onkeydown={(e) => e.key === 'Enter' && handleFindClips()}
    />
    <input
      type="number"
      placeholder="Max clips"
      bind:value={maxClips}
      min="1"
      max="20"
      disabled={loading}
      style="width: 100px"
    />
    <button onclick={handleFindClips} disabled={loading || !url.trim()}>
      {loading ? 'menganalisa…' : 'Cari klip'}
    </button>
  </div>
</div>

<div class="card">
  {#if rows.length === 0}
    <div class="empty">
      <div class="empty-icon">📹</div>
      <div class="empty-text">Belum ada klip. Masukin URL di atas.</div>
    </div>
  {:else}
    <table>
      <thead>
        <tr>
          <th>Video</th>
          <th>Klip</th>
          <th>Model</th>
          <th style="text-align:right">Cost</th>
          <th>Tanggal</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.id)}
          <tr onclick={() => toggleExpand(row.id)}>
            <td>
              <a href={row.youtube_url} target="_blank" rel="noopener noreferrer">
                {truncateUrl(row.youtube_url)}
              </a>
            </td>
            <td class="num">
              {(row.clips || []).length}
            </td>
            <td><span class="chip">{row.model}</span></td>
            <td class="num" style="text-align:right">{fmtCost(row.cost_usd)}</td>
            <td>{fmtDate(row.created_at)}</td>
          </tr>
          {#if expanded[row.id]}
            <tr class="expanded-row">
              <td colspan="5">
                <div class="clips-list">
                  {#each row.clips || [] as clip, idx}
                    <div class="clip-card">
                      <div class="clip-header">
                        <div class="clip-title">{clip.title || '-'}</div>
                        <div class="clip-time">
                          {fmtTime(clip.start_sec)}–{fmtTime(clip.end_sec)}
                        </div>
                      </div>
                      <div class="clip-hook">
                        <strong>Hook:</strong> {clip.hook || '-'}
                      </div>
                      <div class="clip-why">
                        <strong>Alasan viral:</strong> {clip.why || '-'}
                      </div>
                      <div class="clip-caption">
                        <strong>Caption:</strong> {clip.caption || '-'}
                      </div>
                    </div>
                  {/each}
                </div>
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .top > div:first-child {
    flex: 1;
  }

  h1 {
    margin: 0 0 6px 0;
    font-size: 28px;
    font-weight: 600;
  }

  .sub {
    font-size: 14px;
    color: #666;
    margin: 0;
  }

  .pill {
    background: #f0f0f0;
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 500;
    color: #333;
    white-space: nowrap;
  }

  .filters {
    margin-bottom: 20px;
  }

  .input-group {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  input[type='text'],
  input[type='number'] {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 14px;
    font-family: inherit;
  }

  input[type='number'] {
    flex: 0 0 auto;
  }

  button {
    padding: 8px 16px;
    background: #2563eb;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    white-space: nowrap;
    transition: background 200ms;
  }

  button:hover:not(:disabled) {
    background: #1d4ed8;
  }

  button:disabled {
    background: #ccc;
    cursor: not-allowed;
  }

  .card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 16px;
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  thead {
    border-bottom: 2px solid #e0e0e0;
  }

  th {
    text-align: left;
    padding: 12px 8px;
    font-weight: 600;
    color: #333;
  }

  td {
    padding: 12px 8px;
    border-bottom: 1px solid #f0f0f0;
  }

  tr:hover {
    background: #f9f9f9;
    cursor: pointer;
  }

  a {
    color: #2563eb;
    text-decoration: none;
  }

  a:hover {
    text-decoration: underline;
  }

  .chip {
    display: inline-block;
    background: #e0e7ff;
    color: #3730a3;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }

  .num {
    text-align: right;
  }

  .expanded-row {
    background: #f9f9f9;
  }

  .expanded-row > td {
    padding: 16px 8px;
    border-bottom: 2px solid #e0e0e0;
  }

  .clips-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .clip-card {
    background: white;
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 12px;
  }

  .clip-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    padding-bottom: 8px;
    border-bottom: 1px solid #f0f0f0;
  }

  .clip-title {
    font-weight: 600;
    color: #222;
    flex: 1;
  }

  .clip-time {
    font-size: 12px;
    color: #666;
    font-weight: 500;
  }

  .clip-hook,
  .clip-why,
  .clip-caption {
    margin: 6px 0;
    font-size: 13px;
    color: #444;
    line-height: 1.4;
  }

  .empty {
    text-align: center;
    padding: 60px 20px;
    color: #999;
  }

  .empty-icon {
    font-size: 48px;
    margin-bottom: 12px;
  }

  .empty-text {
    font-size: 16px;
    font-weight: 500;
  }
</style>
