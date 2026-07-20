<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api, fmtViews } from '../lib/api.js'
  import { FALLBACK_MOVERS } from '../lib/data.js'
  import LineChart from '../lib/LineChart.svelte'

  let kpis = $state({ sources: 0, total_views: 0, produced: 0, formulas: 0, clips: 0 })
  let channel = $state({ total_views: 0, avg_view_pct: 0, avg_duration: 0, series: [], top_videos: [], error: null })
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

      // channel analytics from YouTube (live)
      if (o.channel) {
        channel = o.channel
      }

      // build chart from channel.series (daily views for our own channel)
      const channelSeries = (o.channel && o.channel.series) ? o.channel.series : []
      const lset = new Set()
      channelSeries.forEach((s) => s.points.forEach((p) => lset.add(p.d)))
      labels = [...lset].sort()
      datasets = channelSeries.map((s, i) => ({
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
    <h1>{$_('dashboard.title')}</h1>
    <div class="sub">{$_('dashboard.subtitle')}</div>
  </div>
  <div class="pill">⟳ live · @HReelBot</div>
</div>

<div class="kpis">
  <div class="card kpi">
    <div class="label">{$_('dashboard.sources_analyzed')}</div>
    <div class="val num">{kpis.sources}</div>
    <div class="delta up">{$_('dashboard.from_research_lib')}</div>
  </div>
  <div class="card kpi">
    <div class="label">{$_('dashboard.total_views')}</div>
    {#if channel.error}
      <div class="val mut" style="font-size:13px">{$_('dashboard.analytics_not_ready')}</div>
    {:else}
      <div class="val num">{fmtViews(channel.total_views)}</div>
    {/if}
    <div class="delta up">{$_('dashboard.youtube_90d')}</div>
  </div>
  <div class="card kpi">
    <div class="label">{$_('dashboard.avg_retention')}</div>
    <div class="val num">{channel.avg_view_pct.toFixed(1)}%</div>
    <div class="delta mut">{$_('dashboard.avg_view_duration', { values: { duration: channel.avg_duration } })}</div>
  </div>
  <div class="card kpi">
    <div class="label">{$_('dashboard.formulas_clips')}</div>
    <div class="val num">{kpis.formulas} <span class="mut" style="font-size:14px">/ {kpis.clips}</span></div>
    <div class="delta mut">{$_('dashboard.formula_clip_desc')}</div>
  </div>
</div>

<div class="grid2">
  <div class="card">
    <h3>{$_('dashboard.trend_views')} <span class="mut">{$_('dashboard.trend_views_90d')}</span></h3>
    {#if loaded && datasets.length}
      <LineChart {labels} {datasets} height={118} />
    {:else}
      <p class="mut" style="font-size:12.5px">
        {#if channel.error}{$_('dashboard.analytics_error', { values: { error: channel.error } })}{:else}{$_('dashboard.no_channel_data')}{/if}
      </p>
    {/if}
  </div>
  <div class="card">
    <h3>{$_('dashboard.top_performing')} <span class="mut">{$_('dashboard.top_views_label')}</span></h3>
    <table>
      <thead><tr><th>{$_('dashboard.video_header')}</th><th style="text-align:right">{$_('dashboard.views_header')}</th><th style="text-align:right">{$_('dashboard.retention_header')}</th></tr></thead>
      <tbody>
        {#each channel.top_videos as m}
          <tr>
            <td>{m.title}</td>
            <td class="num up" style="text-align:right">{fmtViews(m.views)}</td>
            <td class="num mut" style="text-align:right">{m.retention.toFixed(1)}%</td>
          </tr>
        {:else}
          {#each movers as m}
            <tr><td>{m.title}</td><td class="num {m.up ? 'up' : 'mut'}" style="text-align:right">{m.rate}</td><td></td></tr>
          {/each}
        {/each}
      </tbody>
    </table>
  </div>
</div>

{#if !usingReal}
  <div class="note">{$_('dashboard.db_unavailable')}</div>
{/if}
