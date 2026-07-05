<script>
  import { onMount, onDestroy } from 'svelte'
  import { page } from './lib/stores.js'
  import { api } from './lib/api.js'
  import Drawer from './lib/Drawer.svelte'
  import OpenClaw from './pages/OpenClaw.svelte'
  import Dashboard from './pages/Dashboard.svelte'
  import Sources from './pages/Sources.svelte'
  import Analysis from './pages/Analysis.svelte'
  import Performance from './pages/Performance.svelte'
  import Pipeline from './pages/Pipeline.svelte'
  import Posts from './pages/Posts.svelte'
  import Agents from './pages/Agents.svelte'
  import Formulas from './pages/Formulas.svelte'
  import Clips from './pages/Clips.svelte'
  import Clipper from './pages/Clipper.svelte'
  import Snoop from './pages/Snoop.svelte'
  import Cost from './pages/Cost.svelte'
  import Discover from './pages/Discover.svelte'
  import Creators from './pages/Creators.svelte'

  // Standard line icons (Lucide), monochrome, inherit text color.
  const I = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`
  // Menu grouped by purpose. Each group renders under a section header.
  const NAV_GROUPS = [
    { title: 'Overview', items: [
      { p: 'dashboard', ico: I('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>'), label: 'Dashboard' },
      { p: 'performance', ico: I('<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>'), label: 'Performance' },
      { p: 'cost', ico: I('<line x1="12" x2="12" y1="2" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>'), label: 'Cost' }
    ]},
    { title: 'Discover & Analyze', items: [
      { p: 'discover', ico: I('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'), label: 'Discover' },
      { p: 'sources', ico: I('<path d="m22 8-6 4 6 4V8z"/><rect x="2" y="6" width="14" height="12" rx="2"/>'), label: 'Sources' },
      { p: 'snoop', ico: I('<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>'), label: 'Snoop' },
      { p: 'creators', ico: I('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'), label: 'Creators' },
      { p: 'analysis', ico: I('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><circle cx="11.5" cy="14.5" r="2.5"/><path d="M13.3 16.3 15 18"/>'), label: 'Analysis' },
      { p: 'formulas', ico: I('<path d="M10 2v7.31"/><path d="M14 9.3V2"/><path d="M8.5 2h7"/><path d="M14 9.3a6.5 6.5 0 1 1-4 0"/><path d="M5.52 16h12.96"/>'), label: 'Formulas' }
    ]},
    { title: 'Produce', items: [
      { p: 'clipper', ico: I('<path d="M7 4v16"/><path d="M17 4v16"/><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h4"/><path d="M17 9h4"/><path d="M3 15h4"/><path d="M17 15h4"/>'), label: 'Clipper' },
      { p: 'clips', ico: I('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>'), label: 'Clips' },
      { p: 'pipeline', ico: I('<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>'), label: 'Pipeline' },
      { p: 'posts', ico: I('<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>'), label: 'Posts' }
    ]},
    { title: 'Agents', items: [
      { p: 'openclaw', ico: I('<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>'), label: 'OpenClaw' },
      { p: 'agents', ico: I('<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>'), label: 'Agents' }
    ]}
  ]

  let current = $state('dashboard')
  page.subscribe((v) => (current = v))

  let services = $state([])
  let live = $state(0)
  let total = $state(6)
  let timer

  // per-row restart state: { [name]: { busy: bool, result: string|null } }
  let rowState = $state({})
  let restartingAll = $state(false)
  let restartAllResult = $state(null)

  async function pollServices() {
    const r = await api.services()
    if (r && r.services) {
      services = r.services
      live = r.live
      total = r.total
    }
  }

  async function restartSvc(name) {
    rowState = { ...rowState, [name]: { busy: true, result: null } }
    const r = await api.restartService(name)
    const result = r ? r.status : 'error'
    rowState = { ...rowState, [name]: { busy: false, result } }
    // clear label after 3 s then refresh dots
    setTimeout(() => {
      rowState = { ...rowState, [name]: { busy: false, result: null } }
    }, 3000)
    await pollServices()
  }

  async function restartAllSvcs() {
    if (!confirm('Restart all services? This will cycle every running service.')) return
    restartingAll = true
    restartAllResult = null
    const r = await api.restartAll()
    restartingAll = false
    if (r) {
      restartAllResult = `${r.restarted} restarted`
    } else {
      restartAllResult = 'error'
    }
    setTimeout(() => { restartAllResult = null }, 4000)
    await pollServices()
  }

  onMount(() => {
    pollServices()
    timer = setInterval(pollServices, 8000)
  })
  onDestroy(() => clearInterval(timer))
</script>

<div class="app">
  <aside class="side">
    <div class="brand"><span class="dot"></span> ContentOps</div>
    <nav class="nav">
      {#each NAV_GROUPS as g}
        <div class="nav-group">{g.title}</div>
        {#each g.items as n}
          <a class:active={current === n.p} onclick={() => page.set(n.p)}>
            <span class="ico">{@html n.ico}</span> {n.label}
          </a>
        {/each}
      {/each}
    </nav>
    <div class="foot">
      <div class="badge-row">
        <div class="badge-live" class:partial={live < total}>stack — {live}/{total} live</div>
        <button
          class="btn-restart-all"
          disabled={restartingAll}
          onclick={restartAllSvcs}
          title="Restart all services"
        >{restartingAll ? '⟳' : '⟳ all'}</button>
      </div>
      {#if restartAllResult}
        <div class="restart-result" class:err={restartAllResult === 'error'}>{restartAllResult}</div>
      {/if}
      <div class="svclist">
        {#each services as s}
          {@const rs = rowState[s.name] || { busy: false, result: null }}
          <div class="svc" class:up={s.up} class:down={!s.up} class:busy={rs.busy}>
            <span class="led"></span>
            <span class="svc-name">{s.name}</span>
            <span class="port">{s.port}</span>
            {#if s.name !== 'pipeline-api'}
              <button
                class="btn-restart-row"
                disabled={rs.busy}
                onclick={() => restartSvc(s.name)}
                title="Restart {s.name}"
              >{rs.busy ? '…' : '⟳'}</button>
            {/if}
            {#if rs.result}
              <span class="row-result" class:ok={rs.result === 'restarted'} class:err={rs.result === 'error' || rs.result === 'not_running'}>{rs.result}</span>
            {/if}
          </div>
        {/each}
        {#if !services.length}
          <div class="svc down"><span class="led"></span> menghubungkan…</div>
        {/if}
      </div>
    </div>
  </aside>

  <main class="main">
    {#if current === 'openclaw'}<OpenClaw />
    {:else if current === 'dashboard'}<Dashboard />
    {:else if current === 'sources'}<Sources />
    {:else if current === 'analysis'}<Analysis />
    {:else if current === 'clips'}<Clips />
    {:else if current === 'clipper'}<Clipper />
    {:else if current === 'snoop'}<Snoop />
    {:else if current === 'performance'}<Performance />
    {:else if current === 'pipeline'}<Pipeline />
    {:else if current === 'posts'}<Posts />
    {:else if current === 'agents'}<Agents />
    {:else if current === 'formulas'}<Formulas />
    {:else if current === 'cost'}<Cost />
    {:else if current === 'discover'}<Discover />
    {:else if current === 'creators'}<Creators />
    {/if}
  </main>
</div>

<Drawer />
