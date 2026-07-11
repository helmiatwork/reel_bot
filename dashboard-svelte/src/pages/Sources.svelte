<script>
  import { onMount } from 'svelte'
  import { api, fmtViews } from '../lib/api.js'
  import { SOURCE_DETAIL } from '../lib/data.js'
  import { openDrawer } from '../lib/stores.js'
  import Pagination from '../lib/Pagination.svelte'
  import SourceUploadModal from '../lib/SourceUploadModal.svelte'
  import JobsPopup from '../lib/JobsPopup.svelte'

  let rows = $state([])
  let total = $state(0)
  let offset = $state(0)
  const limit = 25
  let q = $state('')
  let niche = $state('')
  let modalOpen = $state(false)
  let jobsOpen = $state(false)
  let jobs = $state([])
  let jobsPollInterval = $state(null)

  const PLATFORM_ICON = {
    youtube: 'i-yt', tiktok: 'i-tt', instagram: 'i-ig', xiaohongshu: 'i-xhs'
  }

  function fmtPlatform(p) {
    if (!p || p === '-') return { icon: null, label: '—' }
    const labels = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram', xiaohongshu: 'Xiaohongshu' }
    return { icon: PLATFORM_ICON[p], label: labels[p] || p }
  }

  function enrich(r) {
    const d = SOURCE_DETAIL[r.id] || {}
    return {
      id: r.id,
      title: r.title,
      channel: r.channel,
      status: r.status,
      views: r.views,
      viewsLabel: fmtViews(r.views),
      // AI-inferred category from DB; fall back to SOURCE_DETAIL, never platform
      niche: r.niche && r.niche !== '-' ? r.niche : (d.niche || '-'),
      platform: r.platform || '-',
      formula: d.formula || '-',
      tags: d.tags || [],
      dur: d.dur || '-',
      res: d.res || '-',
      lang: d.lang || '-',
      hook: d.hook || '-',
      clip: d.clip ?? false,
      face: d.face ?? false,
      sum: d.sum || '',
      gen_prompt_format: r.gen_prompt_format || '',
      // ponytail: youtube_url carried for frames drawer; absent from /dash/table/sources SELECT (blocker noted)
      youtube_url: r.youtube_url || null
    }
  }

  async function load() {
    const t = await api.table('sources', limit, offset)
    if (t && t.rows) {
      rows = t.rows.map(enrich)
      total = t.total ?? 0
    }
  }

  let filtered = $derived(
    rows.filter(
      (r) =>
        (!q || r.title.toLowerCase().includes(q.toLowerCase())) &&
        (!niche || r.niche === niche)
    )
  )
  let niches = $derived([...new Set(rows.map((r) => r.niche))].filter((n) => n && n !== '-'))

  let runningCount = $derived(jobs.filter(j => j.status === 'running').length)

  onMount(() => {
    load()
    pollJobs()
    jobsPollInterval = setInterval(pollJobs, 5000)
    return () => {
      if (jobsPollInterval) clearInterval(jobsPollInterval)
    }
  })

  async function pollJobs() {
    const data = await api.analyzeRuns(50)
    if (data) jobs = data
  }

  function prev() { offset = Math.max(0, offset - limit); load() }
  function next() { offset = offset + limit; load() }
</script>

<div class="top">
  <div class="top-row">
    <div><h1>Sources</h1><div class="sub">Library riset — klik baris buat detail</div></div>
  </div>
  <div class="pill">{total || rows.length} source</div>
</div>

<div class="filters">
  <select bind:value={niche}>
    <option value="">Semua niche</option>
    {#each niches as n}<option value={n}>{n}</option>{/each}
  </select>
  <input placeholder="cari judul..." bind:value={q} />
  <button class="btn-secondary" onclick={() => jobsOpen = true} title="Lihat daftar proses">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
    Proses
    {#if runningCount > 0}
      <span class="badge">{runningCount}</span>
    {/if}
  </button>
  <button class="btn-primary" onclick={() => modalOpen = true}>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M12 5v14M5 12h14"/></svg>
    Tambah source
  </button>
</div>

<div class="card">
  <table>
    <thead>
      <tr><th>Judul</th><th>Niche</th><th>Platform</th><th>Tags</th><th>Prompt</th><th style="text-align:right">Views</th><th>Status</th></tr>
    </thead>
    <tbody>
      {#each filtered as s}
        {@const plat = fmtPlatform(s.platform)}
        <tr onclick={() => openDrawer('source', s)}>
          <td>{s.title}</td>
          <td>{s.niche}</td>
          <td>
            {#if plat.icon}
              <div style="display:flex;align-items:center;gap:0.25rem">
                <svg class="plat-ico {s.platform}" style="width:14px;height:14px"><use href="#{plat.icon}"/></svg>
                <span>{plat.label}</span>
              </div>
            {:else}
              {plat.label}
            {/if}
          </td>
          <td>{#each s.tags.slice(0, 3) as t}<span class="tag">{t}</span>{/each}</td>
          <td>{#if s.gen_prompt_format === 'prompt_json'}<span class="chip c-prompt-json">JSON</span>{:else if s.gen_prompt_format === 'prompt_video'}<span class="chip c-prompt-text">Text</span>{:else}<span class="mut">—</span>{/if}</td>
          <td class="num" style="text-align:right">{s.viewsLabel}</td>
          <td><span class="chip {s.status === 'used' ? 'c-used' : 'c-analyzed'}">{s.status}</span></td>
        </tr>
      {/each}
      {#if !filtered.length}
        <tr><td colspan="7" class="mut">Belum ada source di DB.</td></tr>
      {/if}
    </tbody>
  </table>
</div>

<Pagination {offset} {limit} {total} onprev={prev} onnext={next} />

<SourceUploadModal bind:isOpen={modalOpen} onSuccess={() => { modalOpen = false; load() }} />
<JobsPopup bind:isOpen={jobsOpen} />

<style>
  .top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .btn-primary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    transition: opacity 0.2s;
    white-space: nowrap;
  }

  .btn-primary:hover {
    opacity: 0.9;
  }

  .btn-secondary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    background: var(--bg-alt);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    transition: all 0.2s;
    white-space: nowrap;
  }

  .btn-secondary:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 0.375rem;
    background: var(--accent);
    color: white;
    border-radius: 10px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-left: 0.25rem;
  }
</style>
