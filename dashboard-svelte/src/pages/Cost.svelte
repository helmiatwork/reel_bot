<script>
  import { onMount, onDestroy } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import Chart from 'chart.js/auto'

  // real token spend (primary)
  let tk = $state({ rows: [], series: [], by_agent: [], totals: { cost_usd: 0, total_tokens: 0, calls: 0 } })
  // cliproxy request volume (secondary / liveness)
  let cx = $state({ providers: [], totals: { requests: 0, success: 0, failed: 0 } })
  let err = $state('')
  let canvas, chart, timer

  function rebuild() {
    if (!canvas || !tk.series.length) return
    if (chart) chart.destroy()
    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: tk.series.map((s) => s.d),
        datasets: [{ label: 'token / hari', data: tk.series.map((s) => s.tokens), backgroundColor: '#a78bfa' }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8b97ab', font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: '#8b97ab', font: { size: 10 } }, grid: { color: '#1f2937' } },
          y: { ticks: { color: '#8b97ab', font: { size: 11 }, callback: (v) => (v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(0) + 'k' : v) }, grid: { color: '#1f2937' } }
        }
      }
    })
  }

  async function load() {
    const [t, c] = await Promise.all([api.tokenUsage(), api.cost()])
    if (t) { tk = t; if (t.error) err = t.error }
    if (c) cx = c
    rebuild()
  }

  onMount(() => { load(); timer = setInterval(load, 15000) })
  onDestroy(() => { clearInterval(timer); chart && chart.destroy() })

  const usd = (n) => '$' + (Number(n) || 0).toFixed(4)
  const fmtTok = (n) => (n >= 1e6 ? (n / 1e6).toFixed(2) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(n || 0))
  let cxRate = $derived(cx.totals?.requests ? Math.round((cx.totals.success / cx.totals.requests) * 100) : 0)
</script>

<div class="top">
  <div><h1>{$_('cost.title')}</h1><div class="sub">{$_('cost.subtitle')}</div></div>
  <div class="pill">{tk.totals.calls} call</div>
</div>

<div class="kpis">
  <div class="card kpi"><div class="label">{$_('cost.token_cost')}</div><div class="val num">{usd(tk.totals.cost_usd)}</div><div class="delta up">{$_('cost.from_recorded')}</div></div>
  <div class="card kpi"><div class="label">{$_('cost.total_tokens')}</div><div class="val num">{fmtTok(tk.totals.total_tokens)}</div><div class="delta mut">{$_('cost.llm_calls', { values: { calls: tk.totals.calls } })}</div></div>
  <div class="card kpi"><div class="label">{$_('cost.cliproxy_requests')}</div><div class="val num">{cx.totals?.requests || 0}</div><div class="delta {cx.totals?.failed ? 'down' : 'mut'}">{cxRate}% sukses</div></div>
  <div class="card kpi"><div class="label">{$_('cost.models_used')}</div><div class="val num">{tk.rows.length}</div><div class="delta mut">{$_('cost.unique')}</div></div>
</div>

<div class="grid2">
  <div class="card">
    <h3>{$_('cost.tokens_per_day')} <span class="mut">{$_('cost.api_usage')}</span></h3>
    {#if tk.series.length}
      <div style="height:140px;position:relative"><canvas bind:this={canvas}></canvas></div>
    {:else}
      <p class="mut" style="font-size:12.5px">{$_('cost.no_calls_recorded')}</p>
    {/if}
  </div>
  <div class="card">
    <h3>{$_('cost.cost_per_model')} <span class="mut">{$_('cost.price_tokens')}</span></h3>
    <table>
      <thead><tr><th>{$_('cost.model_header')}</th><th class="num" style="text-align:right">{$_('cost.token_header')}</th><th class="num" style="text-align:right">{$_('cost.call_header')}</th><th class="num" style="text-align:right">{$_('cost.cost_header')}</th></tr></thead>
      <tbody>
        {#each tk.rows as r}
          <tr>
            <td>{r.model}</td>
            <td class="num" style="text-align:right">{fmtTok(r.total_tokens)}</td>
            <td class="num mut" style="text-align:right">{r.calls}</td>
            <td class="num" style="text-align:right">{usd(r.cost_usd)}</td>
          </tr>
        {/each}
        {#if !tk.rows.length}<tr><td colspan="4" class="mut">{$_('cost.no_token_data')}</td></tr>{/if}
      </tbody>
    </table>
  </div>
</div>

<div class="card" style="margin-top:14px">
  <h3>{$_('cost.cost_per_agent')} <span class="mut">{$_('cost.claude_flow')}</span></h3>
  <table>
    <thead><tr><th>{$_('cost.agent_header')}</th><th class="num" style="text-align:right">{$_('cost.call_header')}</th><th class="num" style="text-align:right">{$_('cost.token_header')}</th><th class="num" style="text-align:right">{$_('cost.cost_header')}</th></tr></thead>
    <tbody>
      {#each tk.by_agent as a}
        <tr>
          <td>{a.agent || '—'}</td>
          <td class="num mut" style="text-align:right">{a.calls}</td>
          <td class="num" style="text-align:right">{fmtTok(a.total_tokens)}</td>
          <td class="num" style="text-align:right">{usd(a.cost_usd)}</td>
        </tr>
      {/each}
      {#if !tk.by_agent.length}<tr><td colspan="4" class="mut">{$_('cost.no_agent_calls')}</td></tr>{/if}
    </tbody>
  </table>
</div>

<div class="card" style="margin-top:14px">
  <h3>{$_('cost.request_volume')} <span class="mut">{$_('cost.liveness_provider')}</span></h3>
  <table>
    <thead><tr><th>{$_('cost.provider_header')}</th><th class="num" style="text-align:right">{$_('cost.request_header')}</th><th class="num" style="text-align:right">{$_('cost.failed_header')}</th></tr></thead>
    <tbody>
      {#each cx.providers as p}
        <tr><td>{p.name}</td><td class="num" style="text-align:right">{p.requests}</td><td class="num {p.failed ? 'down' : 'mut'}" style="text-align:right">{p.failed}</td></tr>
      {/each}
      {#if !cx.providers.length}<tr><td colspan="3" class="mut">{$_('cost.no_requests')}</td></tr>{/if}
    </tbody>
  </table>
</div>

<div class="note">✅ {$_('cost.cost_note')} {#if err}· <span class="down">{err}</span>{/if}</div>
