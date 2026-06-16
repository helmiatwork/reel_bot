<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import { FALLBACK_MOVERS } from '../lib/data.js'
  import LineChart from '../lib/LineChart.svelte'

  let kpis = $state({ sources: 0, total_views: 0, produced: 0, formulas: 0, clips: 0 })
  let labels = $state([])
  let datasets = $state([])
  let movers = $state([])
  let loaded = $state(false)
  let usingReal = $state(false)

  const COLORS = ['#34d399', '#6ea8fe', '#fbbf24', '#a78bfa']

  onMount(async () => {
    const o = await api.overview()
    if (o && o.kpis) {
      usingReal = true
      kpis = o.kpis
      // build chart from series points (union of all date labels)
      const lset = new Set()
      ;(o.series || []).forEach((s) => s.points.forEach((p) => lset.add(p.d)))
      labels = [...lset].sort()
      datasets = (o.series || []).map((s, i) => ({
        label: s.label,
        data: labels.map((d) => {
          const pt = s.points.find((p) => p.d === d)
          return pt ? pt.v : null
        }),
        borderColor: COLORS[i % COLORS.length],
        backgroundColor: COLORS[i % COLORS.length] + '14',
        fill: true,
        tension: 0.35,
        pointRadius: 2,
        spanGaps: true
      }))
      movers = (o.movers || []).map((m) => ({ title: m.title, rate: fmtViews(m.views), up: true }))
    }
    if (!movers.length) movers = FALLBACK_MOVERS
    loaded = true
  })
</script>

<div class="top">
  <div>
    <h1>Dashboard</h1>
    <div class="sub">Overview — data dari content_automation</div>
  </div>
  <div class="pill">⟳ live · @HReelBot</div>
</div>

<div class="kpis">
  <div class="card kpi">
    <div class="label">Source dianalisa</div>
    <div class="val num">{kpis.sources}</div>
    <div class="delta up">library riset</div>
  </div>
  <div class="card kpi">
    <div class="label">Total views dipantau</div>
    <div class="val num">{fmtViews(kpis.total_views)}</div>
    <div class="delta up">▲ performance_snapshots</div>
  </div>
  <div class="card kpi">
    <div class="label">Video diproduksi</div>
    <div class="val num">{kpis.produced}</div>
    <div class="delta mut">pipeline_runs done</div>
  </div>
  <div class="card kpi">
    <div class="label">Formula + klip</div>
    <div class="val num">{kpis.formulas} <span class="mut" style="font-size:14px">/ {kpis.clips}</span></div>
    <div class="delta mut">formula di DB · klip</div>
  </div>
</div>

<div class="grid2">
  <div class="card">
    <h3>Tren views <span class="mut">— 7 hari (performance_snapshots)</span></h3>
    {#if loaded && datasets.length}
      <LineChart {labels} {datasets} height={118} />
    {:else}
      <p class="mut" style="font-size:12.5px">Belum ada snapshot views buat ditampilkan.</p>
    {/if}
  </div>
  <div class="card">
    <h3>Naik tercepat <span class="mut">— top views</span></h3>
    <table>
      <thead><tr><th>Video</th><th style="text-align:right">views</th></tr></thead>
      <tbody>
        {#each movers as m}
          <tr><td>{m.title}</td><td class="num {m.up ? 'up' : 'mut'}" style="text-align:right">{m.rate}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

{#if !usingReal}
  <div class="note">⚠️ DB belum terjangkau — menampilkan angka fallback. Cek service postgres di sidebar.</div>
{/if}
