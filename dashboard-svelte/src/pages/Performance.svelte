<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import LineChart from '../lib/LineChart.svelte'
  import { rangeFilter, bucket } from '../lib/perfBuckets.js'

  const PLATFORMS_ALL = ['youtube', 'tiktok', 'instagram', 'xiaohongshu']
  const PLATFORM_ICON = { youtube: 'i-yt', tiktok: 'i-tt', instagram: 'i-ig', xiaohongshu: 'i-xhs' }
  const PLATFORM_COLORS = {
    youtube: '#FF0000', tiktok: '#69C9D0', instagram: '#E4405F', xiaohongshu: '#FF2442',
  }
  const CHART_TYPES = [
    { v: 'table', icon: 'i-chart-table', label: 'Table' },
    { v: 'bar',   icon: 'i-chart-bar',   label: 'Bar' },
    { v: 'line',  icon: 'i-chart-line',  label: 'Line' },
    { v: 'area',  icon: 'i-chart-area',  label: 'Area' },
  ]
  const RANGE_OPTIONS = [
    { v: '7d',     l: 'Last 7 days' },
    { v: '30d',    l: 'Last 30 days' },
    { v: '90d',    l: 'Last 90 days' },
    { v: 'year',   l: 'This year' },
    { v: 'all',    l: 'All time' },
    { v: 'custom', l: 'Custom range' },
  ]

  function colorFor(p) {
    return PLATFORM_COLORS[p?.toLowerCase()] || '#6ea8fe'
  }

  let labels      = $state([])
  let datasets    = $state([])
  let totals      = $state([])
  let videos      = $state([])
  let accounts    = $state([])
  let loading     = $state(true)
  let refreshing  = $state(false)
  let lastRefresh = $state(null)
  let collapsed   = $state({})

  // ── Filters ────────────────────────────────────────────────────────────────
  let filterPlatform = $state('all')
  let filterAccount  = $state('all')
  let rangePreset    = $state('30d')
  let customFrom     = $state('')
  let customTo       = $state('')
  let granularity    = $state('D')
  let chartType      = $state('line')

  // ── Stat card derivations ──────────────────────────────────────────────────
  let totalViews  = $derived(totals.reduce((s, t) => s + (t.total_views || 0), 0))
  let topPlatform = $derived(
    totals.length
      ? totals.reduce((a, b) => b.total_views > a.total_views ? b : a).platform
      : '—'
  )

  // Platform-filtered raw datasets (for legend + overlay check)
  let visibleDatasets = $derived(
    filterPlatform === 'all' ? datasets : datasets.filter(d => d.label === filterPlatform)
  )

  // Range + granularity applied → chart-ready or null when empty
  function _computeChartReady(lbls, ds, range, cfrom, cto, gran) {
    if (!lbls.length || !ds.length) return null
    const { labels: rl, data: rd } = rangeFilter(lbls, ds.map(d => d.data), range, cfrom, cto)
    const { labels: bl, data: bd } = bucket(rl, rd, gran)
    if (!bl.length) return null
    return { labels: bl, datasets: ds.map((d, i) => ({ ...d, data: bd[i] ?? [] })) }
  }

  let _chartReady = $derived(
    _computeChartReady(labels, visibleDatasets, rangePreset, customFrom, customTo, granularity)
  )

  // Skeleton labels (last 7 days, computed once at mount)
  const _skeletonLabels = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - 6 + i); return d.toISOString().slice(0, 10)
  })

  let chartLabels = $derived(_chartReady?.labels ?? _skeletonLabels)

  let chartDatasets = $derived(
    _chartReady
      ? _chartReady.datasets
      : (filterPlatform === 'all' ? PLATFORMS_ALL : [filterPlatform]).map(p => ({
          label: p,
          data: new Array(chartLabels.length).fill(null),
          borderColor: colorFor(p) + '44',
          backgroundColor: 'transparent',
          pointRadius: 0,
          spanGaps: false,
          borderDash: [4, 4],
        }))
  )

  let legendItems = $derived(
    _chartReady
      ? _chartReady.datasets
      : (filterPlatform === 'all' ? PLATFORMS_ALL : [filterPlatform]).map(p => ({
          label: p, borderColor: colorFor(p),
        }))
  )

  // ── Other derived values (unchanged from original) ─────────────────────────
  let visibleTotals = $derived(
    filterPlatform === 'all' ? totals : totals.filter(t => t.platform === filterPlatform)
  )

  let tablePlatforms = $derived(
    visibleTotals.length
      ? visibleTotals
      : (filterPlatform === 'all' ? PLATFORMS_ALL : [filterPlatform]).map(p => ({
          platform: p, total_views: 0, video_count: 0, _empty: true,
        }))
  )

  let visibleAccounts = $derived(
    accounts.filter(a =>
      (filterPlatform === 'all' || a.platform === filterPlatform) &&
      (filterAccount === 'all' || String(a.id) === filterAccount)
    )
  )

  let visibleAccountsByPlatform = $derived(
    visibleAccounts.reduce((acc, a) => {
      ;(acc[a.platform] ??= []).push(a)
      return acc
    }, {})
  )

  let visibleVideos = $derived(
    filterPlatform === 'all' ? videos : videos.filter(v => v.platform === filterPlatform)
  )

  // ── Data loading ───────────────────────────────────────────────────────────
  async function load() {
    loading = true
    const d = await api.performance()
    if (d) {
      const dateSet = new Set()
      ;(d.series || []).forEach(s => s.points.forEach(p => dateSet.add(p.date)))
      labels = [...dateSet].sort()
      datasets = (d.series || []).map(s => ({
        label: s.platform,
        data: labels.map(date => {
          const pt = s.points.find(p => p.date === date)
          return pt ? pt.views : null
        }),
        borderColor: colorFor(s.platform),
        backgroundColor: colorFor(s.platform) + '22',
        pointRadius: 3,
        spanGaps: true,
      }))
      totals   = d.totals   || []
      videos   = d.videos   || []
      accounts = d.accounts || []
    }
    loading = false
  }

  async function doRefresh() {
    refreshing = true
    await api.performanceRefresh()
    await load()
    lastRefresh = new Date().toLocaleTimeString()
    refreshing = false
  }

  function pickAccount(id) {
    filterAccount = id
    if (id !== 'all') {
      const acc = accounts.find(a => String(a.id) === id)
      if (acc && filterPlatform === 'all') filterPlatform = acc.platform
    }
  }

  onMount(load)
</script>

<!-- ── Page header ──────────────────────────────────────────────────────────── -->
<div class="top">
  <div>
    <h1>Performance</h1>
    <div class="sub">Views video yang sudah di-post — snapshot harian per platform</div>
  </div>
  <button class="btn" onclick={doRefresh} disabled={refreshing}>
    {refreshing ? 'Mengambil data…' : 'Refresh views'}
  </button>
</div>

{#if lastRefresh}
  <div class="sub" style="margin-bottom:12px;font-size:11.5px">Terakhir refresh: {lastRefresh}</div>
{/if}

<!-- ── Stat cards ───────────────────────────────────────────────────────────── -->
<div class="kpis" style="margin-bottom:16px">
  <div class="card kpi">
    <div class="label">Total Views</div>
    <div class="val">{totals.length ? fmtViews(totalViews) : '—'}</div>
  </div>
  <div class="card kpi">
    <div class="label">Platforms tracked</div>
    <div class="val">{totals.length || '—'}</div>
  </div>
  <div class="card kpi">
    <div class="label">Videos tracked</div>
    <div class="val">{videos.length || '—'}</div>
  </div>
  <div class="card kpi">
    <div class="label">Top platform</div>
    <div class="val" style="font-size:18px;text-transform:capitalize">{topPlatform}</div>
  </div>
</div>

<!-- ── Filter bar ───────────────────────────────────────────────────────────── -->
<div class="pf-bar">
  <!-- Platform chips -->
  <div class="pf-chips">
    <button class="pfchip" class:active={filterPlatform === 'all'} onclick={() => { filterPlatform = 'all'; filterAccount = 'all' }}>
      Semua
    </button>
    {#each PLATFORMS_ALL as p}
      <button class="pfchip {p}" class:active={filterPlatform === p} onclick={() => { filterPlatform = p; filterAccount = 'all' }}>
        <svg class="pico"><use href="#{PLATFORM_ICON[p]}"/></svg>
        {p === 'xiaohongshu' ? 'Xiaohongshu' : p.charAt(0).toUpperCase() + p.slice(1)}
      </button>
    {/each}
  </div>

  <!-- Account dropdown — only when accounts are available -->
  {#if accounts.length}
    <select class="acct-sel" value={filterAccount} onchange={e => pickAccount(e.currentTarget.value)}>
      <option value="all">Semua akun</option>
      {#each accounts as a}
        <option value={String(a.id)}>
          {a.handle}{a.label && a.label !== a.handle ? ` (${a.label})` : ''}
        </option>
      {/each}
    </select>
  {/if}

  <!-- Range + granularity (right-aligned) -->
  <div class="pf-right">
    <select class="acct-sel" onchange={e => rangePreset = e.currentTarget.value}>
      {#each RANGE_OPTIONS as opt}
        <option value={opt.v} selected={rangePreset === opt.v}>{opt.l}</option>
      {/each}
    </select>
    {#if rangePreset === 'custom'}
      <input type="date" class="acct-sel" bind:value={customFrom}>
      <span class="mut" style="font-size:12px">–</span>
      <input type="date" class="acct-sel" bind:value={customTo}>
    {/if}
    <div class="seg">
      {#each [{v:'D',l:'D'},{v:'M',l:'M'},{v:'Q',l:'Q'}] as opt}
        <button class:active={granularity === opt.v} onclick={() => granularity = opt.v}>{opt.l}</button>
      {/each}
    </div>
  </div>
</div>

<!-- ── Growth chart ─────────────────────────────────────────────────────────── -->
<div class="card" style="margin-bottom:16px">
  <div class="chart-hdr">
    <h3 style="margin:0">Pertumbuhan views <span class="mut">— per platform</span></h3>
    <!-- Chart-type toggle -->
    <div class="ct-btns" role="group" aria-label="Chart type">
      {#each CHART_TYPES as ct}
        <button class:active={chartType === ct.v} onclick={() => chartType = ct.v} title={ct.label} aria-label={ct.label}>
          <svg class="ic" style="width:14px;height:14px"><use href="#{ct.icon}"/></svg>
        </button>
      {/each}
    </div>
  </div>

  <!-- Legend — always visible, muted when skeleton -->
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin:8px 0 10px">
    {#each legendItems as ds}
      <span style="display:flex;align-items:center;gap:5px;font-size:12px;opacity:{_chartReady ? 1 : 0.4}">
        <span style="display:inline-block;width:20px;height:3px;background:{ds.borderColor};border-radius:2px"></span>
        {ds.label}
      </span>
    {/each}
  </div>

  {#if loading}
    <p class="mut" style="font-size:12.5px">Memuat…</p>
  {:else if chartType === 'table'}
    <!-- Table view -->
    <div style="overflow-x:auto;max-height:400px;overflow-y:auto">
      {#if !_chartReady}
        <p class="mut" style="font-size:12.5px;padding:20px 0;text-align:center">
          {datasets.length ? 'Tidak ada data untuk filter ini' : 'Belum ada data'}
        </p>
      {:else}
        <table>
          <thead>
            <tr>
              <th>Date</th>
              {#each _chartReady.datasets as ds}<th class="num" style="text-align:right">{ds.label}</th>{/each}
            </tr>
          </thead>
          <tbody>
            {#each _chartReady.labels as lbl, i}
              <tr>
                <td class="num">{lbl}</td>
                {#each _chartReady.datasets as ds}
                  <td class="num" style="text-align:right">{ds.data[i] != null ? fmtViews(ds.data[i]) : '—'}</td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  {:else}
    <div class="chart-wrap">
      <LineChart labels={chartLabels} datasets={chartDatasets} height={160} chartType={chartType} />
      {#if !datasets.length}
        <div class="chart-overlay">
          <p>Belum ada data — video yang kamu tandai posted di Jadwal Post akan muncul di sini setelah worker fetch views</p>
        </div>
      {:else if !_chartReady}
        <div class="chart-overlay">
          <p>Tidak ada data untuk filter ini</p>
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- ── Platform roll-up table ──────────────────────────────────────────────── -->
<div class="card" style="margin-bottom:16px">
  <h3>Views per platform</h3>
  <table>
    <thead>
      <tr>
        <th>Platform</th>
        <th class="num" style="text-align:right">Total views</th>
        <th class="num" style="text-align:right">Jumlah video</th>
      </tr>
    </thead>
    <tbody>
      {#each tablePlatforms as t}
        <tr style={t._empty ? 'opacity:0.45' : ''}>
          <td style="display:flex;align-items:center;gap:8px">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{colorFor(t.platform)}"></span>
            {t.platform}
          </td>
          <td class="num" style="text-align:right">{t._empty ? '—' : fmtViews(t.total_views)}</td>
          <td class="num" style="text-align:right">{t._empty ? '—' : t.video_count}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<!-- ── Per-account breakdown ────────────────────────────────────────────────── -->
{#if accounts.length}
<div class="card" style="margin-bottom:16px">
  <h3>Views per akun <span class="mut">— breakdown per channel</span></h3>

  {#if !visibleAccounts.length}
    <p class="mut" style="font-size:12.5px">Tidak ada akun untuk filter ini.</p>
  {:else}
    {#each Object.entries(visibleAccountsByPlatform) as [platform, accts]}
      {@const ptotal = totals.find(t => t.platform === platform)}
      <div style="margin-bottom:16px">
        <button
          onclick={() => collapsed[platform] = !collapsed[platform]}
          style="display:flex;align-items:center;gap:8px;background:none;border:none;padding:6px 0;cursor:pointer;width:100%;text-align:left"
        >
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{colorFor(platform)}"></span>
          <span style="font-weight:600;font-size:13px;text-transform:capitalize">{platform}</span>
          {#if ptotal}
            <span class="mut" style="font-size:12px;margin-left:4px">{fmtViews(ptotal.total_views)} total</span>
          {/if}
          <span class="mut" style="font-size:11px;margin-left:auto">{collapsed[platform] ? '▶' : '▼'}</span>
        </button>

        {#if !collapsed[platform]}
        <table style="margin-top:4px">
          <thead>
            <tr>
              <th>Akun</th>
              <th class="num" style="text-align:right">Total views</th>
              <th class="num" style="text-align:right">Video</th>
            </tr>
          </thead>
          <tbody>
            {#each accts as a}
              <tr>
                <td style="display:flex;align-items:center;gap:6px">
                  <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:{colorFor(a.platform)}"></span>
                  <span style="font-weight:500">{a.handle}</span>
                  {#if a.label && a.label !== a.handle}
                    <span class="mut" style="font-size:11.5px">{a.label}</span>
                  {/if}
                </td>
                <td class="num" style="text-align:right">{fmtViews(a.total_views)}</td>
                <td class="num" style="text-align:right">{a.video_count}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {/if}
      </div>
    {/each}
  {/if}
</div>
{/if}

<!-- ── Video detail table ───────────────────────────────────────────────────── -->
{#if visibleVideos.length}
<div class="card">
  <h3>Detail video <span class="mut">— views terkini per video</span></h3>
  <table>
    <thead>
      <tr>
        <th>Platform</th>
        <th>Judul</th>
        <th class="num" style="text-align:right">Views</th>
        <th class="num" style="text-align:right">Pertama tercatat</th>
      </tr>
    </thead>
    <tbody>
      {#each visibleVideos as v}
        <tr>
          <td>
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{colorFor(v.platform)};margin-right:6px"></span>
            {v.platform}
          </td>
          <td>
            <a href={v.url} target="_blank" rel="noopener" style="color:inherit;text-decoration:underline;text-underline-offset:2px">
              {v.title}
            </a>
          </td>
          <td class="num" style="text-align:right">{fmtViews(v.latest_views)}</td>
          <td class="num" style="text-align:right;color:var(--text-muted)">{v.first_seen}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
{/if}

<style>
  /* ── Filter bar ──────────────────────────────────────────────────────────── */
  .pf-bar {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;
  }
  .pf-chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }

  .pfchip {
    display: inline-flex; align-items: center; gap: 5px;
    background: var(--panel); border: 1.5px solid var(--line);
    color: var(--mut); border-radius: 20px; padding: 5px 12px;
    font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
    line-height: 1; transition: border-color .15s, color .15s, background .15s;
  }
  .pfchip.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .pfchip:hover:not(.active) { border-color: var(--accent); color: var(--accent); }

  /* Platform brand icon inside chip */
  .pico { width: 13px; height: 13px; flex-shrink: 0; fill: currentColor; stroke: none; }
  .pfchip:not(.active).youtube   .pico { color: #FF0000; }
  .pfchip:not(.active).tiktok    .pico { color: #333; }
  .pfchip:not(.active).instagram .pico { color: #E4405F; }
  .pfchip:not(.active).xiaohongshu .pico { color: #FF2442; }
  :global(.dark) .pfchip:not(.active).tiktok .pico { color: #aaa; }
  .pfchip.active .pico { color: #fff; }

  .acct-sel {
    background: var(--panel); border: 1px solid var(--line); color: var(--txt);
    border-radius: 8px; padding: 6px 10px; font-size: 12.5px; cursor: pointer;
    font-family: inherit;
  }

  .pf-right {
    display: flex; align-items: center; gap: 6px; margin-left: auto; flex-wrap: wrap;
  }

  .seg {
    display: inline-flex; border: 1px solid var(--line); border-radius: 8px;
    overflow: hidden; background: var(--soft);
  }
  .seg button {
    background: none; border: none; padding: 5px 11px; font-size: 12px;
    font-weight: 500; cursor: pointer; color: var(--mut); font-family: inherit;
    transition: background .15s, color .15s;
  }
  .seg button.active { background: var(--accent); color: #fff; }
  .seg button:hover:not(.active) { color: var(--accent); }

  /* ── Chart card header ───────────────────────────────────────────────────── */
  .chart-hdr {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 0;
  }

  /* ── Chart-type toggle ───────────────────────────────────────────────────── */
  .ct-btns { display: inline-flex; gap: 2px; }
  .ct-btns button {
    background: none; border: none; padding: 5px 7px; border-radius: 7px;
    cursor: pointer; color: var(--mut); display: flex; align-items: center;
    font-family: inherit; transition: background .12s, color .12s;
  }
  .ct-btns button.active { background: var(--soft); color: var(--accent); }
  .ct-btns button:hover:not(.active) { color: var(--accent); }

  /* ── Empty chart overlay ─────────────────────────────────────────────────── */
  .chart-wrap { position: relative; }
  .chart-overlay {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    pointer-events: none;
  }
  .chart-overlay p {
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 10px 18px; text-align: center; color: var(--mut);
    font-size: 12px; line-height: 1.6; margin: 0; max-width: 360px;
  }
</style>
