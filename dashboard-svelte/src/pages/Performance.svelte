<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
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
  function fmtUsd(n) {
    return n == null ? '—' : '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  function fmtRpm(n) {
    return n == null || n === 0 ? '—' : '$' + Number(n).toFixed(2)
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

  // ── Top performers (winners) state ────────────────────────────────────────
  let winners        = $state([])
  let winnersLoading = $state(false)
  // Per-winner clone state keyed by url: { n, running, done, total, createdIds, error }
  let cloneState     = $state({})

  // ── Revenue state ──────────────────────────────────────────────────────────
  let revSummary   = $state(null)   // {platforms, videos, grand_total_revenue, grand_total_clicks}
  let revEntries   = $state([])     // raw list for the revenue table
  let revLoading   = $state(false)
  let showRevModal = $state(false)
  let editingEntry = $state(null)   // null = add mode, object = edit mode
  let revSaving    = $state(false)
  let revError     = $state('')
  let revForm      = $state({ platform: 'youtube', video_url: '', revenue_usd: '', link_clicks: '', entry_date: '', note: '' })

  // ── Revenue derived stat card values ──────────────────────────────────────
  let grandRevenue = $derived(revSummary?.grand_total_revenue ?? 0)
  let grandClicks  = $derived(revSummary?.grand_total_clicks ?? 0)
  let grandRPM     = $derived.by(() => {
    if (!revSummary?.platforms?.length) return 0
    const totalViews = revSummary.platforms.reduce((s, p) => s + (p.total_views || 0), 0)
    return totalViews > 0 ? grandRevenue / totalViews * 1000 : 0
  })

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

  // ── Other derived values ───────────────────────────────────────────────────
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

  // Revenue table filtered by platform + date range
  let visibleRevEntries = $derived(
    revEntries.filter(e => {
      if (filterPlatform !== 'all' && e.platform !== filterPlatform) return false
      if (customFrom && e.entry_date < customFrom) return false
      if (customTo   && e.entry_date > customTo)   return false
      return true
    })
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
    loadRevenue()
    loadWinners()
  }

  async function loadWinners() {
    winnersLoading = true
    const data = await api.winners()
    winners = data || []
    // initialise clone state for each winner (preserve existing if already set)
    const next = {}
    for (const w of winners) {
      next[w.url] = cloneState[w.url] ?? { n: 3, running: false, done: 0, total: 0, createdIds: [], error: null }
    }
    cloneState = next
    winnersLoading = false
  }

  async function startClone(winner) {
    const url = winner.url
    cloneState = { ...cloneState, [url]: { ...cloneState[url], running: true, done: 0, createdIds: [], error: null } }
    const n = cloneState[url]?.n ?? 3
    const payload = { n, niche: winner.platform }
    if (winner.seed?.content_item_id) payload.seed_content_item_id = winner.seed.content_item_id
    else if (winner.seed?.source_id)  payload.seed_source_id = winner.seed.source_id
    else                               payload.seed_video_url = winner.url

    const res = await api.winnersClone(payload)
    if (!res?.run_id) {
      cloneState = { ...cloneState, [url]: { ...cloneState[url], running: false, error: 'Clone failed to start' } }
      return
    }
    cloneState = { ...cloneState, [url]: { ...cloneState[url], total: n } }
    pollClone(url, res.run_id)
  }

  function pollClone(url, run_id) {
    const tid = setInterval(async () => {
      const s = await api.winnersCloneStatus(run_id)
      if (!s) return
      cloneState = {
        ...cloneState,
        [url]: { ...cloneState[url], done: s.done ?? 0, total: s.total ?? 0, createdIds: s.created_ids ?? [] },
      }
      if (s.status === 'done' || s.status === 'error') {
        clearInterval(tid)
        cloneState = {
          ...cloneState,
          [url]: { ...cloneState[url], running: false, error: s.error ?? null },
        }
      }
    }, 1500)
  }

  async function loadRevenue() {
    revLoading = true
    const [summary, list] = await Promise.all([api.revenueSummary(), api.revenueList()])
    revSummary = summary
    revEntries = list || []
    revLoading = false
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

  // ── Revenue modal helpers ──────────────────────────────────────────────────
  function openAddModal() {
    const today = new Date().toISOString().slice(0, 10)
    revForm = { platform: filterPlatform === 'all' ? 'youtube' : filterPlatform,
                video_url: '', revenue_usd: '', link_clicks: '', entry_date: today, note: '' }
    editingEntry = null
    revError = ''
    showRevModal = true
  }

  function openEditModal(e) {
    revForm = { platform: e.platform, video_url: e.video_url || '',
                revenue_usd: String(e.revenue_usd), link_clicks: String(e.link_clicks || ''),
                entry_date: e.entry_date, note: e.note || '' }
    editingEntry = e
    revError = ''
    showRevModal = true
  }

  async function saveRevenue() {
    revError = ''
    const payload = {
      platform:     revForm.platform,
      video_url:    revForm.video_url || null,
      revenue_usd:  parseFloat(revForm.revenue_usd) || 0,
      link_clicks:  parseInt(revForm.link_clicks) || 0,
      entry_date:   revForm.entry_date,
      note:         revForm.note || null,
    }
    if (!payload.entry_date) { revError = 'Entry date is required'; return }
    revSaving = true
    const res = editingEntry
      ? await api.revenueUpdate(editingEntry.id, payload)
      : await api.revenueCreate(payload)
    revSaving = false
    if (!res || res.detail) { revError = res?.detail || 'Save failed'; return }
    showRevModal = false
    loadRevenue()
  }

  async function deleteRevenue(id) {
    if (!confirm($_('performance.delete_confirmation'))) return
    await api.revenueDelete(id)
    loadRevenue()
  }

  onMount(load)
</script>

<!-- ── Page header ──────────────────────────────────────────────────────────── -->
<div class="top">
  <div>
    <h1>{$_('performance.title')}</h1>
    <div class="sub">{$_('performance.subtitle')}</div>
  </div>
  <button class="btn" onclick={doRefresh} disabled={refreshing}>
    {refreshing ? $_('performance.refresh_fetching') : $_('performance.refresh_btn')}
  </button>
</div>

{#if lastRefresh}
  <div class="sub" style="margin-bottom:12px;font-size:11.5px">{$_('performance.last_refresh')} {lastRefresh}</div>
{/if}

<!-- ── Stat cards ───────────────────────────────────────────────────────────── -->
<div class="kpis" style="margin-bottom:16px">
  <div class="card kpi">
    <div class="label">{$_('performance.total_views')}</div>
    <div class="val">{totals.length ? fmtViews(totalViews) : '—'}</div>
  </div>
  <div class="card kpi">
    <div class="label">{$_('performance.platforms_tracked')}</div>
    <div class="val">{totals.length || '—'}</div>
  </div>
  <div class="card kpi">
    <div class="label">{$_('performance.videos_tracked')}</div>
    <div class="val">{videos.length || '—'}</div>
  </div>
  <div class="card kpi">
    <div class="label">{$_('performance.top_platform')}</div>
    <div class="val" style="font-size:18px;text-transform:capitalize">{topPlatform}</div>
  </div>
  <div class="card kpi kpi-money">
    <div class="label">{$_('performance.total_revenue')}</div>
    <div class="val">{revLoading ? '…' : fmtUsd(grandRevenue)}</div>
  </div>
  <div class="card kpi kpi-money">
    <div class="label">{$_('performance.rpm')}</div>
    <div class="val">{revLoading ? '…' : fmtRpm(grandRPM)}</div>
  </div>
  <div class="card kpi kpi-money">
    <div class="label">{$_('performance.total_clicks')}</div>
    <div class="val">{revLoading ? '…' : (grandClicks || '—')}</div>
  </div>
</div>

<!-- ── Filter bar ───────────────────────────────────────────────────────────── -->
<div class="pf-bar">
  <!-- Platform chips -->
  <div class="pf-chips">
    <button class="pfchip" class:active={filterPlatform === 'all'} onclick={() => { filterPlatform = 'all'; filterAccount = 'all' }}>
      {$_('app.all')}
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
      <option value="all">{$_('performance.all_accounts')}</option>
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
    <h3 style="margin:0">{$_('performance.chart_title')} <span class="mut">— {$_('performance.chart_subtitle')}</span></h3>
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
    <p class="mut" style="font-size:12.5px">{$_('performance.loading')}</p>
  {:else if chartType === 'table'}
    <!-- Table view -->
    <div style="overflow-x:auto;max-height:400px;overflow-y:auto">
      {#if !_chartReady}
        <p class="mut" style="font-size:12.5px;padding:20px 0;text-align:center">
          {datasets.length ? $_('performance.no_data_for_filter') : $_('performance.no_data_yet')}
        </p>
      {:else}
        <table>
          <thead>
            <tr>
              <th>{$_('performance.table_header_date')}</th>
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
          <p>{$_('performance.no_chart_data')}</p>
        </div>
      {:else if !_chartReady}
        <div class="chart-overlay">
          <p>{$_('performance.no_data_for_filter')}</p>
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- ── Platform roll-up table ──────────────────────────────────────────────── -->
<div class="card" style="margin-bottom:16px">
  <h3>{$_('performance.views_per_platform')}</h3>
  <table>
    <thead>
      <tr>
        <th>{$_('performance.table_header_platform')}</th>
        <th class="num" style="text-align:right">{$_('performance.table_header_total_views')}</th>
        <th class="num" style="text-align:right">{$_('performance.table_header_video_count')}</th>
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
  <h3>{$_('performance.views_per_account')} <span class="mut">— {$_('performance.views_per_account_subtitle')}</span></h3>

  {#if !visibleAccounts.length}
    <p class="mut" style="font-size:12.5px">{$_('performance.no_accounts_for_filter')}</p>
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
              <th>{$_('performance.table_header_account')}</th>
              <th class="num" style="text-align:right">{$_('performance.table_header_total_views')}</th>
              <th class="num" style="text-align:right">{$_('performance.table_header_video_count')}</th>
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
<div class="card" style="margin-bottom:16px">
  <h3>{$_('performance.detail_video')} <span class="mut">— {$_('performance.detail_video_subtitle')}</span></h3>
  <table>
    <thead>
      <tr>
        <th>{$_('performance.table_header_platform')}</th>
        <th>{$_('performance.table_header_title')}</th>
        <th class="num" style="text-align:right">{$_('performance.table_header_views')}</th>
        <th class="num" style="text-align:right">{$_('performance.table_header_first_seen')}</th>
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

<!-- ── Top performers ────────────────────────────────────────────────────────── -->
<div class="card" style="margin-bottom:16px">
  <div class="rev-hdr">
    <h3 style="margin:0">{$_('performance.top_performers')} <span class="mut">— {$_('performance.top_performers_subtitle')}</span></h3>
    {#if winners.length}
      <span class="mut" style="font-size:12px">{winners.length} {$_('performance.video_count_label')}</span>
    {/if}
  </div>

  {#if winnersLoading}
    <p class="mut" style="font-size:12.5px;margin-top:8px">{$_('performance.loading')}</p>
  {:else if !winners.length}
    <p class="mut" style="font-size:12.5px;margin-top:8px">
      {$_('performance.no_posted_videos')}
    </p>
  {:else}
    <div style="overflow-x:auto;margin-top:8px">
      <table>
        <thead>
          <tr>
            <th>{$_('performance.table_header_platform')}</th>
            <th>{$_('performance.table_header_title')}</th>
            <th class="num" style="text-align:right">{$_('performance.table_header_views')}</th>
            <th class="num" style="text-align:right">{$_('performance.table_header_revenue')}</th>
            <th class="num" style="text-align:right">{$_('performance.table_header_rpm')}</th>
            <th style="text-align:right">{$_('performance.clone_to_studio')}</th>
          </tr>
        </thead>
        <tbody>
          {#each winners as w}
            {@const cs = cloneState[w.url] ?? { n: 3, running: false, done: 0, total: 0, createdIds: [], error: null }}
            <tr>
              <td>
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{colorFor(w.platform)};margin-right:6px"></span>
                {w.platform}
              </td>
              <td class="rev-url">
                <a href={w.url} target="_blank" rel="noopener"
                   style="color:inherit;text-decoration:underline;text-underline-offset:2px;font-size:12px">
                  {w.title.length > 48 ? w.title.slice(0, 45) + '…' : w.title}
                </a>
              </td>
              <td class="num" style="text-align:right">{fmtViews(w.latest_views)}</td>
              <td class="num" style="text-align:right;color:var(--green,#22c55e)">{w.revenue > 0 ? fmtUsd(w.revenue) : '—'}</td>
              <td class="num" style="text-align:right">{w.rpm > 0 ? fmtRpm(w.rpm) : '—'}</td>
              <td style="text-align:right;white-space:nowrap">
                {#if cs.running}
                  <span class="mut" style="font-size:12px">{cs.done}/{cs.total} {$_('performance.cloning_status')}</span>
                {:else if cs.createdIds.length && !cs.error}
                  <span class="clone-ok">
                    {cs.createdIds.length} {$_('performance.clone_ok_scripts')} <a href="#" onclick={e => { e.preventDefault(); document.querySelector('[data-page="studio"]')?.click() }} style="color:var(--accent)">{$_('performance.clone_ok_studio')}</a>
                  </span>
                {:else}
                  <span class="clone-ctrl">
                    <input type="number" class="n-input" min="1" max="10" value={cs.n}
                      oninput={e => cloneState = { ...cloneState, [w.url]: { ...cs, n: Math.max(1, Math.min(10, parseInt(e.currentTarget.value) || 3)) } }}
                    >
                    <button class="btn btn-sm" onclick={() => startClone(w)} disabled={cs.running}>
                      {$_('performance.clone_label')} {cs.n}
                    </button>
                  </span>
                  {#if cs.error}
                    <div class="mut" style="font-size:11.5px;color:#ef4444">{cs.error}</div>
                  {/if}
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<!-- ── Revenue section ───────────────────────────────────────────────────────── -->
<div class="card">
  <div class="rev-hdr">
    <h3 style="margin:0">{$_('performance.revenue_section_title')} <span class="mut">— {$_('performance.revenue_section_subtitle')}</span></h3>
    <button class="btn btn-sm" onclick={openAddModal}>{$_('performance.add_revenue_btn')}</button>
  </div>

  {#if revLoading}
    <p class="mut" style="font-size:12.5px;margin-top:8px">{$_('performance.loading')}</p>
  {:else if !visibleRevEntries.length}
    <p class="mut" style="font-size:12.5px;margin-top:8px">
      {$_('performance.no_revenue_entries')}{filterPlatform !== 'all' ? ` ${$_('performance.no_revenue_entries_platform', {values: {platform: filterPlatform}})}` : ''}.
      {$_('performance.add_revenue_instruction')}
    </p>
  {:else}
    <div style="overflow-x:auto;margin-top:8px">
      <table>
        <thead>
          <tr>
            <th>{$_('performance.table_header_platform')}</th>
            <th>{$_('performance.table_header_video_url')}</th>
            <th class="num" style="text-align:right">{$_('performance.table_header_views')}</th>
            <th class="num" style="text-align:right">{$_('performance.table_header_revenue')}</th>
            <th class="num" style="text-align:right">{$_('performance.table_header_rpm')}</th>
            <th class="num" style="text-align:right">{$_('performance.table_header_clicks')}</th>
            <th style="text-align:right">{$_('performance.table_header_entry_date')}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each visibleRevEntries as e}
            {@const vidViews = revSummary?.videos?.find(v => v.video_url === e.video_url)?.latest_views ?? 0}
            {@const rpm = vidViews > 0 ? e.revenue_usd / vidViews * 1000 : 0}
            <tr>
              <td>
                <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{colorFor(e.platform)};margin-right:5px"></span>
                {e.platform}
              </td>
              <td class="rev-url">
                {#if e.video_url}
                  <a href={e.video_url} target="_blank" rel="noopener"
                     style="color:inherit;text-decoration:underline;text-underline-offset:2px;font-size:12px">
                    {e.video_url.length > 40 ? e.video_url.slice(0, 37) + '…' : e.video_url}
                  </a>
                {:else}
                  <span class="mut" style="font-size:12px">—</span>
                {/if}
              </td>
              <td class="num" style="text-align:right">{vidViews ? fmtViews(vidViews) : '—'}</td>
              <td class="num" style="text-align:right;color:var(--green,#22c55e);font-weight:600">{fmtUsd(e.revenue_usd)}</td>
              <td class="num" style="text-align:right">{fmtRpm(rpm)}</td>
              <td class="num" style="text-align:right">{e.link_clicks || '—'}</td>
              <td class="num" style="text-align:right;color:var(--text-muted,var(--mut))">{e.entry_date}</td>
              <td style="text-align:right;white-space:nowrap">
                <button class="act-btn" onclick={() => openEditModal(e)} title="Edit">✎</button>
                <button class="act-btn del" onclick={() => deleteRevenue(e.id)} title="Delete">✕</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<!-- ── Revenue modal ──────────────────────────────────────────────────────────── -->
{#if showRevModal}
<div class="modal-backdrop" onclick={e => { if (e.target === e.currentTarget) showRevModal = false }}>
  <div class="modal-box" role="dialog" aria-modal="true">
    <div class="modal-hdr">
      <span style="font-weight:600;font-size:14px">{editingEntry ? $_('performance.modal_title_edit') : $_('performance.modal_title_add')}</span>
      <button class="act-btn" onclick={() => showRevModal = false} style="font-size:16px">✕</button>
    </div>

    <div class="modal-body">
      <label class="field">
        <span>{$_('performance.modal_label_platform')}</span>
        <select class="acct-sel" bind:value={revForm.platform}>
          {#each PLATFORMS_ALL as p}
            <option value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
          {/each}
        </select>
      </label>

      <label class="field">
        <span>{$_('performance.modal_label_video_url')} <span class="mut">{$_('performance.modal_label_video_url_optional')}</span></span>
        <input type="url" class="acct-sel inp" bind:value={revForm.video_url} placeholder={$_('performance.modal_placeholder_video_url')}>
      </label>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <label class="field">
          <span>{$_('performance.modal_label_revenue_usd')}</span>
          <input type="number" class="acct-sel inp" bind:value={revForm.revenue_usd}
                 min="0" step="0.01" placeholder="0.00">
        </label>
        <label class="field">
          <span>{$_('performance.modal_label_link_clicks')} <span class="mut">{$_('performance.modal_label_video_url_optional')}</span></span>
          <input type="number" class="acct-sel inp" bind:value={revForm.link_clicks}
                 min="0" step="1" placeholder="0">
        </label>
      </div>

      <label class="field">
        <span>{$_('performance.modal_label_entry_date')}</span>
        <input type="date" class="acct-sel inp" bind:value={revForm.entry_date}>
      </label>

      <label class="field">
        <span>{$_('performance.modal_label_note')} <span class="mut">{$_('performance.modal_label_video_url_optional')}</span></span>
        <input type="text" class="acct-sel inp" bind:value={revForm.note} placeholder={$_('performance.modal_placeholder_note')}>
      </label>

      {#if revError}
        <p style="color:#ef4444;font-size:12.5px;margin:0">{revError}</p>
      {/if}
    </div>

    <div class="modal-foot">
      <button class="btn-ghost" onclick={() => showRevModal = false}>{$_('performance.modal_btn_cancel')}</button>
      <button class="btn" onclick={saveRevenue} disabled={revSaving}>
        {revSaving ? $_('performance.modal_btn_saving') : (editingEntry ? $_('performance.modal_btn_save') : $_('performance.modal_btn_add'))}
      </button>
    </div>
  </div>
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

  /* ── Money KPI cards ─────────────────────────────────────────────────────── */
  .kpi-money { border-left: 2px solid #22c55e; }

  /* ── Revenue section header ──────────────────────────────────────────────── */
  .rev-hdr {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px;
  }
  .btn-sm { padding: 5px 12px; font-size: 12px; }

  /* ── Revenue table ───────────────────────────────────────────────────────── */
  .rev-url { max-width: 220px; overflow: hidden; }

  .act-btn {
    background: none; border: none; cursor: pointer; color: var(--mut);
    padding: 2px 5px; border-radius: 5px; font-size: 13px; font-family: inherit;
    transition: background .12s, color .12s;
  }
  .act-btn:hover { background: var(--soft); color: var(--txt); }
  .act-btn.del:hover { background: #fee2e2; color: #ef4444; }
  :global(.dark) .act-btn.del:hover { background: #450a0a; color: #f87171; }

  /* ── Modal ───────────────────────────────────────────────────────────────── */
  .modal-backdrop {
    position: fixed; inset: 0; z-index: 1000;
    background: rgba(0,0,0,.45); display: flex;
    align-items: center; justify-content: center; padding: 16px;
  }
  .modal-box {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 14px; width: 100%; max-width: 440px;
    box-shadow: 0 8px 32px rgba(0,0,0,.18);
  }
  .modal-hdr {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px 10px; border-bottom: 1px solid var(--line);
  }
  .modal-body { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
  .modal-foot {
    padding: 10px 16px 14px; border-top: 1px solid var(--line);
    display: flex; justify-content: flex-end; gap: 8px;
  }

  .field { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
  .field span { color: var(--mut); }
  .inp { width: 100%; box-sizing: border-box; }

  .btn-ghost {
    background: none; border: 1px solid var(--line); color: var(--mut);
    border-radius: 8px; padding: 6px 14px; font-size: 13px; cursor: pointer;
    font-family: inherit; transition: border-color .12s, color .12s;
  }
  .btn-ghost:hover { border-color: var(--accent); color: var(--txt); }

  /* ── Clone controls ──────────────────────────────────────────────────────── */
  .clone-ctrl { display: inline-flex; align-items: center; gap: 5px; }
  .n-input {
    width: 42px; text-align: center; background: var(--panel);
    border: 1px solid var(--line); border-radius: 6px; color: var(--txt);
    font-size: 12px; padding: 4px 5px; font-family: inherit;
  }
  .clone-ok { font-size: 12px; color: var(--mut); }
</style>
