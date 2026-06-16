<script>
  import { onMount, onDestroy } from 'svelte'
  import { api } from '../lib/api.js'
  import Chart from 'chart.js/auto'

  let totals = $state({ requests: 0, success: 0, failed: 0, est_cost: 0, est_per_request: 0 })
  let providers = $state([])
  let series = $state([])
  let err = $state('')
  let canvas, chart, timer

  function rebuild() {
    if (!canvas || !series.length) return
    if (chart) chart.destroy()
    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: series.map((s) => s.time),
        datasets: [{ label: 'request / 10 mnt', data: series.map((s) => s.requests), backgroundColor: '#6ea8fe' }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8b97ab', font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: '#8b97ab', font: { size: 9 }, maxRotation: 90 }, grid: { color: '#1f2937' } },
          y: { ticks: { color: '#8b97ab', font: { size: 11 } }, grid: { color: '#1f2937' } }
        }
      }
    })
  }

  async function load() {
    const c = await api.cost()
    if (!c) { err = 'pipeline-api tak terjangkau'; return }
    if (c.error) err = c.error
    totals = c.totals || totals
    providers = c.providers || []
    series = c.series || []
    rebuild()
  }

  onMount(() => { load(); timer = setInterval(load, 15000) })
  onDestroy(() => { clearInterval(timer); chart && chart.destroy() })

  const usd = (n) => '$' + (Number(n) || 0).toFixed(3)
  let successRate = $derived(totals.requests ? Math.round((totals.success / totals.requests) * 100) : 0)
</script>

<div class="top">
  <div><h1>Cost</h1><div class="sub">Proxy spend dari cliproxy usage — request count → estimasi</div></div>
  <div class="pill">est ${totals.est_per_request}/req</div>
</div>

<div class="kpis">
  <div class="card kpi"><div class="label">Total request</div><div class="val num">{totals.requests}</div><div class="delta mut">sejak cliproxy start</div></div>
  <div class="card kpi"><div class="label">Estimasi biaya</div><div class="val num">{usd(totals.est_cost)}</div><div class="delta mut">≈ request × tarif</div></div>
  <div class="card kpi"><div class="label">Success rate</div><div class="val num">{successRate}%</div><div class="delta {totals.failed ? 'down' : 'up'}">{totals.failed} gagal</div></div>
  <div class="card kpi"><div class="label">Provider</div><div class="val num">{providers.length}</div><div class="delta mut">upstream aktif</div></div>
</div>

<div class="grid2">
  <div class="card">
    <h3>Volume request <span class="mut">— bucket 10 menit (in-memory)</span></h3>
    {#if series.length}
      <div style="height:140px;position:relative"><canvas bind:this={canvas}></canvas></div>
    {:else}
      <p class="mut" style="font-size:12.5px">Belum ada request tercatat. Trigger pipeline buat ngisi.</p>
    {/if}
  </div>
  <div class="card">
    <h3>Per provider</h3>
    <table>
      <thead><tr><th>Provider</th><th class="num" style="text-align:right">Req</th><th class="num" style="text-align:right">Gagal</th><th class="num" style="text-align:right">Est</th></tr></thead>
      <tbody>
        {#each providers as p}
          <tr>
            <td>{p.name}</td>
            <td class="num" style="text-align:right">{p.requests}</td>
            <td class="num {p.failed ? 'down' : 'mut'}" style="text-align:right">{p.failed}</td>
            <td class="num" style="text-align:right">{usd(p.est_cost)}</td>
          </tr>
        {/each}
        {#if !providers.length}<tr><td colspan="4" class="mut">Belum ada data.</td></tr>{/if}
      </tbody>
    </table>
  </div>
</div>

<div class="note">⚠️ cliproxy cuma log <b>jumlah request</b> (bukan token), dan in-memory (reset kalau cliproxy restart). Biaya = estimasi kasar (request × tarif rata-rata). Set <code>EST_COST_PER_REQUEST</code> di env buat kalibrasi. {#if err}· <span class="down">{err}</span>{/if}</div>
