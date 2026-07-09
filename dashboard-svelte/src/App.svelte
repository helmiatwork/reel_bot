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
  import Songs from './pages/Songs.svelte'
  import Decompose from './pages/Decompose.svelte'
  import Generate from './pages/Generate.svelte'
  import Cookies from './pages/Cookies.svelte'
  import Jadwal from './pages/Jadwal.svelte'

  // Standard line icons (Lucide), monochrome, inherit text color.
  const I = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`

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
      { p: 'songs', ico: I('<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'), label: 'Songs' },
      { p: 'analysis', ico: I('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><circle cx="11.5" cy="14.5" r="2.5"/><path d="M13.3 16.3 15 18"/>'), label: 'Analysis' },
      { p: 'formulas', ico: I('<path d="M10 2v7.31"/><path d="M14 9.3V2"/><path d="M8.5 2h7"/><path d="M14 9.3a6.5 6.5 0 1 1-4 0"/><path d="M5.52 16h12.96"/>'), label: 'Formulas' },
      { p: 'decompose', ico: I('<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>'), label: 'Pecah Kompilasi' },
      { p: 'cookies', ico: I('<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'), label: 'Cookies' }
    ]},
    { title: 'Produce', items: [
      { p: 'generate', ico: I('<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>'), label: 'Generate' },
      { p: 'clipper', ico: I('<path d="M7 4v16"/><path d="M17 4v16"/><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h4"/><path d="M17 9h4"/><path d="M3 15h4"/><path d="M17 15h4"/>'), label: 'Clipper' },
      { p: 'clips', ico: I('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>'), label: 'Clips' },
      { p: 'pipeline', ico: I('<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>'), label: 'Pipeline' },
      { p: 'posts', ico: I('<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>'), label: 'Posts' },
      { p: 'jadwal', ico: I('<rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>'), label: 'Jadwal Post', badge: 'New' }
    ]},
    { title: 'Agents', items: [
      { p: 'openclaw', ico: I('<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>'), label: 'OpenClaw' },
      { p: 'agents', ico: I('<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>'), label: 'Agents' }
    ]}
  ]

  // Sample notifications (static for shell demo — wire to real endpoint when multi-user)
  const NOTIFS = [
    { id: 1, msg: 'Corpus discovery selesai — 5 video baru', time: '2 mnt lalu', read: false },
    { id: 2, msg: 'Jadwal post "Carp salt crust" jatuh tempo', time: '18 mnt lalu', read: false },
    { id: 3, msg: 'Script baru berhasil dibuat', time: '1 jam lalu', read: true },
  ]

  let current = $state('dashboard')
  page.subscribe((v) => (current = v))

  let services = $state([])
  let live = $state(0)
  let total = $state(6)
  let timer

  let rowState = $state({})
  let restartingAll = $state(false)
  let restartAllResult = $state(null)

  // Theme toggle: light (default) / dark
  let isDark = $state(false)

  // Notification dropdown
  let notifOpen = $state(false)

  function toggleTheme() {
    isDark = !isDark
    const t = isDark ? 'dark' : 'light'
    document.body.className = t
    localStorage.setItem('reelbot-theme', t)
  }

  function toggleNotif(e) {
    e.stopPropagation()
    notifOpen = !notifOpen
  }

  function closeNotif() { notifOpen = false }

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
    const saved = localStorage.getItem('reelbot-theme') || 'light'
    isDark = saved === 'dark'
    document.body.className = saved

    pollServices()
    timer = setInterval(pollServices, 8000)

    // Close notif panel on outside click
    document.addEventListener('click', closeNotif)
  })
  onDestroy(() => {
    clearInterval(timer)
    document.removeEventListener('click', closeNotif)
  })
</script>

<!-- Flat line-icon sprite (Feather/custom, currentColor) — shared DOM, accessible by all pages -->
<svg style="display:none"><defs>
  <symbol id="i-home" viewBox="0 0 24 24"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></symbol>
  <symbol id="i-spark" viewBox="0 0 24 24"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/></symbol>
  <symbol id="i-film" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M17 9h4M3 15h4M17 15h4"/></symbol>
  <symbol id="i-cookie" viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9 3 3 0 0 1-3-3 3 3 0 0 1-3-3 3 3 0 0 1-3-3Z"/><circle cx="9" cy="12" r="1"/><circle cx="14" cy="15" r="1"/><circle cx="15" cy="9" r="1"/></symbol>
  <symbol id="i-cal" viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/></symbol>
  <symbol id="i-dollar" viewBox="0 0 24 24"><path d="M12 2v20M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.6 7 6.5 9.2 9.5 12 9.5s5 1.1 5 3-2.2 3-5 3-5-1.1-5-3"/></symbol>
  <symbol id="i-bot" viewBox="0 0 24 24"><rect x="4" y="8" width="16" height="11" rx="2"/><path d="M12 8V4M9 4h6"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/></symbol>
  <symbol id="i-bell" viewBox="0 0 24 24"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M10.5 21a2 2 0 0 0 3 0"/></symbol>
  <symbol id="i-moon" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"/></symbol>
  <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></symbol>
  <symbol id="i-cart" viewBox="0 0 24 24"><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/><path d="M2 3h3l2.5 13h10L20 7H6"/></symbol>
  <symbol id="i-play" viewBox="0 0 24 24"><path d="M7 5v14l12-7z"/></symbol>
  <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></symbol>
  <symbol id="i-yt" viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="3"/><path d="M10 9.5v5l4-2.5z" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-tt" viewBox="0 0 24 24"><path d="M9 15a3 3 0 1 0 3 3V6c.7 1.8 2.3 3 4.5 3"/></symbol>
  <symbol id="i-ig" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="5"/><circle cx="12" cy="12" r="3.5"/><circle cx="16.5" cy="7.5" r=".6" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-xhs" viewBox="0 0 24 24"><path d="M4 5h16v14H4z"/><path d="M4 5l8 5 8-5"/></symbol>
  <symbol id="i-x" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></symbol>
  <symbol id="i-trash" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></symbol>
  <symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
  <!-- apps grid (3×3 dots) -->
  <symbol id="i-apps" viewBox="0 0 24 24"><rect x="3" y="3" width="4" height="4" rx="1"/><rect x="10" y="3" width="4" height="4" rx="1"/><rect x="17" y="3" width="4" height="4" rx="1"/><rect x="3" y="10" width="4" height="4" rx="1"/><rect x="10" y="10" width="4" height="4" rx="1"/><rect x="17" y="10" width="4" height="4" rx="1"/><rect x="3" y="17" width="4" height="4" rx="1"/><rect x="10" y="17" width="4" height="4" rx="1"/><rect x="17" y="17" width="4" height="4" rx="1"/></symbol>
  <!-- fullscreen expand -->
  <symbol id="i-expand" viewBox="0 0 24 24"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></symbol>
  <!-- trend arrows -->
  <symbol id="i-arrow-up-right" viewBox="0 0 24 24"><path d="M7 17 17 7M7 7h10v10"/></symbol>
  <symbol id="i-arrow-down-right" viewBox="0 0 24 24"><path d="M7 7l10 10M17 7v10H7"/></symbol>
</defs></svg>

<div class="app">
  <aside class="side">
    <div class="brand">reel<span class="ba">bot</span></div>
    <nav class="nav">
      {#each NAV_GROUPS as g}
        <div class="nav-group">{g.title}</div>
        {#each g.items as n}
          <a class:active={current === n.p} onclick={() => page.set(n.p)}>
            <span class="ico">{@html n.ico}</span>
            {n.label}
            {#if n.badge}<span class="badge-new">{n.badge}</span>{/if}
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
    <div class="topbar">
      <div class="tb-search">
        <span class="si">
          <svg class="ic"><use href="#i-search"/></svg>
        </span>
        <input placeholder="Cari konten, tag, niche…" aria-label="Search">
      </div>
      <div class="tb-spacer"></div>
      <!-- right cluster: apps · cart · expand · moon/sun · bell · avatar -->
      <span class="tb-icon" title="Apps">
        <svg class="ic"><use href="#i-apps"/></svg>
      </span>
      <span class="tb-icon" title="Cart">
        <svg class="ic"><use href="#i-cart"/></svg>
        <span class="cnt">5</span>
      </span>
      <span class="tb-icon" title="Fullscreen" onclick={() => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()}>
        <svg class="ic"><use href="#i-expand"/></svg>
      </span>
      <span class="tb-icon" onclick={toggleTheme} title="Ganti tema">
        <svg class="ic"><use href={isDark ? '#i-sun' : '#i-moon'}/></svg>
      </span>
      <!-- notification bell + dropdown -->
      <div class="tb-notif-wrap" style="position:relative">
        <span class="tb-icon" onclick={toggleNotif} title="Notifications">
          <svg class="ic"><use href="#i-bell"/></svg>
          {#if NOTIFS.filter(n => !n.read).length > 0}
            <span class="cnt">{NOTIFS.filter(n => !n.read).length}</span>
          {/if}
        </span>
        {#if notifOpen}
          <div class="notif-panel" onclick={(e) => e.stopPropagation()}>
            <div class="notif-head">Notifikasi</div>
            {#each NOTIFS as n}
              <div class="notif-row" class:unread={!n.read}>
                <div class="notif-msg">{n.msg}</div>
                <div class="notif-time">{n.time}</div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
      <div class="tb-divider"></div>
      <div class="tb-user">
        <div class="tb-avatar">H</div>
        <div>
          <div class="tb-nm">Helmi</div>
          <div class="tb-rl">Owner</div>
        </div>
      </div>
    </div>

    <div class="content">
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
      {:else if current === 'songs'}<Songs />
      {:else if current === 'decompose'}<Decompose />
      {:else if current === 'generate'}<Generate />
      {:else if current === 'cookies'}<Cookies />
      {:else if current === 'jadwal'}<Jadwal />
      {/if}
    </div>
  </main>
</div>

<Drawer />

<style>
  /* Notification panel — scoped to App shell */
  .notif-panel{
    position:absolute;top:calc(100% + 10px);right:-10px;
    width:300px;background:var(--card);border:1px solid var(--line);
    border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.15);z-index:50;overflow:hidden;
  }
  .notif-head{padding:12px 16px;font-size:13px;font-weight:600;border-bottom:1px solid var(--line)}
  .notif-row{padding:11px 16px;border-bottom:1px solid var(--line);cursor:pointer}
  .notif-row:last-child{border-bottom:0}
  .notif-row:hover{background:var(--soft)}
  .notif-row.unread .notif-msg{font-weight:600}
  .notif-msg{font-size:13px;line-height:1.4}
  .notif-time{font-size:11px;color:var(--mut);margin-top:3px}
</style>
