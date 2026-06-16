<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import LineChart from '../lib/LineChart.svelte'

  let labels = $state([])
  let datasets = $state([])
  let rows = $state([])
  const COLORS = ['#34d399', '#6ea8fe', '#fbbf24', '#a78bfa', '#f87171']

  onMount(async () => {
    const o = await api.overview()
    if (o && o.series) {
      const lset = new Set()
      o.series.forEach((s) => s.points.forEach((p) => lset.add(p.d)))
      labels = [...lset].sort()
      datasets = o.series.map((s, i) => ({
        label: s.label,
        data: labels.map((d) => {
          const pt = s.points.find((p) => p.d === d)
          return pt ? pt.v : null
        }),
        borderColor: COLORS[i % COLORS.length],
        tension: 0.35,
        pointRadius: 2,
        spanGaps: true
      }))
    }
    if (o && o.movers) {
      rows = o.movers.map((m) => ({ title: m.title, views: fmtViews(m.views) }))
    }
  })
</script>

<div class="top">
  <div><h1>Performance</h1><div class="sub">Tren views per source — snapshot harian</div></div>
  <div class="pill">performance_snapshots</div>
</div>

<div class="card" style="margin-bottom:16px">
  <h3>Pertumbuhan views <span class="mut">— top source</span></h3>
  {#if datasets.length}
    <LineChart {labels} {datasets} height={120} />
  {:else}
    <p class="mut" style="font-size:12.5px">Belum ada data snapshot.</p>
  {/if}
</div>

<div class="card">
  <h3>Peringkat views <span class="mut">— views_at_analysis</span></h3>
  <table>
    <thead><tr><th>Video</th><th class="num" style="text-align:right">Views</th></tr></thead>
    <tbody>
      {#each rows as r}
        <tr><td>{r.title}</td><td class="num" style="text-align:right">{r.views}</td></tr>
      {/each}
      {#if !rows.length}<tr><td colspan="2" class="mut">Belum ada data.</td></tr>{/if}
    </tbody>
  </table>
</div>
