<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { page, atmItemId, pushToast } from '../lib/stores.js'

  const STATUSES = ['idea', 'blueprint', 'shoot', 'edit', 'review', 'ready', 'scheduled', 'posted', 'monitored']
  const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6] // Monday = 0

  let items = $state([])
  let loadError = $state('')
  let settings = $state(null)
  let settingsMsg = $state('')
  let form = $state({ title: '', niche: '', reference_url: '', format: 'short', voice_mode: 'self' })
  let formMsg = $state('')
  let busy = $state(false)

  let byStatus = $derived(Object.fromEntries(STATUSES.map((s) => [s, items.filter((i) => i.status === s)])))

  function detail(r) {
    const d = r.data?.detail
    return typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join('; ') : ''
  }

  async function load() {
    const [a, b] = await Promise.all([api.atmItems(), api.atmSettings()])
    if (a.ok) { items = a.data.items; loadError = '' } else loadError = $_('atm.load_error')
    if (b.ok) settings = b.data
  }

  async function saveSettings() {
    const r = await api.atmSettingsSave({ ...settings, per_week: Number(settings.per_week), alert_ratio: Number(settings.alert_ratio) })
    settingsMsg = r.ok ? $_('atm.saved') : detail(r) || $_('atm.save_error')
  }

  function toggleDay(d) {
    const set = new Set(settings.weekdays)
    set.has(d) ? set.delete(d) : set.add(d)
    settings.weekdays = [...set].sort()
  }

  async function createItem() {
    busy = true
    formMsg = ''
    const body = { ...form, reference_url: form.reference_url.trim() || null }
    const r = await api.atmItemCreate(body)
    busy = false
    if (!r.ok) { formMsg = detail(r) || $_('atm.save_error'); return }
    form = { ...form, title: '', reference_url: '' }
    pushToast('success', $_('atm.created'), r.data.title)
    await load()
  }

  function openItem(item) {
    atmItemId.set(item.id)
    page.set('production')
  }

  onMount(load)
</script>

<div class="plan">
  <div class="page-top">
    <h1>{$_('atm.plan_title')}</h1>
    <div class="sub">{$_('atm.plan_subtitle')}</div>
  </div>

  <div class="grid2">
    <div class="panel">
      <h3>{$_('atm.new_content')}</h3>
      <div class="form-col">
        <input class="inp" placeholder={$_('atm.f_title')} maxlength="200" bind:value={form.title} />
        <input class="inp" placeholder={$_('atm.f_niche')} bind:value={form.niche} />
        <input class="inp" placeholder={$_('atm.f_reference')} bind:value={form.reference_url} />
        <div class="form-row">
          <select class="inp" bind:value={form.format}>
            <option value="short">{$_('atm.format_short')}</option>
            <option value="long">{$_('atm.format_long')}</option>
          </select>
          <select class="inp" bind:value={form.voice_mode}>
            <option value="self">{$_('atm.voice_self')}</option>
            <option value="ai">{$_('atm.voice_ai')}</option>
          </select>
          <button class="btn-primary" disabled={busy || !form.title.trim()} onclick={createItem}>{$_('atm.create')}</button>
        </div>
        {#if formMsg}<div class="err">{formMsg}</div>{/if}
      </div>
    </div>

    <div class="panel">
      <h3>{$_('atm.routine')}</h3>
      {#if settings}
        <div class="form-col">
          <div class="form-row days">
            {#each WEEKDAYS as d}
              <label class="day" class:on={settings.weekdays.includes(d)}>
                <input type="checkbox" checked={settings.weekdays.includes(d)} onchange={() => toggleDay(d)} />
                {$_('atm.wd_' + d)}
              </label>
            {/each}
          </div>
          <div class="form-row">
            <label class="lbl">{$_('atm.s_time')}<input class="inp" type="time" bind:value={settings.post_time} /></label>
            <label class="lbl">{$_('atm.s_tz')}<input class="inp" bind:value={settings.tz} /></label>
            <label class="lbl">{$_('atm.s_per_week')}<input class="inp" type="number" min="1" max="21" bind:value={settings.per_week} /></label>
          </div>
          <div class="form-row">
            <label class="lbl">{$_('atm.f_niche')}<input class="inp" bind:value={settings.niche} /></label>
            <label class="lbl">{$_('atm.s_format')}
              <select class="inp" bind:value={settings.format}>
                <option value="short">{$_('atm.format_short')}</option>
                <option value="long">{$_('atm.format_long')}</option>
              </select>
            </label>
            <label class="lbl">{$_('atm.s_alert')}<input class="inp" type="number" step="0.05" min="0.1" max="1" bind:value={settings.alert_ratio} /></label>
          </div>
          <div class="form-row">
            <button class="btn-primary" disabled={!settings.weekdays.length} onclick={saveSettings}>{$_('atm.save')}</button>
            {#if settingsMsg}<span class="mut">{settingsMsg}</span>{/if}
          </div>
        </div>
      {:else}
        <div class="mut">{$_('atm.loading')}</div>
      {/if}
    </div>
  </div>

  {#if loadError}<div class="err">{loadError}</div>{/if}
  <div class="board">
    {#each STATUSES as s}
      <div class="column">
        <div class="col-header">
          <span class="col-title">{$_('atm.status_' + s)}</span>
          <span class="col-count">{byStatus[s].length}</span>
        </div>
        <div class="col-cards">
          {#each byStatus[s] as it (it.id)}
            <div class="card" role="button" tabindex="0" onclick={() => openItem(it)} onkeydown={(e) => e.key === 'Enter' && openItem(it)}>
              <div class="card-title">{it.title}</div>
              {#if it.niche}<span class="niche-badge">{it.niche}</span>{/if}
              {#if it.scheduled_at}<div class="mut small">{it.scheduled_at.slice(0, 16).replace('T', ' ')}</div>{/if}
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  .plan { padding: 0 2px 32px; }
  .page-top { margin-bottom: 18px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 14px; margin-bottom: 20px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
  .panel h3 { margin: 0 0 10px; font-size: 14px; font-weight: 650; }
  .form-col { display: flex; flex-direction: column; gap: 8px; }
  .form-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-end; }
  .lbl { display: flex; flex-direction: column; gap: 3px; font-size: 11.5px; color: var(--mut); flex: 1; min-width: 100px; }
  .inp { flex: 1; min-width: 100px; background: var(--soft); border: 1px solid var(--line); border-radius: 7px; padding: 8px 10px; color: var(--txt); font-size: 13px; outline: none; }
  .inp:focus { border-color: var(--accent); }
  .days { align-items: center; }
  .day { display: flex; align-items: center; gap: 4px; font-size: 12.5px; padding: 4px 9px; border: 1px solid var(--line); border-radius: 16px; cursor: pointer; }
  .day.on { border-color: var(--accent); color: var(--accent); }
  .day input { display: none; }
  .btn-primary { background: var(--accent); color: #fff; border: none; border-radius: 7px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
  .btn-primary:disabled { opacity: .45; cursor: default; }
  .err { color: var(--red, #f87171); font-size: 12.5px; }
  .mut { color: var(--mut); font-size: 12.5px; }
  .small { font-size: 11px; margin-top: 4px; }
  .board { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; }
  .column { flex: 0 0 200px; display: flex; flex-direction: column; }
  .col-header { display: flex; align-items: center; justify-content: space-between; padding: 6px 4px 8px; }
  .col-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
  .col-count { font-size: 11px; background: var(--soft); border-radius: 10px; padding: 1px 7px; color: var(--mut); }
  .col-cards { display: flex; flex-direction: column; gap: 8px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 10px 12px; cursor: pointer; }
  .card:hover { border-color: var(--accent); }
  .card-title { font-size: 13px; font-weight: 600; line-height: 1.4; margin-bottom: 4px; }
  .niche-badge { display: inline-block; background: rgba(99,102,241,.15); color: var(--accent); font-size: 10.5px; border-radius: 4px; padding: 1px 6px; }
</style>
