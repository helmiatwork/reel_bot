<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import { FORMULAS } from '../lib/data.js'
  import { openDrawer } from '../lib/stores.js'

  let formulas = $state(FORMULAS.map((f) => ({ ...f, avg_views: 0, n: 0 })))
  let hasPerf = $state(false)

  onMount(async () => {
    const [tbl, perf] = await Promise.all([api.table('formulas'), api.formulaPerformance()])
    const inDb = new Set((tbl?.rows || []).map((r) => r.slug))
    const pmap = {}
    ;(perf?.rows || []).forEach((r) => (pmap[r.slug] = r))
    if (perf?.rows?.some((r) => r.n > 0)) hasPerf = true

    formulas = FORMULAS.map((f) => {
      const p = pmap[f.slug] || {}
      return { ...f, db: inDb.has(f.slug) || f.db, avg_views: p.avg_views || 0, n: p.n || 0 }
    }).sort((a, b) => b.avg_views - a.avg_views || (b.db === a.db ? 0 : b.db ? 1 : -1))
  })

  const clip = (s) => (s.length > 64 ? s.slice(0, 64) + '…' : s)
</script>

<div class="top">
  <div><h1>Formulas</h1><div class="sub">Struktur viral — diurut performa (avg views per formula)</div></div>
  <div class="pill">{formulas.length} formula</div>
</div>

{#if hasPerf}
  <div class="note" style="background:rgba(52,211,153,.08);border-color:rgba(52,211,153,.25);color:#6ee7b7;margin-top:0;margin-bottom:14px">
    ✅ Diurut dari avg views tertinggi — formula paling atas = paling perform di source kamu.
  </div>
{/if}

<div class="card">
  <div class="fcards">
    {#each formulas as f}
      <div class="fcard" onclick={() => openDrawer('formula', f)}>
        <div class="t" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          {f.slug}
          {#if f.db}<span class="m-chip s-active">di DB</span>{:else}<span class="m-chip s-mod">usul</span>{/if}
          {#if f.n > 0}<span class="m-chip m-vision" style="margin-left:auto">{fmtViews(f.avg_views)} avg · {f.n} src</span>{/if}
        </div>
        <div class="s">{f.face} · Best: {f.best}</div>
        <div class="s"><code>{clip(f.struct)}</code></div>
      </div>
    {/each}
  </div>
</div>
