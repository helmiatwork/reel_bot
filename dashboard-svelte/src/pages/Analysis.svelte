<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'

  let rows = $state([])
  let q = $state('')
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

  let filtered = $derived(
    rows.filter(
      (r) =>
        !q ||
        (r.youtube_url && r.youtube_url.toLowerCase().includes(q.toLowerCase())) ||
        (r.hook && r.hook.toLowerCase().includes(q.toLowerCase()))
    )
  )

  function toggleExpand(id) {
    expanded[id] = !expanded[id]
  }

  onMount(async () => {
    const data = await api.analysis()
    if (data && data.rows) {
      rows = data.rows
    }
  })
</script>

<div class="top">
  <div><h1>Analysis</h1><div class="sub">Claude video-analysis results — klik baris buat detail</div></div>
  <div class="pill">{rows.length} hasil</div>
</div>

<div class="filters">
  <input placeholder="cari URL atau hook..." bind:value={q} />
</div>

<div class="card">
  <table>
    <thead>
      <tr>
        <th>Video</th>
        <th>Hook</th>
        <th>Tags</th>
        <th>Model</th>
        <th style="text-align:right">Cost</th>
        <th>Tanggal</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as row (row.id)}
        <tr onclick={() => toggleExpand(row.id)}>
          <td>
            <a href={row.youtube_url} target="_blank" rel="noopener noreferrer">
              {truncateUrl(row.youtube_url)}
            </a>
          </td>
          <td>{truncate(row.hook, 60)}</td>
          <td>
            {#each (row.tags || []).slice(0, 3) as t}
              <span class="tag">{t}</span>
            {/each}
          </td>
          <td><span class="chip">{row.model}</span></td>
          <td class="num" style="text-align:right">{fmtCost(row.cost_usd)}</td>
          <td>{fmtDate(row.created_at)}</td>
        </tr>
        {#if expanded[row.id]}
          <tr class="expanded-row">
            <td colspan="6">
              <div class="detail">
                <div class="detail-section">
                  <strong>Intent:</strong> {row.intent || '-'}
                </div>
                <div class="detail-section">
                  <strong>Hook:</strong> {row.hook || '-'}
                </div>
                <div class="detail-section">
                  <strong>Structure:</strong> {row.structure || '-'}
                </div>
                <div class="detail-section">
                  <strong>Retention:</strong> {row.retention || '-'}
                </div>
                <div class="detail-section">
                  <strong>Tags:</strong>
                  <div class="tags-list">
                    {#each row.tags || [] as t}
                      <span class="tag">{t}</span>
                    {/each}
                  </div>
                </div>
              </div>
            </td>
          </tr>
        {/if}
      {/each}
      {#if !filtered.length}
        <tr><td colspan="6" class="mut">Belum ada analisa di DB.</td></tr>
      {/if}
    </tbody>
  </table>
</div>

<style>
  .expanded-row {
    background: var(--bg-secondary, #f5f5f5);
  }

  .detail {
    padding: 1rem;
    border-top: 1px solid var(--border-color, #eee);
  }

  .detail-section {
    margin-bottom: 0.75rem;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .detail-section strong {
    display: block;
    color: var(--text-secondary, #666);
    font-weight: 600;
    margin-bottom: 0.25rem;
  }

  .tags-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  a {
    color: var(--link-color, #0066cc);
    text-decoration: none;
  }

  a:hover {
    text-decoration: underline;
  }

  .chip {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    background: var(--bg-chip, #e0e0e0);
    font-size: 0.85rem;
    color: var(--text-secondary, #666);
  }

  .tag {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    background: var(--bg-tag, #f0f0f0);
    font-size: 0.8rem;
    color: var(--text-secondary, #666);
  }

  .num {
    font-variant-numeric: tabular-nums;
  }
</style>
