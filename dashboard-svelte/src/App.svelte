<script>
  import { onMount, onDestroy } from 'svelte'
  import { page, jobs, pushToast, beepSuccess, beepError } from './lib/stores.js'
  import { api } from './lib/api.js'
  import Drawer from './lib/Drawer.svelte'
  import Toasts from './lib/Toasts.svelte'
  import HowItWorks from './components/HowItWorks.svelte'
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
  import PublishAccounts from './pages/PublishAccounts.svelte'
  import Jadwal from './pages/Jadwal.svelte'
  import Seo from './pages/Seo.svelte'
  import Prep from './pages/Prep.svelte'
  import Studio from './pages/Studio.svelte'

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
      { p: 'seo', ico: I('<line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/><line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/>'), label: 'SEO' },
      { p: 'sources', ico: I('<path d="m22 8-6 4 6 4V8z"/><rect x="2" y="6" width="14" height="12" rx="2"/>'), label: 'Sources' },
      { p: 'snoop', ico: I('<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>'), label: 'Snoop' },
      { p: 'creators', ico: I('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'), label: 'Creators' },
      { p: 'songs', ico: I('<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'), label: 'Songs' },
      { p: 'analysis', ico: I('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><circle cx="11.5" cy="14.5" r="2.5"/><path d="M13.3 16.3 15 18"/>'), label: 'Analysis' },
      { p: 'formulas', ico: I('<path d="M10 2v7.31"/><path d="M14 9.3V2"/><path d="M8.5 2h7"/><path d="M14 9.3a6.5 6.5 0 1 1-4 0"/><path d="M5.52 16h12.96"/>'), label: 'Formulas' },
      { p: 'decompose', ico: I('<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>'), label: 'Pecah Kompilasi' },
      { p: 'cookies', ico: I('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'), label: 'Scrape Accounts' }
    ]},
    { title: 'Produce', items: [
      { p: 'generate', ico: I('<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>'), label: 'Generate' },
      { p: 'clipper', ico: I('<path d="M7 4v16"/><path d="M17 4v16"/><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h4"/><path d="M17 9h4"/><path d="M3 15h4"/><path d="M17 15h4"/>'), label: 'Clipper' },
      { p: 'clips', ico: I('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>'), label: 'Clips' },
      { p: 'pipeline', ico: I('<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>'), label: 'Pipeline' },
      { p: 'posts', ico: I('<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>'), label: 'Posts' },
      { p: 'publish-accounts', ico: I('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M19 8l2 2 4-4"/>'), label: 'Publish Accounts' },
      { p: 'jadwal', ico: I('<rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>'), label: 'Jadwal Post', badge: 'New' },
      { p: 'prep', ico: I('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'), label: 'Prep' },
      { p: 'studio', ico: I('<rect x="3" y="3" width="18" height="4" rx="1"/><rect x="3" y="10" width="18" height="4" rx="1"/><rect x="3" y="17" width="18" height="4" rx="1"/>'), label: 'Studio', badge: 'New' }
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
  let jobPollTimer = null
  let prevJobsSnapshot = new Map() // ponytail: track prev status for transition detection

  let rowState = $state({})
  let restartingAll = $state(false)
  let restartAllResult = $state(null)

  // Theme toggle: light (default) / dark
  let isDark = $state(false)

  // Notification dropdown
  let notifOpen = $state(false)

  // How-it-works walkthrough
  let tourOpen = $state(false)

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

  async function pollJobs() {
    try {
      const data = await api.analyzeRuns(50)
      if (data) {
        jobs.set(data)
        // Detect transitions: running → done/error
        let isFirstPoll = prevJobsSnapshot.size === 0
        data.forEach(job => {
          const prev = prevJobsSnapshot.get(job.run_id)
          if (!isFirstPoll && prev && prev.status === 'running') {
            if (job.status === 'done') {
              const toastTitle = 'Analisa selesai'
              const toastSub = job.title || (job.url ? (job.url.startsWith('file://') ? 'Upload file' : job.url.substring(0, 45) + '…') : '—')
              pushToast('success', toastTitle, toastSub)
              beepSuccess()
            } else if (job.status === 'error') {
              const toastTitle = 'Analisa gagal'
              const msg = job.last_msg || job.error || '—'
              pushToast('error', toastTitle, msg.substring(0, 60))
              beepError()
            }
          }
          prevJobsSnapshot.set(job.run_id, { status: job.status })
        })
      }
    } catch (e) {
      // polling recovers next tick
    }
  }

  onMount(() => {
    const saved = localStorage.getItem('reelbot-theme') || 'light'
    isDark = saved === 'dark'
    document.body.className = saved

    pollServices()
    timer = setInterval(pollServices, 8000)

    // App-wide job poller
    pollJobs()
    jobPollTimer = setInterval(pollJobs, 5000)

    // Close notif panel on outside click
    document.addEventListener('click', closeNotif)
  })
  onDestroy(() => {
    clearInterval(timer)
    if (jobPollTimer) clearInterval(jobPollTimer)
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
  <symbol id="i-play" viewBox="0 0 24 24"><path d="M7 5v14l12-7z"/></symbol>
  <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></symbol>
  <!-- brand logos — fill:currentColor, no stroke -->
  <symbol id="i-yt" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></symbol>
  <symbol id="i-tt" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></symbol>
  <symbol id="i-ig" viewBox="0 0 24 24"><path fill="currentColor" stroke="none" d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></symbol>
  <!-- ponytail: self-colored RED badge, no currentColor needed -->
  <symbol id="i-xhs" viewBox="0 0 24 24"><rect x="0" y="0" width="24" height="24" rx="5" fill="#FF2442"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="8" font-weight="bold" font-family="sans-serif">RED</text></symbol>
  <symbol id="i-x" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></symbol>
  <symbol id="i-trash" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></symbol>
  <symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
  <!-- fullscreen expand -->
  <symbol id="i-expand" viewBox="0 0 24 24"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></symbol>
  <!-- help / question-mark-in-circle -->
  <symbol id="i-help" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.82 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor"/></symbol>
  <!-- trend arrows -->
  <symbol id="i-arrow-up-right" viewBox="0 0 24 24"><path d="M7 17 17 7M7 7h10v10"/></symbol>
  <symbol id="i-arrow-down-right" viewBox="0 0 24 24"><path d="M7 7l10 10M17 7v10H7"/></symbol>
  <!-- chart-type toggle icons (stroke, inherit from svg.ic) -->
  <symbol id="i-chart-table" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="1"/><path d="M3 9h18M3 15h18M9 3v18"/></symbol>
  <symbol id="i-chart-bar"   viewBox="0 0 24 24"><path d="M3 20h18M6 20V13M10 20V8M14 20V11M18 20V5"/></symbol>
  <symbol id="i-chart-line"  viewBox="0 0 24 24"><polyline points="3 17 8 11 13 14 21 6"/></symbol>
  <symbol id="i-chart-area"  viewBox="0 0 24 24"><polyline points="3 17 8 11 13 14 21 6"/><path d="M21 6V20H3V17"/></symbol>
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
      <!-- right cluster: help · expand · moon/sun · bell · avatar -->
      <span class="tb-icon" title="How Reelbot works" onclick={() => tourOpen = true} role="button" tabindex="0" onkeydown={(e) => e.key === 'Enter' && (tourOpen = true)} aria-label="Open walkthrough">
        <svg class="ic"><use href="#i-help"/></svg>
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
      {:else if current === 'publish-accounts'}<PublishAccounts />
      {:else if current === 'jadwal'}<Jadwal />
      {:else if current === 'seo'}<Seo />
      {:else if current === 'prep'}<Prep />
      {:else if current === 'studio'}<Studio />
      {/if}
    </div>
  </main>
</div>

<Drawer />
<Toasts />
<HowItWorks bind:open={tourOpen} />

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
