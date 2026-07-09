<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'

  // ── State ────────────────────────────────────────────────────────────────────
  let items = $state([])
  let counts = $state({ total: 0, today: 0, overdue: 0, scheduled: 0, draft: 0, posted: 0 })
  let loading = $state(true)
  let activeTab = $state('semua')

  // Detail modal
  let modal = $state(null)   // null = closed, else item being edited
  let saving = $state(false)
  let saveErr = $state('')

  // Create flow: step 0=closed, 1=corpus picker, 2=schedule form
  let createStep = $state(0)
  let corpus = $state([])
  let corpusLoading = $state(false)
  let pickedRef = $state(null)  // corpus item picked in step 1
  let newForm = $state(emptyForm())

  // URL paste per platform (in modal)
  let urlInputs = $state({})

  const PLATFORMS = ['youtube', 'tiktok', 'instagram', 'xiaohongshu']

  // ponytail: render SVG brand logos for platforms; remove text labels
  const PLATFORM_ICON = {
    youtube: 'i-yt', tiktok: 'i-tt', instagram: 'i-ig', xiaohongshu: 'i-xhs'
  }

  const STATUS_LABEL = {
    draft: 'Draft', scheduled: 'Terjadwal', posted: 'Diposting', overdue: 'Terlambat'
  }

  const TABS = [
    { id: 'semua', label: 'Semua' },
    { id: 'today', label: 'Hari Ini' },
    { id: 'overdue', label: 'Overdue' },
    { id: 'scheduled', label: 'Scheduled' },
    { id: 'draft', label: 'Draft' },
    { id: 'posted', label: 'Diposting' }
  ]

  function emptyForm() {
    return {
      title: '',
      platforms: [],
      scheduled_at: '',
      caption: '',
      thumb_url: '',
      source_url: '',
      content_ref: ''
    }
  }

  // ── Derived status per item ──────────────────────────────────────────────────
  function itemStatus(item) {
    const targets = platformList(item.platforms)
    const urls = item.platform_urls || {}
    const allPosted = targets.length > 0 && targets.every(p => urls[p])
    if (allPosted) return 'posted'
    if (!item.scheduled_at) return 'draft'
    const dt = new Date(item.scheduled_at)
    if (dt < new Date()) return 'overdue'
    return 'scheduled'
  }

  function platformList(csv) {
    if (!csv) return []
    return csv.split(',').map(s => s.trim()).filter(Boolean)
  }

  // ── Fetch ────────────────────────────────────────────────────────────────────
  async function loadItems() {
    loading = true
    const r = await api.scheduleList()
    if (r) {
      items = r.items || []
      counts = r.counts || counts
    }
    loading = false
  }

  // ── Filtering ────────────────────────────────────────────────────────────────
  let filtered = $derived.by(() => {
    if (activeTab === 'semua') return items
    if (activeTab === 'today') return items.filter(i => {
      if (!i.scheduled_at) return false
      const d = new Date(i.scheduled_at)
      const now = new Date()
      return d.toDateString() === now.toDateString()
    })
    return items.filter(i => itemStatus(i) === activeTab)
  })

  // ── Modal helpers ────────────────────────────────────────────────────────────
  function openModal(item) {
    modal = { ...item, platforms: platformList(item.platforms) }
    urlInputs = {}
    saveErr = ''
  }

  function closeModal() { modal = null; saveErr = '' }

  function togglePlatform(p) {
    if (!modal) return
    const urls = modal.platform_urls || {}
    if (urls[p]) return  // posted — locked
    const idx = modal.platforms.indexOf(p)
    if (idx >= 0) {
      modal = { ...modal, platforms: modal.platforms.filter(x => x !== p) }
    } else {
      modal = { ...modal, platforms: [...modal.platforms, p] }
    }
  }

  function chipState(p) {
    if (!modal) return 'off'
    const urls = modal.platform_urls || {}
    if (urls[p]) return 'posted'
    return modal.platforms.includes(p) ? 'on' : 'off'
  }

  async function savePlatformUrl(p) {
    const url = (urlInputs[p] || '').trim()
    if (!url || !modal) return
    const merged = { ...(modal.platform_urls || {}), [p]: url }
    const r = await api.scheduleUpdate(modal.id, { platform_urls: merged })
    if (r && r.id) {
      modal = { ...modal, platform_urls: merged }
      urlInputs = { ...urlInputs, [p]: '' }
      await loadItems()
    }
  }

  async function saveModal() {
    if (!modal) return
    saving = true; saveErr = ''
    const payload = {
      title: modal.title,
      platforms: modal.platforms.join(','),
      scheduled_at: modal.scheduled_at ?? '',
      caption: modal.caption || '',
      thumb_url: modal.thumb_url || '',
      source_url: modal.source_url || ''
    }
    const r = modal.id
      ? await api.scheduleUpdate(modal.id, payload)
      : await api.scheduleCreate(payload)
    saving = false
    if (r && r.id) {
      closeModal()
      await loadItems()
    } else {
      saveErr = 'Gagal menyimpan, coba lagi.'
    }
  }

  async function deleteItem(id) {
    if (!confirm('Hapus jadwal ini?')) return
    await api.scheduleDelete(id)
    closeModal()
    await loadItems()
  }

  // ── Create flow ──────────────────────────────────────────────────────────────
  async function openCreate() {
    createStep = 1
    corpusLoading = true
    corpus = []
    pickedRef = null
    newForm = emptyForm()
    const r = await api.scheduleCorpus()
    corpus = r || []
    corpusLoading = false
  }

  function pickCorpus(item) {
    pickedRef = item
    newForm = {
      ...newForm,
      title: item.title || '',
      content_ref: item.ref || '',
      thumb_url: item.thumb || '',
      source_url: item.source_url || ''
    }
    createStep = 2
  }

  async function submitCreate() {
    saving = true; saveErr = ''
    const payload = {
      title: newForm.title,
      platforms: newForm.platforms.join(','),
      scheduled_at: newForm.scheduled_at || null,
      caption: newForm.caption || '',
      thumb_url: newForm.thumb_url || '',
      source_url: newForm.source_url || '',
      content_ref: newForm.content_ref || ''
    }
    const r = await api.scheduleCreate(payload)
    saving = false
    if (r && r.id) {
      createStep = 0
      await loadItems()
    } else {
      saveErr = 'Gagal membuat jadwal.'
    }
  }

  function toggleNewPlatform(p) {
    const idx = newForm.platforms.indexOf(p)
    if (idx >= 0) {
      newForm = { ...newForm, platforms: newForm.platforms.filter(x => x !== p) }
    } else {
      newForm = { ...newForm, platforms: [...newForm.platforms, p] }
    }
  }

  // ── Formatting ───────────────────────────────────────────────────────────────
  function fmtDate(iso) {
    if (!iso) return '—'
    return new Date(iso).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  function toDatetimeLocal(iso) {
    if (!iso) return ''
    const d = new Date(iso)
    const pad = n => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  }

  onMount(loadItems)
</script>

<div class="page">
  <!-- Header -->
  <div class="ph">
    <div>
      <div class="ptitle">Jadwal Post</div>
      <div class="pbread">Produce › Jadwal Post</div>
    </div>
    <button class="btn" onclick={openCreate}>+ Jadwalkan Post</button>
  </div>

  <!-- Stat cards -->
  <div class="cards">
    <div class="card">
      <div class="card-inner">
        <div>
          <div class="card-label">TOTAL TERJADWAL</div>
          <div class="card-num">{counts.total}</div>
          <div class="card-trend neutral">{counts.scheduled} aktif</div>
        </div>
        <div class="card-ico accent">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/></svg>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-inner">
        <div>
          <div class="card-label">HARI INI</div>
          <div class="card-num">{counts.today}</div>
          <div class="card-trend up">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M7 17 17 7M7 7h10v10"/></svg>
            {counts.today} hari ini
          </div>
        </div>
        <div class="card-ico green">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-inner">
        <div>
          <div class="card-label">OVERDUE</div>
          <div class="card-num">{counts.overdue}</div>
          <div class="card-trend" class:down={counts.overdue > 0} class:neutral={counts.overdue === 0}>
            {#if counts.overdue > 0}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M7 7l10 10M17 7v10H7"/></svg>
              perlu perhatian
            {:else}
              semua on track
            {/if}
          </div>
        </div>
        <div class="card-ico red">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-inner">
        <div>
          <div class="card-label">SUDAH DIPOSTING</div>
          <div class="card-num">{counts.posted}</div>
          <div class="card-trend up">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M7 17 17 7M7 7h10v10"/></svg>
            {counts.posted} selesai
          </div>
        </div>
        <div class="card-ico amber">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>
        </div>
      </div>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    {#each TABS as t}
      <button class="tab" class:active={activeTab === t.id} onclick={() => activeTab = t.id}>
        {t.label}
      </button>
    {/each}
  </div>

  <!-- Grid -->
  {#if loading}
    <div class="empty-state">Memuat jadwal…</div>
  {:else if filtered.length === 0}
    <div class="empty-state">Tidak ada item. <button class="link" onclick={openCreate}>+ Buat jadwal baru</button></div>
  {:else}
    <div class="grid">
      {#each filtered as item (item.id)}
        {@const st = itemStatus(item)}
        {@const plist = platformList(item.platforms)}
        <div class="tile" onclick={() => openModal(item)}>
          <div class="thumb">
            {#if item.thumb_url}
              <img src={item.thumb_url} alt={item.title} loading="lazy">
            {:else}
              <div class="thumb-ph">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 5v14l12-7z"/></svg>
              </div>
            {/if}
            <span class="status-pill {st}">{STATUS_LABEL[st]}</span>
          </div>
          <div class="tile-body">
            <div class="tile-title">{item.title || '(tanpa judul)'}</div>
            <div class="tile-meta">
              <span class="tile-date">{fmtDate(item.scheduled_at)}</span>
            </div>
            <div class="tile-plats">
              {#each plist as p}
                <span class="plat-badge {p}" class:posted={(item.platform_urls || {})[p]}>
                  <svg class="plat-ico {p}"><use href="#{PLATFORM_ICON[p] || 'i-yt'}"/></svg>
                </span>
              {/each}
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Detail Modal -->
{#if modal}
  <div class="overlay" onclick={closeModal}>
    <div class="modal" onclick={(e) => e.stopPropagation()}>
      <div class="modal-head">
        <div class="modal-title">{modal.id ? 'Edit Jadwal' : 'Jadwal Baru'}</div>
        <button class="close-btn" onclick={closeModal}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>

      <!-- Video thumb placeholder -->
      <div class="modal-thumb">
        {#if modal.thumb_url}
          <img src={modal.thumb_url} alt={modal.title}>
        {:else}
          <div class="thumb-ph-lg">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 5v14l12-7z"/></svg>
          </div>
        {/if}
      </div>

      <!-- Form -->
      <div class="modal-form">
        <label>
          <span>Judul</span>
          <input bind:value={modal.title} placeholder="Judul konten…">
        </label>

        <label>
          <span>Platform tujuan</span>
          <div class="chip-row">
            {#each PLATFORMS as p}
              {@const state = chipState(p)}
              {@const urls = modal.platform_urls || {}}
              <div class="chip-wrap">
                <button
                  class="chip {state}"
                  disabled={state === 'posted'}
                  onclick={() => togglePlatform(p)}
                >
                  {#if state === 'posted'}
                    <svg class="chip-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5"/></svg>
                  {:else}
                    <svg class="chip-ico plat-ico {p}"><use href="#{PLATFORM_ICON[p] || 'i-yt'}"/></svg>
                  {/if}
                </button>
                {#if state === 'posted' && urls[p]}
                  <a class="posted-url" href={urls[p]} target="_blank" rel="noopener">{urls[p].slice(0, 32)}…</a>
                {:else if state === 'on'}
                  <div class="url-row">
                    <input
                      class="url-input"
                      placeholder="Tempel URL hasil upload…"
                      bind:value={urlInputs[p]}
                    >
                    <button class="btn-sm" onclick={() => savePlatformUrl(p)} disabled={!urlInputs[p]}>Simpan</button>
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        </label>

        <label>
          <span>Tanggal & waktu post</span>
          <input type="datetime-local" value={toDatetimeLocal(modal.scheduled_at)}
            oninput={(e) => modal = { ...modal, scheduled_at: e.target.value ? new Date(e.target.value).toISOString() : '' }}>
        </label>

        <label>
          <span>Caption</span>
          <textarea bind:value={modal.caption} rows="3" placeholder="Caption untuk semua platform…"></textarea>
        </label>

        {#if saveErr}
          <div class="form-err">{saveErr}</div>
        {/if}

        <div class="modal-actions">
          {#if modal.id}
            <button class="btn-danger" onclick={() => deleteItem(modal.id)}>Hapus</button>
          {/if}
          <button class="btn-outline" onclick={closeModal}>Batal</button>
          <button class="btn" onclick={saveModal} disabled={saving}>
            {saving ? 'Menyimpan…' : 'Simpan'}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Create flow: step 1 = corpus picker -->
{#if createStep === 1}
  <div class="overlay" onclick={() => createStep = 0}>
    <div class="modal modal-lg" onclick={(e) => e.stopPropagation()}>
      <div class="modal-head">
        <div class="modal-title">Pilih Konten (1/2)</div>
        <button class="close-btn" onclick={() => createStep = 0}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>
      {#if corpusLoading}
        <div class="empty-state">Memuat corpus…</div>
      {:else if corpus.length === 0}
        <div class="empty-state">Tidak ada konten teranalisis. Jalankan Discover terlebih dahulu.</div>
      {:else}
        <div class="corpus-grid">
          {#each corpus as c}
            <div class="corpus-tile" onclick={() => pickCorpus(c)}>
              {#if c.thumb}
                <img src={c.thumb} alt={c.title}>
              {:else}
                <div class="thumb-ph-sm">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 5v14l12-7z"/></svg>
                </div>
              {/if}
              <div class="corpus-title">{c.title || c.ref}</div>
              {#if c.retention}
                <div class="corpus-ret">{c.retention}% retensi</div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      <div class="modal-actions">
        <button class="btn-outline" onclick={() => { pickedRef = null; createStep = 2 }}>Lewati — buat manual</button>
      </div>
    </div>
  </div>
{/if}

<!-- Create flow: step 2 = schedule form -->
{#if createStep === 2}
  <div class="overlay" onclick={() => createStep = 0}>
    <div class="modal" onclick={(e) => e.stopPropagation()}>
      <div class="modal-head">
        <div class="modal-title">Atur Jadwal (2/2)</div>
        <button class="close-btn" onclick={() => createStep = 0}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>

      {#if pickedRef?.thumb}
        <div class="modal-thumb"><img src={pickedRef.thumb} alt={newForm.title}></div>
      {/if}

      <div class="modal-form">
        <label>
          <span>Judul</span>
          <input bind:value={newForm.title} placeholder="Judul konten…">
        </label>

        <label>
          <span>Platform tujuan</span>
          <div class="chip-row">
            {#each PLATFORMS as p}
              <button class="chip {newForm.platforms.includes(p) ? 'on' : 'off'}" onclick={() => toggleNewPlatform(p)}>
                <svg class="chip-ico plat-ico {p}"><use href="#{PLATFORM_ICON[p] || 'i-yt'}"/></svg>
              </button>
            {/each}
          </div>
        </label>

        <label>
          <span>Tanggal & waktu post</span>
          <input type="datetime-local" bind:value={newForm.scheduled_at}>
        </label>

        <label>
          <span>Caption</span>
          <textarea bind:value={newForm.caption} rows="3" placeholder="Caption untuk semua platform…"></textarea>
        </label>

        {#if saveErr}
          <div class="form-err">{saveErr}</div>
        {/if}

        <div class="modal-actions">
          <button class="btn-outline" onclick={() => createStep = 1}>Kembali</button>
          <button class="btn" onclick={submitCreate} disabled={saving}>
            {saving ? 'Menyimpan…' : 'Jadwalkan'}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .page{padding:0}
  .ph{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:22px}
  .ptitle{font-size:18px;font-weight:700;color:var(--txt)}
  .pbread{font-size:12px;color:var(--mut);margin-top:2px}

  /* Stat cards */
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;margin-bottom:22px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px}
  .card-inner{display:flex;justify-content:space-between;align-items:center}
  .card-label{font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--mut);text-transform:uppercase;margin-bottom:6px}
  .card-num{font-size:26px;font-weight:700;color:var(--txt);line-height:1}
  .card-trend{display:flex;align-items:center;gap:4px;font-size:12px;margin-top:6px}
  .card-trend svg{width:13px;height:13px;flex-shrink:0}
  .card-trend.up{color:var(--green)}
  .card-trend.down{color:var(--red)}
  .card-trend.neutral{color:var(--mut)}
  .card-ico{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}
  .card-ico svg{width:20px;height:20px}
  .card-ico.accent{background:rgba(64,81,137,.12);color:var(--accent)}
  .card-ico.green{background:rgba(10,179,156,.12);color:var(--green)}
  .card-ico.red{background:rgba(240,101,72,.12);color:var(--red)}
  .card-ico.amber{background:rgba(247,184,75,.15);color:var(--amber)}

  /* Tabs */
  .tabs{display:flex;gap:2px;background:var(--soft);border-radius:8px;padding:3px;margin-bottom:20px;width:fit-content;flex-wrap:wrap}
  .tab{padding:6px 14px;border:none;background:transparent;border-radius:6px;font-size:13px;font-weight:500;color:var(--mut);cursor:pointer;transition:all .15s}
  .tab:hover{color:var(--txt)}
  .tab.active{background:var(--panel);color:var(--accent);box-shadow:0 1px 4px rgba(0,0,0,.1)}

  /* Grid */
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:14px}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;cursor:pointer;transition:box-shadow .15s}
  .tile:hover{box-shadow:0 4px 16px rgba(0,0,0,.1)}
  .thumb{position:relative;aspect-ratio:9/16;background:var(--soft);overflow:hidden}
  .thumb img{width:100%;height:100%;object-fit:cover}
  .thumb-ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--mut)}
  .thumb-ph svg{width:32px;height:32px}
  .status-pill{position:absolute;top:8px;left:8px;font-size:10px;font-weight:700;padding:3px 8px;border-radius:20px}
  .status-pill.draft{background:rgba(135,138,153,.2);color:var(--mut)}
  .status-pill.scheduled{background:rgba(64,81,137,.15);color:var(--accent)}
  .status-pill.posted{background:rgba(10,179,156,.15);color:var(--green)}
  .status-pill.overdue{background:rgba(240,101,72,.15);color:var(--red)}
  .tile-body{padding:10px 12px}
  .tile-title{font-size:13px;font-weight:600;color:var(--txt);margin-bottom:4px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
  .tile-meta{font-size:11px;color:var(--mut);margin-bottom:6px}
  .tile-plats{display:flex;gap:4px;flex-wrap:wrap}
  .plat-badge{font-size:10px;font-weight:700;padding:4px 8px;border-radius:6px;background:var(--soft);color:var(--mut);display:flex;align-items:center;gap:4px}
  .plat-ico{width:14px;height:14px;flex-shrink:0;fill:currentColor;stroke:none}
  .plat-badge.youtube .plat-ico{color:#FF0000}
  .plat-badge.tiktok .plat-ico{color:#000}
  .plat-badge.instagram .plat-ico{color:#E4405F}
  .plat-badge.xiaohongshu .plat-ico{color:#FF2442}
  .plat-badge.posted{background:rgba(10,179,156,.1);color:var(--green)}
  /* dark mode: tiktok white text/icon in dark theme */
  :global(.dark) .plat-badge.tiktok .plat-ico{color:#fff}

  /* Overlay & modal */
  .overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:100;padding:20px}
  .modal{background:var(--panel);border-radius:14px;width:100%;max-width:480px;max-height:90vh;overflow-y:auto;box-shadow:0 16px 48px rgba(0,0,0,.22)}
  .modal-lg{max-width:760px}
  .modal-head{display:flex;justify-content:space-between;align-items:center;padding:18px 20px 0}
  .modal-title{font-size:15px;font-weight:700;color:var(--txt)}
  .close-btn{width:28px;height:28px;border:none;background:transparent;cursor:pointer;color:var(--mut);display:flex;align-items:center;justify-content:center;border-radius:6px}
  .close-btn:hover{background:var(--soft);color:var(--txt)}
  .close-btn svg{width:16px;height:16px}
  .modal-thumb{padding:14px 20px 0}
  .modal-thumb img{width:100%;max-height:140px;object-fit:cover;border-radius:8px}
  .thumb-ph-lg{height:120px;background:var(--soft);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--mut)}
  .thumb-ph-lg svg{width:36px;height:36px}
  .modal-form{padding:16px 20px 20px;display:flex;flex-direction:column;gap:14px}
  .modal-form label{display:flex;flex-direction:column;gap:5px}
  .modal-form label span{font-size:12px;font-weight:600;color:var(--mut)}
  .modal-form input,.modal-form textarea{border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13px;background:var(--bg);color:var(--txt);outline:none;transition:border-color .15s}
  .modal-form input:focus,.modal-form textarea:focus{border-color:var(--accent)}
  .modal-form textarea{resize:vertical;font-family:inherit}
  .modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:4px}
  .form-err{font-size:12px;color:var(--red);background:rgba(240,101,72,.08);padding:8px 10px;border-radius:6px}

  /* Chips */
  .chip-row{display:flex;gap:8px;flex-wrap:wrap}
  .chip-wrap{display:flex;flex-direction:column;gap:4px}
  .chip{padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;border:1.5px solid var(--line);background:var(--bg);color:var(--mut);transition:all .15s;display:flex;align-items:center;gap:6px}
  .chip:disabled{cursor:default;opacity:1}
  .chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
  .chip.off:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
  .chip.posted{background:rgba(10,179,156,.1);border-color:var(--green);color:var(--green);display:flex;align-items:center;gap:4px}
  .chip-ico{width:14px;height:14px;flex-shrink:0;fill:currentColor;stroke:none}
  /* chip brand colors — stay colored in all states */
  .chip .plat-ico.youtube{color:#FF0000}
  .chip .plat-ico.tiktok{color:#000}
  .chip .plat-ico.instagram{color:#E4405F}
  .chip .plat-ico.xiaohongshu{color:#FF2442}
  :global(.dark) .chip .plat-ico.tiktok{color:#fff}
  .posted-url{font-size:11px;color:var(--accent);word-break:break-all;max-width:160px}
  .url-row{display:flex;gap:6px;align-items:center}
  .url-input{border:1px solid var(--line);border-radius:6px;padding:5px 8px;font-size:12px;background:var(--bg);color:var(--txt);outline:none;min-width:0;flex:1}
  .url-input:focus{border-color:var(--accent)}
  .btn-sm{padding:5px 10px;background:var(--accent);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap}
  .btn-sm:disabled{opacity:.5;cursor:default}

  /* Corpus picker */
  .corpus-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;padding:16px 20px;max-height:380px;overflow-y:auto}
  .corpus-tile{cursor:pointer;border-radius:8px;overflow:hidden;border:1.5px solid var(--line);background:var(--card);transition:border-color .15s}
  .corpus-tile:hover{border-color:var(--accent)}
  .corpus-tile img{width:100%;aspect-ratio:16/9;object-fit:cover}
  .thumb-ph-sm{aspect-ratio:16/9;background:var(--soft);display:flex;align-items:center;justify-content:center;color:var(--mut)}
  .thumb-ph-sm svg{width:22px;height:22px}
  .corpus-title{font-size:12px;font-weight:600;padding:6px 8px 2px;color:var(--txt);display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
  .corpus-ret{font-size:11px;color:var(--green);padding:0 8px 8px;font-weight:600}

  /* Misc */
  .empty-state{text-align:center;padding:48px 24px;color:var(--mut);font-size:14px}
  .link{background:none;border:none;color:var(--accent);cursor:pointer;font-size:14px;text-decoration:underline;padding:0}
  .btn{padding:8px 18px;background:var(--accent);color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer}
  .btn:disabled{opacity:.6;cursor:default}
  .btn-outline{padding:8px 16px;background:transparent;color:var(--txt);border:1.5px solid var(--line);border-radius:8px;font-size:13px;font-weight:500;cursor:pointer}
  .btn-outline:hover{border-color:var(--accent);color:var(--accent)}
  .btn-danger{padding:8px 14px;background:transparent;color:var(--red);border:1.5px solid var(--red);border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;margin-right:auto}
  .btn-danger:hover{background:rgba(240,101,72,.08)}
</style>
