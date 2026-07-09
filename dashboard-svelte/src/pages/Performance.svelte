<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import LineChart from '../lib/LineChart.svelte'

  const PLATFORM_COLORS = {
    youtube:     '#FF0000',
    tiktok:      '#69C9D0',
    instagram:   '#E4405F',
    xiaohongshu: '#FF2442',
  }
  function colorFor(p) {
    return PLATFORM_COLORS[p?.toLowerCase()] || '#6ea8fe'
  }

  let labels      = $state([])
  let datasets    = $state([])
  let totals      = $state([])
  let videos      = $state([])
  let loading     = $state(true)
  let refreshing  = $state(false)
  let lastRefresh = $state(null)

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
      totals = d.totals || []
      videos = d.videos || []
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

  onMount(load)
</script>

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

<div class="card" style="margin-bottom:16px">
  <h3>Pertumbuhan views <span class="mut">— per platform</span></h3>
  {#if loading}
    <p class="mut" style="font-size:12.5px">Memuat…</p>
  {:else if datasets.length}
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px">
      {#each datasets as ds}
        <span style="display:flex;align-items:center;gap:5px;font-size:12px">
          <span style="display:inline-block;width:20px;height:3px;background:{ds.borderColor};border-radius:2px"></span>
          {ds.label}
        </span>
      {/each}
    </div>
    <LineChart {labels} {datasets} height={160} />
  {:else}
    <p class="mut" style="font-size:12.5px">
      Belum ada data — video yang kamu tandai posted di Jadwal Post akan muncul di sini setelah worker jalan.
    </p>
  {/if}
</div>

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
      {#each totals as t}
        <tr>
          <td style="display:flex;align-items:center;gap:8px">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{colorFor(t.platform)}"></span>
            {t.platform}
          </td>
          <td class="num" style="text-align:right">{fmtViews(t.total_views)}</td>
          <td class="num" style="text-align:right">{t.video_count}</td>
        </tr>
      {/each}
      {#if !totals.length}
        <tr>
          <td colspan="3" class="mut">
            Belum ada data — video yang kamu tandai posted di Jadwal Post akan muncul di sini setelah worker jalan.
          </td>
        </tr>
      {/if}
    </tbody>
  </table>
</div>

{#if videos.length}
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
      {#each videos as v}
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
