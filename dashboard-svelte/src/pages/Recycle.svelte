<script>
  import { onMount, onDestroy } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { pushToast } from '../lib/stores.js'

  let url = $state('')
  let recipes = $state([])
  let selected = $state(null)
  let formulas = $state([])   // all formulas, so an old recipe's formula name still resolves
  let formulaId = $state('')  // '' = AI picks
  let targetMin = $state('')  // minutes in the form; sent as seconds
  let loadError = $state('')
  let busy = $state(false)
  let timer = null

  const activeFormulas = $derived(formulas.filter((f) => f.active))
  const formulaName = (id) => formulas.find((f) => f.id === id)?.name

  const secs = (t) => {
    if (typeof t === 'number') return Math.floor(t)
    return String(t ?? '').split(':').reduce((a, p) => a * 60 + (parseFloat(p) || 0), 0) | 0
  }
  // source_url was validated as http(s) YouTube on the server; re-check before building a link
  function link(src, t) {
    try {
      const u = new URL(src)
      if (u.protocol !== 'https:' && u.protocol !== 'http:') return null
      u.searchParams.set('t', secs(t) + 's')
      return u.toString()
    } catch (e) { return null }
  }

  // minutes -> seconds for the API; null = AI chooses; NaN = outside 30-3600 s
  function targetSecs() {
    if (targetMin === '' || targetMin == null) return null
    const s = Math.round(Number(targetMin) * 60)
    return s >= 30 && s <= 3600 ? s : NaN
  }

  // tokens/cost as the backend stored them (rows from before usage tracking have none)
  const usageVals = (u) => ({
    inp: String(u.prompt_tokens ?? 0), out: String(u.completion_tokens ?? 0),
    cost: Number(u.cost_usd ?? 0).toFixed(4), n: String(u.attempts ?? 0), model: String(u.model ?? '-')
  })

  async function load() {
    const r = await api.atmRecycles()
    if (!r.ok) { loadError = $_('atm.load_error'); return }
    loadError = ''
    recipes = r.data.recipes
    if (selected) await pick(selected.id, true)
    schedule()
  }

  async function loadFormulas() {
    const r = await api.atmFormulas()
    if (r.ok) formulas = r.data.formulas
    else loadError = $_('atm.load_error')
  }

  function schedule() {
    clearTimeout(timer)
    if (recipes.some((x) => x.status === 'building') || selected?.status === 'building') timer = setTimeout(load, 5000)
  }

  async function pick(id, quiet = false) {
    const r = await api.atmRecycle(id)
    if (r.ok) selected = r.data
    else if (!quiet) pushToast('error', $_('atm.load_error'))
  }

  async function create() {
    if (!url.trim()) return
    const target = targetSecs()
    if (Number.isNaN(target)) { pushToast('error', $_('atm.recycle_bad_target')); return }
    busy = true
    const r = await api.atmRecycleCreate(url.trim(), {
      formula_id: formulaId ? Number(formulaId) : null,
      target_duration_s: target
    })
    busy = false
    if (r.ok) { url = ''; pushToast('success', $_('atm.recycle_created')); await load() }
    else pushToast('error', r.status === 400
      ? (typeof r.data?.detail === 'string' ? r.data.detail : $_('atm.recycle_bad_url'))
      : $_('atm.load_error'))
  }

  async function rebuild(id) {
    const r = await api.atmRecycleRebuild(id)
    if (r.ok) await load()
    else pushToast('error', r.status === 409 ? $_('atm.recycle_still_building') : $_('atm.load_error'))
  }

  async function remove(x) {
    if (!confirm($_('atm.recycle_delete_confirm'))) return
    const r = await api.atmRecycleDelete(x.id)
    if (!r.ok) { pushToast('error', $_('atm.load_error')); return }
    if (selected?.id === x.id) selected = null
    await load()
  }

  onMount(() => { load(); loadFormulas() })
  onDestroy(() => clearTimeout(timer))
</script>

<div class="recycle">
  <div class="page-top">
    <h1>{$_('atm.recycle_title')}</h1>
    <div class="sub">{$_('atm.recycle_subtitle')}</div>
  </div>
  {#if loadError}<div class="err">{loadError}</div>{/if}

  <div class="bar">
    <input type="url" bind:value={url} placeholder={$_('atm.recycle_url_ph')} onkeydown={(e) => e.key === 'Enter' && create()} />
    <select bind:value={formulaId} aria-label={$_('atm.recycle_formula')}>
      <option value="">{$_('atm.recycle_formula_auto')}</option>
      {#each activeFormulas as f (f.id)}<option value={String(f.id)}>{f.name}</option>{/each}
    </select>
    <input class="target" type="number" min="0.5" max="60" step="0.5" bind:value={targetMin}
      placeholder={$_('atm.recycle_target_ph')} aria-label={$_('atm.recycle_target_ph')} />
    <button class="btn" disabled={busy || !url.trim()} onclick={create}>{$_('atm.recycle_create')}</button>
  </div>

  <div class="grid2">
    <div class="panel">
      {#if !recipes.length}<div class="mut">{$_('atm.recycle_none')}</div>{/if}
      {#each recipes as x (x.id)}
        <div class="row">
          <button class="link" onclick={() => pick(x.id)}>
            <span class="badge {x.status}">{$_('atm.recycle_' + x.status)}</span>
            <span class="content">{x.source_title || x.source_url}</span>
            {#if x.usage}<span class="usage">{$_('atm.recycle_usage', { values: usageVals(x.usage) })}</span>{/if}
          </button>
          <button class="del" onclick={() => remove(x)}>{$_('atm.delete')}</button>
        </div>
      {/each}
    </div>

    <div class="panel wide">
      {#if selected?.usage}<div class="usage">{$_('atm.recycle_usage', { values: usageVals(selected.usage) })}</div>{/if}
      {#if !selected}
        <div class="mut">{$_('atm.recycle_pick')}</div>
      {:else if selected.status === 'error'}
        <div class="err">{selected.error}</div>
        <button class="btn" onclick={() => rebuild(selected.id)}>{$_('atm.recycle_rebuild')}</button>
      {:else if selected.status === 'building'}
        <div class="mut">{$_('atm.recycle_building')}...</div>
        <button class="btn" onclick={() => rebuild(selected.id)}>{$_('atm.recycle_rebuild')}</button>
      {:else if selected.recipe}
        {@const r = selected.recipe}
        <div class="head">
          <div>
            <span class="badge">{formulaName(selected.formula_id) ?? r.formula}</span>
            {#if r.formula_reason}<div class="mut">{r.formula_reason}</div>{/if}
          </div>
          {#if r.target_duration_s}<div class="mut">{$_('atm.recycle_target')}: {Math.round(r.target_duration_s)}s</div>{/if}
        </div>
        <h3>{$_('atm.recycle_angle')}</h3>
        <div class="content">{r.angle}</div>
        <h3>{$_('atm.recycle_titles')}</h3>
        <ul>{#each r.titles ?? [] as t}<li>{t}</li>{/each}</ul>
        <h3>{$_('atm.recycle_value')}</h3>
        <div class="content">
          {$_('atm.recycle_score')}: {r.added_value?.score}/10 · {$_('atm.recycle_risk')}: {r.added_value?.reused_content_risk}
          <div class="mut">{r.added_value?.why}</div>
          <ul>{#each r.added_value?.tips ?? [] as t}<li>{t}</li>{/each}</ul>
        </div>
        <h3>{$_('atm.recycle_credit')}</h3>
        <div class="content">{r.credit}</div>

        {#if r.beats}
          <h3>{$_('atm.recycle_beats')}</h3>
          {#each r.beats as b, i}
            <div class="beat">
              <div class="beat-head">
                <span class="beat-name">{i + 1}. {b.beat}</span>
                <span class="mut">{b.out_start}-{b.out_end}</span>
                <span class="badge">{b.emotion}</span>
              </div>
              <div class="beat-row"><span class="mut">{$_('atm.recycle_narration')}</span><div class="content">{b.narration}</div></div>
              <div class="beat-row"><span class="mut">{$_('atm.recycle_music')}</span><div>{b.music}</div></div>
              <div class="beat-row">
                <span class="mut">{$_('atm.recycle_clips')}</span>
                <ul class="clips">
                  {#each b.clips ?? [] as c}
                    {@const href = link(selected.source_url, c.source_start)}
                    <li>
                      {#if href}<a {href} target="_blank" rel="noopener noreferrer">{c.source_start}-{c.source_end}</a>{:else}{c.source_start}-{c.source_end}{/if}
                      <span class="badge">{c.treatment}</span>
                      {#if c.repeat}<span class="badge">{$_('atm.recycle_repeat')}</span>{/if}
                      <span class="mut">{c.note}</span>
                    </li>
                  {/each}
                </ul>
              </div>
            </div>
          {/each}
        {:else if r.timeline}
          <div class="scroll">
            <table>
              <thead><tr>
                <th>{$_('atm.recycle_col_out')}</th><th>{$_('atm.recycle_col_src')}</th><th>{$_('atm.recycle_col_emotion')}</th>
                <th>{$_('atm.recycle_col_music')}</th><th>{$_('atm.recycle_col_vo')}</th><th>{$_('atm.recycle_col_note')}</th>
              </tr></thead>
              <tbody>
                {#each r.timeline as row}
                  {@const href = link(selected.source_url, row.source_start)}
                  <tr>
                    <td>{row.out_start}-{row.out_end}</td>
                    <td>{#if href}<a {href} target="_blank" rel="noopener noreferrer">{row.source_start}-{row.source_end}</a>{:else}{row.source_start}-{row.source_end}{/if}</td>
                    <td>{row.emotion}</td>
                    <td>{row.music}</td>
                    <td>{row.narration}</td>
                    <td>{#if row.repeat}<span class="badge">{$_('atm.recycle_repeat')}</span> {/if}{row.note}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      {/if}
    </div>
  </div>
</div>

<style>
  .recycle { padding: 0 2px 32px; }
  .page-top { margin-bottom: 18px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }
  .bar { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
  .bar input { flex: 1; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; color: var(--txt); padding: 7px 10px; font-size: 13px; }
  .bar .target { flex: 0 0 170px; }
  .bar select { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; color: var(--txt); padding: 7px 10px; font-size: 13px; max-width: 260px; }
  .btn { background: var(--accent); color: #fff; border: 0; border-radius: 6px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .btn:disabled { opacity: .5; cursor: default; }
  .grid2 { display: grid; grid-template-columns: minmax(260px, 1fr) 3fr; gap: 14px; align-items: start; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; min-width: 0; }
  .panel h3 { margin: 12px 0 4px; font-size: 14px; font-weight: 650; }
  .row { display: flex; justify-content: space-between; gap: 10px; border-top: 1px solid var(--line); padding: 8px 2px; font-size: 13px; }
  .link { background: none; border: 0; text-align: left; color: var(--txt); cursor: pointer; padding: 0; }
  .link:hover .content { color: var(--accent); }
  .content { font-size: 13px; line-height: 1.4; }
  .usage { display: block; color: var(--mut); font-size: 11.5px; margin: 2px 0 6px; }
  .head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .beat { border-top: 1px solid var(--line); padding: 10px 0; }
  .beat-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
  .beat-name { font-weight: 650; font-size: 13px; }
  .beat-row { display: flex; gap: 10px; font-size: 13px; margin-top: 3px; }
  .beat-row > .mut { min-width: 64px; }
  .clips { margin: 0; }
  .clips li { margin-bottom: 3px; }
  .del { background: none; border: 1px solid var(--line); border-radius: 6px; color: var(--mut); font-size: 11.5px; padding: 3px 9px; cursor: pointer; align-self: flex-start; }
  .del:hover { color: var(--red, #f87171); border-color: var(--red, #f87171); }
  .badge { background: rgba(99,102,241,.15); color: var(--accent); font-size: 10.5px; border-radius: 4px; padding: 1px 6px; }
  .badge.error { color: var(--red, #f87171); }
  .badge.ready { color: var(--green, #4ade80); }
  .err { color: var(--red, #f87171); font-size: 12.5px; margin-bottom: 8px; }
  .mut { color: var(--mut); font-size: 12.5px; }
  .scroll { overflow-x: auto; margin-top: 14px; }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
  th, td { text-align: left; vertical-align: top; border-top: 1px solid var(--line); padding: 6px 8px; }
  th { color: var(--mut); font-weight: 600; }
  ul { margin: 4px 0; padding-left: 18px; font-size: 13px; }
</style>
