<script>
  import { onMount, onDestroy } from 'svelte'
  import { page } from './lib/stores.js'
  import { api } from './lib/api.js'
  import Drawer from './lib/Drawer.svelte'
  import Studio from './pages/Studio.svelte'
  import Dashboard from './pages/Dashboard.svelte'
  import Sources from './pages/Sources.svelte'
  import Performance from './pages/Performance.svelte'
  import Pipeline from './pages/Pipeline.svelte'
  import Posts from './pages/Posts.svelte'
  import Agents from './pages/Agents.svelte'
  import Formulas from './pages/Formulas.svelte'
  import Clips from './pages/Clips.svelte'
  import Cost from './pages/Cost.svelte'

  const NAV = [
    { p: 'studio', ico: '✨', label: 'Studio' },
    { p: 'dashboard', ico: '▦', label: 'Dashboard' },
    { p: 'sources', ico: '▶', label: 'Sources' },
    { p: 'clips', ico: '✂', label: 'Clips' },
    { p: 'performance', ico: '📈', label: 'Performance' },
    { p: 'pipeline', ico: '⚙', label: 'Pipeline' },
    { p: 'posts', ico: '📤', label: 'Posts' },
    { p: 'agents', ico: '🤖', label: 'Agents' },
    { p: 'formulas', ico: '✦', label: 'Formulas' },
    { p: 'cost', ico: '💰', label: 'Cost' }
  ]

  let current = $state('dashboard')
  page.subscribe((v) => (current = v))

  let services = $state([])
  let live = $state(0)
  let total = $state(6)
  let timer

  async function pollServices() {
    const r = await api.services()
    if (r && r.services) {
      services = r.services
      live = r.live
      total = r.total
    }
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
      <div class="badge-live" class:partial={live < total}>stack — {live}/{total} live</div>
      <div class="svclist">
        {#each services as s}
          <div class="svc" class:up={s.up} class:down={!s.up}>
            <span class="led"></span> {s.name} <span class="port">{s.port}</span>
          </div>
        {/each}
        {#if !services.length}
          <div class="svc down"><span class="led"></span> menghubungkan…</div>
        {/if}
      </div>
    </div>
  </aside>

  <main class="main">
    {#if current === 'studio'}<Studio />
    {:else if current === 'dashboard'}<Dashboard />
    {:else if current === 'sources'}<Sources />
    {:else if current === 'clips'}<Clips />
    {:else if current === 'performance'}<Performance />
    {:else if current === 'pipeline'}<Pipeline />
    {:else if current === 'posts'}<Posts />
    {:else if current === 'agents'}<Agents />
    {:else if current === 'formulas'}<Formulas />
    {:else if current === 'cost'}<Cost />
    {/if}
  </main>
</div>

<Drawer />
