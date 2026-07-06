<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import { SOURCE_DETAIL } from '../lib/data.js'
  import { openDrawer } from '../lib/stores.js'
  import Pagination from '../lib/Pagination.svelte'

  let rows = $state([])
  let total = $state(0)
  let offset = $state(0)
  const limit = 25
  let q = $state('')
  let niche = $state('')

  function enrich(r) {
    const d = SOURCE_DETAIL[r.id] || {}
    return {
      id: r.id,
      title: r.title,
      channel: r.channel,
      status: r.status,
      views: r.views,
      viewsLabel: fmtViews(r.views),
      // AI-inferred category from DB; fall back to SOURCE_DETAIL, never platform
      niche: r.niche && r.niche !== '-' ? r.niche : (d.niche || '-'),
      platform: r.platform || '-',
      formula: d.formula || '-',
      tags: d.tags || [],
      dur: d.dur || '-',
      res: d.res || '-',
      lang: d.lang || '-',
      hook: d.hook || '-',
      clip: d.clip ?? false,
      face: d.face ?? false,
      sum: d.sum || '',
      // ponytail: youtube_url carried for frames drawer; absent from /dash/table/sources SELECT (blocker noted)
      youtube_url: r.youtube_url || null
    }
  }

  async function load() {
    const t = await api.table('sources', limit, offset)
    if (t && t.rows) {
      rows = t.rows.map(enrich)
      total = t.total ?? 0
    }
  }

  let filtered = $derived(
    rows.filter(
      (r) =>
        (!q || r.title.toLowerCase().includes(q.toLowerCase())) &&
        (!niche || r.niche === niche)
    )
  )
  let niches = $derived([...new Set(rows.map((r) => r.niche))].filter((n) => n && n !== '-'))

  onMount(load)

  function prev() { offset = Math.max(0, offset - limit); load() }
  function next() { offset = offset + limit; load() }
</script>

<div class="top">
  <div><h1>Sources</h1><div class="sub">Library riset — klik baris buat detail</div></div>
  <div class="pill">{total || rows.length} source</div>
</div>

<div class="filters">
  <select bind:value={niche}>
    <option value="">Semua niche</option>
    {#each niches as n}<option value={n}>{n}</option>{/each}
  </select>
  <input placeholder="cari judul..." bind:value={q} />
</div>

<div class="card">
  <table>
    <thead>
      <tr><th>Judul</th><th>Niche</th><th>Platform</th><th>Tags</th><th style="text-align:right">Views</th><th>Status</th></tr>
    </thead>
    <tbody>
      {#each filtered as s}
        <tr onclick={() => openDrawer('source', s)}>
          <td>{s.title}</td>
          <td>{s.niche}</td>
          <td>{s.platform}</td>
          <td>{#each s.tags.slice(0, 3) as t}<span class="tag">{t}</span>{/each}</td>
          <td class="num" style="text-align:right">{s.viewsLabel}</td>
          <td><span class="chip {s.status === 'used' ? 'c-used' : 'c-analyzed'}">{s.status}</span></td>
        </tr>
      {/each}
      {#if !filtered.length}
        <tr><td colspan="6" class="mut">Belum ada source di DB.</td></tr>
      {/if}
    </tbody>
  </table>
</div>

<Pagination {offset} {limit} {total} onprev={prev} onnext={next} />
