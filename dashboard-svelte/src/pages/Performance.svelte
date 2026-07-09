<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import LineChart from '../lib/LineChart.svelte'

  const PLATFORMS_ALL = ['youtube', 'tiktok', 'instagram', 'xiaohongshu']
  const PLATFORM_ICON = { youtube: 'i-yt', tiktok: 'i-tt', instagram: 'i-ig', xiaohongshu: 'i-xhs' }
  const PLATFORM_COLORS = {
    youtube: '#FF0000', tiktok: '#69C9D0', instagram: '#E4405F', xiaohongshu: '#FF2442',
  }
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
  let filterDays     = $state(0)  // 0 = all time

  // Labels visible after time-range filter
  let visibleLabels = $derived(
    filterDays > 0 ? labels.slice(-filterDays) : labels
  )

  // Datasets visible after platform + time filter
  let visibleDatasets = $derived(
    (filterPlatform === 'all' ? datasets : datasets.filter(d => d.label === filterPlatform))
      .map(d => ({
        ...d,
        data: filterDays > 0 ? d.data.slice(-filterDays) : d.data,
      }))
  )

  // Chart labels — falls back to last-7-days skeleton when no data loaded yet
  let chartLabels = $derived(
    visibleLabels.length ? visibleLabels
      : Array.from({ length: 7 }, (_, i) => {
          const d = new Date()
          d.setDate(d.getDate() - 6 + i)
          return d.toISOString().slice(0, 10)
        })
  )

  // Chart datasets — falls back to dashed skeleton lines when nothing to show
  let chartDatasets = $derived(
    visibleDatasets.length
      ? visibleDatasets
      : (filterPlatform === 'all' ? PLATFORMS_ALL : [filterPlatform]).map(p => ({
          label: p,
          data: new Array(chartLabels.length).fill(null),
          borderColor: colorFor(p) + '44',
          backgroundColor: 'transparent',
          tension: 0.35,
          pointRadius: 0,
          spanGaps: false,
          borderDash: [4, 4],
        }))
  )

  // Legend items — always show something (real or skeleton)
  let legendItems = $derived(
    visibleDatasets.length
      ? visibleDatasets
      : (filterPlatform === 'all' ? PLATFORMS_ALL : [filterPlatform]).map(p => ({
          label: p, borderColor: colorFor(p),
        }))
  )

  // Platform totals table rows (with skeleton placeholders when empty)
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

  // Per-account breakdown filtered by platform + account
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

  // Videos filtered by platform
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
        tension: 0.35,
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

  // Picking an account auto-narrows the platform chip to match
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

  <!-- Time range segmented control -->
  <div class="seg" style="margin-left:auto">
    {#each [{v:7,l:'7 hari'},{v:30,l:'30 hari'},{v:0,l:'Semua'}] as opt}
      <button class:active={filterDays === opt.v} onclick={() => filterDays = opt.v}>{opt.l}</button>
    {/each}
  </div>
</div>

<!-- ── Growth chart ─────────────────────────────────────────────────────────── -->
<div class="card" style="margin-bottom:16px">
  <h3>Pertumbuhan views <span class="mut">— per platform</span></h3>

  <!-- Legend — always visible, muted when skeleton -->
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px">
    {#each legendItems as ds}
      <span style="display:flex;align-items:center;gap:5px;font-size:12px;opacity:{visibleDatasets.length ? 1 : 0.4}">
        <span style="display:inline-block;width:20px;height:3px;background:{ds.borderColor};border-radius:2px"></span>
        {ds.label}
      </span>
    {/each}
  </div>

  {#if loading}
    <p class="mut" style="font-size:12.5px">Memuat…</p>
  {:else}
    <div class="chart-wrap">
      <LineChart labels={chartLabels} datasets={chartDatasets} height={160} />
      {#if !datasets.length}
        <div class="chart-overlay">
          <p>Belum ada data — video yang kamu tandai posted di Jadwal Post akan muncul di sini setelah worker fetch views</p>
        </div>
      {:else if !visibleDatasets.length}
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
  .pfchip:not(.active).youtube  .pico { color: #FF0000; }
  .pfchip:not(.active).tiktok   .pico { color: #333; }
  .pfchip:not(.active).instagram .pico { color: #E4405F; }
  .pfchip:not(.active).xiaohongshu .pico { color: #FF2442; }
  :global(.dark) .pfchip:not(.active).tiktok .pico { color: #aaa; }
  /* Active chip always white icon */
  .pfchip.active .pico { color: #fff; }

  .acct-sel {
    background: var(--panel); border: 1px solid var(--line); color: var(--txt);
    border-radius: 8px; padding: 6px 10px; font-size: 12.5px; cursor: pointer;
    font-family: inherit;
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
