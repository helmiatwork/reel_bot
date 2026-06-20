<script>
  import { onMount, onDestroy } from 'svelte'
  import { page } from './lib/stores.js'
  import { api } from './lib/api.js'
  import Drawer from './lib/Drawer.svelte'
  import OpenClaw from './pages/OpenClaw.svelte'
  import Dashboard from './pages/Dashboard.svelte'
  import Sources from './pages/Sources.svelte'
  import Performance from './pages/Performance.svelte'
  import Pipeline from './pages/Pipeline.svelte'
  import Posts from './pages/Posts.svelte'
  import Agents from './pages/Agents.svelte'
  import Formulas from './pages/Formulas.svelte'
  import Clips from './pages/Clips.svelte'
  import Cost from './pages/Cost.svelte'
  import Discover from './pages/Discover.svelte'

  const NAV = [
    { p: 'openclaw', ico: '🦅', label: 'OpenClaw' },
    { p: 'dashboard', ico: '▦', label: 'Dashboard' },
    { p: 'sources', ico: '▶', label: 'Sources' },
    { p: 'clips', ico: '✂', label: 'Clips' },
    { p: 'performance', ico: '📈', label: 'Performance' },
    { p: 'pipeline', ico: '⚙', label: 'Pipeline' },
    { p: 'posts', ico: '📤', label: 'Posts' },
    { p: 'agents', ico: '🤖', label: 'Agents' },
    { p: 'formulas', ico: '✦', label: 'Formulas' },
    { p: 'cost', ico: '💰', label: 'Cost' },
    { p: 'discover', ico: '🔍', label: 'Discover' }
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
      {#each NAV as n}
        <a class:active={current === n.p} onclick={() => page.set(n.p)}>
          <span class="ico">{n.ico}</span> {n.label}
        </a>
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
    {:else if current === 'clips'}<Clips />
    {:else if current === 'performance'}<Performance />
    {:else if current === 'pipeline'}<Pipeline />
    {:else if current === 'posts'}<Posts />
    {:else if current === 'agents'}<Agents />
    {:else if current === 'formulas'}<Formulas />
    {:else if current === 'cost'}<Cost />
    {:else if current === 'discover'}<Discover />
    {/if}
  </main>
</div>

<Drawer />
