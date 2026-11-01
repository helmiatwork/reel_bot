<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { pushToast } from '../lib/stores.js'

  // Same set as recycle_rules.EMOTIONS on the backend (the server validates again)
  const EMOTIONS = ['sedih', 'senang', 'tegang', 'marah', 'haru', 'lucu', 'penasaran']

  let formulas = $state([])
  let loadError = $state('')
  let form = $state(null) // null = closed; id null = new formula
  let busy = $state(false)

  let total = $derived(form ? form.beats.reduce((a, b) => a + (Number(b.pct) || 0), 0) : 0)

  const blankBeat = () => ({ name: '', pct: 0, emotion: 'penasaran', goal: '' })
  const beatsSummary = (f) => f.beats.map((b) => `${b.name} ${b.pct}%`).join(' · ')

  async function load() {
    const r = await api.atmFormulas()
    if (!r.ok) { loadError = $_('atm.load_error'); return }
    loadError = ''
    formulas = r.data.formulas
  }

  // 400 detail = list of messages from the backend; 409 = slug already taken
  function errText(r) {
    if (r.status === 409) return $_('atm.formulas_slug_taken')
    const d = r.data?.detail
    return Array.isArray(d) ? d.filter((x) => typeof x === 'string').join(' · ') : typeof d === 'string' ? d : ''
  }

  function payload(f) {
    return {
      slug: f.slug.trim(), name: f.name.trim(), fits: (f.fits ?? '').trim(), sort: f.sort, active: f.active,
      beats: f.beats.map((b) => ({ name: b.name.trim(), pct: b.pct, emotion: b.emotion, goal: (b.goal ?? '').trim() }))
    }
  }

  function openNew() {
    form = { id: null, slug: '', name: '', fits: '', sort: 0, active: true, beats: [blankBeat()] }
  }

  function openEdit(f) {
    form = {
      id: f.id, slug: f.slug, name: f.name, fits: f.fits ?? '', sort: f.sort, active: f.active,
      beats: f.beats.map((b) => ({ name: b.name, pct: b.pct, emotion: b.emotion, goal: b.goal ?? '' }))
    }
  }

  async function save() {
    busy = true
    const body = payload(form)
    const r = form.id ? await api.atmFormulaUpdate(form.id, body) : await api.atmFormulaCreate(body)
    busy = false
    if (r.ok) { pushToast('success', $_('atm.formulas_saved')); form = null; await load() }
    else pushToast('error', $_('atm.formulas_save_error'), errText(r))
  }

  async function toggle(f) {
    const r = await api.atmFormulaUpdate(f.id, payload({ ...f, active: !f.active }))
    await load() // resync the checkbox with the server either way
    if (!r.ok) pushToast('error', $_('atm.formulas_save_error'), errText(r))
  }

  async function remove(f) {
    if (!confirm($_('atm.formulas_delete_confirm'))) return
    const r = await api.atmFormulaDelete(f.id)
    if (!r.ok) { pushToast('error', $_('atm.load_error')); return }
    pushToast('success', $_('atm.formulas_deleted'))
    if (form?.id === f.id) form = null
    await load()
  }

  function addBeat() { form.beats.push(blankBeat()) }
  function removeBeat(i) { form.beats.splice(i, 1) }

  onMount(load)
</script>

<div class="formulas">
  <div class="page-top top-row">
    <div>
      <h1>{$_('atm.formulas_title')}</h1>
      <div class="sub">{$_('atm.formulas_subtitle')}</div>
    </div>
    <button class="btn" onclick={openNew} disabled={!!form}>{$_('atm.formulas_add')}</button>
  </div>
  {#if loadError}<div class="err">{loadError}</div>{/if}

  {#if form}
    <div class="panel">
      <h3>{form.id ? $_('atm.formulas_form_edit') : $_('atm.formulas_form_new')}</h3>
      <div class="fields">
        <label>{$_('atm.formulas_field_name')}<input bind:value={form.name} /></label>
        <label>{$_('atm.formulas_field_slug')}<input bind:value={form.slug} placeholder="pas" /></label>
        <label>{$_('atm.formulas_field_fits')}<input bind:value={form.fits} /></label>
        <label>{$_('atm.formulas_field_sort')}<input type="number" bind:value={form.sort} /></label>
        <label class="check"><input type="checkbox" bind:checked={form.active} /> {$_('atm.formulas_field_active')}</label>
      </div>

      <div class="scroll">
        <table>
          <thead><tr>
            <th>{$_('atm.formulas_beat_name')}</th><th>{$_('atm.formulas_beat_pct')}</th><th>{$_('atm.formulas_beat_emotion')}</th>
            <th>{$_('atm.formulas_beat_goal')}</th><th></th>
          </tr></thead>
          <tbody>
            {#each form.beats as b, i}
              <tr>
                <td><input bind:value={b.name} /></td>
                <td><input type="number" min="0" max="100" class="pct" bind:value={b.pct} /></td>
                <td>
                  <select bind:value={b.emotion}>
                    {#each EMOTIONS as e}<option value={e}>{e}</option>{/each}
                  </select>
                </td>
                <td><input bind:value={b.goal} /></td>
                <td><button class="del" onclick={() => removeBeat(i)} disabled={form.beats.length <= 1}>{$_('atm.delete')}</button></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <div class="foot">
        <button class="link-btn" onclick={addBeat}>{$_('atm.formulas_add_beat')}</button>
        <span class="total" class:bad={total !== 100}>{$_('atm.formulas_total', { values: { n: total } })}</span>
        <span class="spacer"></span>
        <button class="btn ghost" onclick={() => (form = null)}>{$_('atm.formulas_cancel')}</button>
        <button class="btn" onclick={save} disabled={busy}>{$_('atm.formulas_save')}</button>
      </div>
    </div>
  {/if}

  <div class="panel">
    {#if !formulas.length}<div class="mut">{$_('atm.formulas_none')}</div>{/if}
    {#if formulas.length}
      <div class="scroll">
        <table>
          <thead><tr>
            <th>{$_('atm.formulas_col_name')}</th><th>{$_('atm.formulas_col_slug')}</th><th>{$_('atm.formulas_col_fits')}</th>
            <th>{$_('atm.formulas_col_beats')}</th><th>{$_('atm.formulas_col_active')}</th><th></th>
          </tr></thead>
          <tbody>
            {#each formulas as f (f.id)}
              <tr class:off={!f.active}>
                <td>{f.name}</td>
                <td><code>{f.slug}</code></td>
                <td>{f.fits || '-'}</td>
                <td class="sum">{beatsSummary(f)}</td>
                <td><input type="checkbox" checked={f.active} onchange={() => toggle(f)} aria-label={$_('atm.formulas_col_active')} /></td>
                <td class="acts">
                  <button class="del" onclick={() => openEdit(f)}>{$_('atm.formulas_edit')}</button>
                  <button class="del" onclick={() => remove(f)}>{$_('atm.delete')}</button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</div>

<style>
  .formulas { padding: 0 2px 32px; }
  .page-top { margin-bottom: 18px; }
  .top-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; min-width: 0; }
  .panel h3 { margin: 0 0 10px; font-size: 14px; font-weight: 650; }
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px 14px; margin-bottom: 12px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--mut); }
  label.check { flex-direction: row; align-items: center; align-self: end; gap: 6px; color: var(--txt); }
  input, select { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; color: var(--txt); padding: 6px 8px; font-size: 13px; font-family: inherit; min-width: 0; }
  tbody input, tbody select { width: 100%; }
  .pct { width: 70px !important; }
  .foot { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
  .spacer { flex: 1; }
  .total { font-size: 12.5px; color: var(--mut); }
  .total.bad { color: var(--red, #f87171); font-weight: 650; }
  .btn { background: var(--accent); color: #fff; border: 0; border-radius: 6px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .btn:disabled { opacity: .5; cursor: default; }
  .btn.ghost { background: none; border: 1px solid var(--line); color: var(--mut); }
  .link-btn { background: none; border: 0; color: var(--accent); font-size: 12.5px; cursor: pointer; padding: 0; }
  .del { background: none; border: 1px solid var(--line); border-radius: 6px; color: var(--mut); font-size: 11.5px; padding: 3px 9px; cursor: pointer; }
  .del:hover:not(:disabled) { color: var(--red, #f87171); border-color: var(--red, #f87171); }
  .del:disabled { opacity: .4; cursor: default; }
  .acts { white-space: nowrap; }
  .acts .del { margin-left: 4px; }
  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
  th, td { text-align: left; vertical-align: top; border-top: 1px solid var(--line); padding: 6px 8px; }
  th { color: var(--mut); font-weight: 600; }
  tr.off td { opacity: .55; }
  .sum { color: var(--mut); min-width: 220px; }
  code { font-size: 12px; color: var(--mut); }
  .err { color: var(--red, #f87171); font-size: 12.5px; margin-bottom: 8px; }
  .mut { color: var(--mut); font-size: 12.5px; }
</style>
