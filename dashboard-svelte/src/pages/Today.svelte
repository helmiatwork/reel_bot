<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { page, atmItemId, pushToast } from '../lib/stores.js'

  const ACTIONS = ['shoot', 'edit', 'evaluate', 'upload']

  let tasks = $state([])
  let alerts = $state([])
  let upcoming = $state([])
  let loadError = $state('')
  let busy = $state(false)

  let byAction = $derived(Object.fromEntries(ACTIONS.map((a) => [a, tasks.filter((t) => t.action === a)])))

  async function load() {
    const r = await api.atmToday()
    if (!r.ok) { loadError = $_('atm.load_error'); return }
    loadError = ''
    tasks = r.data.tasks
    alerts = r.data.alerts
    upcoming = r.data.upcoming
  }

  async function autofill() {
    busy = true
    const r = await api.atmAutofill()
    busy = false
    if (!r.ok) { pushToast('error', $_('atm.autofill_error')); return }
    const n = r.data.assigned.length
    pushToast('success', n ? $_('atm.autofill_done', { values: { n } }) : $_('atm.autofill_none'))
    await load()
  }

  function open(id) {
    atmItemId.set(id)
    page.set('production')
  }

  const when = (iso) => (iso ? iso.slice(0, 16).replace('T', ' ') : '')

  onMount(load)
</script>

<div class="today">
  <div class="page-top">
    <div>
      <h1>{$_('atm.today_title')}</h1>
      <div class="sub">{$_('atm.today_subtitle')}</div>
    </div>
    <button class="btn-primary" disabled={busy} onclick={autofill}>{$_('atm.autofill')}</button>
  </div>
  {#if loadError}<div class="err">{loadError}</div>{/if}

  <div class="grid2">
    <div class="panel">
      <h3>{$_('atm.tasks')}</h3>
      {#if !tasks.length}<div class="mut">{$_('atm.no_tasks')}</div>{/if}
      {#each ACTIONS as a}
        {#if byAction[a].length}
          <div class="group">{$_('atm.act_' + a)} <span class="count">{byAction[a].length}</span></div>
          {#each byAction[a] as t (t.item_id)}
            <button class="row" onclick={() => open(t.item_id)}>
              <span>{t.title}</span>
              <span class="mut small">{when(t.scheduled_at)}</span>
            </button>
          {/each}
        {/if}
      {/each}
    </div>

    <div class="panel">
      <h3>{$_('atm.alerts')}</h3>
      {#if !alerts.length}<div class="mut">{$_('atm.no_alerts')}</div>{/if}
      {#each alerts as al}
        <button class="row" onclick={() => open(al.content_item_id)}>
          <span>{al.title}</span>
          <span class="badge">{$_('atm.alert_line', { values: { h: al.checkpoint_h, views: al.views } })}</span>
        </button>
      {/each}
    </div>
  </div>

  <div class="panel">
    <h3>{$_('atm.upcoming')}</h3>
    {#if !upcoming.length}<div class="mut">{$_('atm.no_upcoming')}</div>{/if}
    {#each upcoming as it (it.id)}
      <button class="row" onclick={() => open(it.id)}>
        <span>{it.title}</span>
        <span class="mut small">{when(it.scheduled_at)} · {$_('atm.status_' + it.status)}</span>
      </button>
    {/each}
  </div>
</div>

<style>
  .today { padding: 0 2px 32px; }
  .page-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 18px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 14px; margin-bottom: 14px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
  .panel h3 { margin: 0 0 10px; font-size: 14px; font-weight: 650; }
  .group { font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; margin: 10px 0 4px; }
  .count { background: var(--soft); border-radius: 10px; padding: 1px 7px; color: var(--mut); font-weight: 500; }
  .row { display: flex; justify-content: space-between; gap: 10px; width: 100%; text-align: left; background: none; border: 0; border-top: 1px solid var(--line); padding: 8px 2px; color: var(--txt); font-size: 13px; cursor: pointer; }
  .row:hover { color: var(--accent); }
  .badge { background: rgba(248,113,113,.15); color: var(--red, #f87171); font-size: 11px; border-radius: 4px; padding: 1px 6px; white-space: nowrap; align-self: center; }
  .btn-primary { background: var(--accent); color: #fff; border: none; border-radius: 7px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
  .btn-primary:disabled { opacity: .45; cursor: default; }
  .err { color: var(--red, #f87171); font-size: 12.5px; margin-bottom: 8px; }
  .mut { color: var(--mut); font-size: 12.5px; }
  .small { font-size: 11px; }
</style>
