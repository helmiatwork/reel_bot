<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api, fmtViews, isActiveRunning } from '../lib/api.js'
  import { SOURCE_DETAIL } from '../lib/data.js'
  import { openDrawer, jobs } from '../lib/stores.js'
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
  let selectedJobRunId = $state(null)
  // Run ids we're waiting on, so we can reload the table when they finish
  let watchedRuns = $state([])

  function handleAnalyzeStarted(run_id, _label) {
    watchedRuns = [run_id, ...watchedRuns]
    selectedJobRunId = run_id
    modalOpen = false
    jobsOpen = true
    load() // the backend already inserted a 'running' row — pull it in now
  }

  function handleAlreadyExists(source) {
    modalOpen = false
    openDrawer('source', enrich(source))
  }

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

  let runningCount = $derived($jobs.filter(isActiveRunning).length)

  onMount(() => {
    load()
  })

  // Realtime: when a pending run finishes (per the shared $jobs poll), drop its optimistic
  // row and reload the table so the persisted source replaces it.
  // ponytail: a run_id always shows up in analyzeRuns(50), so a pending row can't get stuck.
  $effect(() => {
    if (!watchedRuns.length) return
    const status = new Map($jobs.map((j) => [j.run_id, j.status]))
    const finished = watchedRuns.filter((id) => {
      const st = status.get(id)
      return st === 'done' || st === 'error'
    })
    if (finished.length) {
      watchedRuns = watchedRuns.filter((id) => !finished.includes(id))
      load()
    }
  })

  function prev() { offset = Math.max(0, offset - limit); load() }
  function next() { offset = offset + limit; load() }
</script>

<div class="top">
  <div class="top-row">
    <div><h1>{$_('sources.title')}</h1><div class="sub">{$_('sources.subtitle')}</div></div>
  </div>
  <div class="pill">{total || rows.length} source</div>
</div>

<div class="filters">
  <select bind:value={niche}>
    <option value="">{$_('sources.all_niches')}</option>
    {#each niches as n}<option value={n}>{n}</option>{/each}
  </select>
  <input placeholder={$_('sources.search_title')} bind:value={q} />
  <button class="btn-secondary" onclick={() => jobsOpen = true} title={$_('sources.view_processes')}>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
    {$_('sources.processes')}
    {#if runningCount > 0}
      <span class="badge">{runningCount}</span>
    {/if}
  </button>
  <button class="btn-primary" onclick={() => modalOpen = true}>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M12 5v14M5 12h14"/></svg>
    {$_('sources.add_source')}
  </button>
</div>

<div class="card">
  <table>
    <thead>
      <tr><th>{$_('sources.title_header')}</th><th>{$_('sources.niche_header')}</th><th>{$_('sources.platform_header')}</th><th>{$_('sources.tags_header')}</th><th>{$_('sources.prompt_header')}</th><th style="text-align:right">{$_('sources.views_header')}</th><th>{$_('sources.status_header')}</th></tr>
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
          <td>{#if s.gen_prompt_format === 'prompt_json'}<span class="chip c-prompt-json">{$_('sources.format_json')}</span>{:else if s.gen_prompt_format === 'prompt_video'}<span class="chip c-prompt-text">{$_('sources.format_text')}</span>{:else}<span class="mut">—</span>{/if}</td>
          <td class="num" style="text-align:right">{s.viewsLabel}</td>
          <td>
            {#if s.status === 'running'}
              <span class="chip c-running"><span class="spin"></span>{$_('sources.status_running')}</span>
            {:else if s.status === 'processing'}
              <span class="chip c-processing">{$_('sources.status_processing')}</span>
            {:else if s.status === 'working'}
              <span class="chip c-working"><span class="spin"></span>{$_('sources.status_working')}</span>
            {:else}
              <span class="chip {s.status === 'error' ? 'c-error' : s.status === 'used' ? 'c-used' : 'c-done'}">{s.status}</span>
            {/if}
          </td>
        </tr>
      {/each}
      {#if !filtered.length}
        <tr><td colspan="7" class="mut">{$_('sources.no_sources')}</td></tr>
      {/if}
    </tbody>
  </table>
</div>

<Pagination {offset} {limit} {total} onprev={prev} onnext={next} />

<SourceUploadModal bind:isOpen={modalOpen} onSuccess={() => { modalOpen = false; load() }} onAnalyzeStarted={handleAnalyzeStarted} onAlreadyExists={handleAlreadyExists} />
<JobsPopup bind:isOpen={jobsOpen} bind:initialRunId={selectedJobRunId} />

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
