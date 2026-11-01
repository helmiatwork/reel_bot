<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { page, atmItemId } from '../lib/stores.js'

  const CHECKPOINTS = [1, 6, 24, 48, 168]

  let items = $state([])
  let snaps = $state({}) // item id -> {checkpoint_h -> snapshot}
  let loadError = $state('')

  async function load() {
    const [a, b] = await Promise.all([api.atmItems('posted'), api.atmItems('monitored')])
    if (!a.ok || !b.ok) { loadError = $_('atm.load_error'); return }
    loadError = ''
    items = [...a.data.items, ...b.data.items]
    const rs = await Promise.all(items.map((i) => api.atmMonitor(i.id)))
    snaps = Object.fromEntries(items.map((it, k) => [it.id, Object.fromEntries((rs[k].ok ? rs[k].data.snapshots : []).map((s) => [s.checkpoint_h, s]))]))
  }

  function open(id) {
    atmItemId.set(id)
    page.set('production')
  }

  const label = (h) => (h >= 24 ? $_('atm.cp_days', { values: { d: h / 24 } }) : $_('atm.cp_hours', { values: { h } }))

  onMount(load)
</script>

<div class="monitor">
  <div class="page-top">
    <h1>{$_('atm.monitor_title')}</h1>
    <div class="sub">{$_('atm.monitor_subtitle')}</div>
  </div>
  {#if loadError}<div class="err">{loadError}</div>{/if}
  {#if !items.length && !loadError}<div class="mut">{$_('atm.no_posted')}</div>{/if}

  {#each items as it (it.id)}
    <div class="panel">
      <div class="head">
        <button class="title" onclick={() => open(it.id)}>{it.title}</button>
        <span class="niche-badge">{$_('atm.status_' + it.status)}</span>
        {#if it.published_url}<a class="mut small" href={it.published_url} target="_blank" rel="noopener noreferrer">{it.published_url}</a>{/if}
      </div>
      <table>
        <thead>
          <tr><th>{$_('atm.cp_age')}</th><th>{$_('atm.views')}</th><th>{$_('atm.likes')}</th><th>{$_('atm.comments')}</th><th></th></tr>
        </thead>
        <tbody>
          {#each CHECKPOINTS as h}
            {@const s = snaps[it.id]?.[h]}
            <tr>
              <td>{label(h)}</td>
              {#if s}
                <td>{s.views ?? '-'}</td><td>{s.likes ?? '-'}</td><td>{s.comments ?? '-'}</td>
                <td>{#if s.alerted}<span class="badge">{$_('atm.alert_badge')}</span>{/if}</td>
              {:else}
                <td class="mut" colspan="4">{$_('atm.no_snapshot')}</td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/each}
</div>

<style>
  .monitor { padding: 0 2px 32px; }
  .page-top { margin-bottom: 18px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
  .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
  .title { background: none; border: 0; padding: 0; color: var(--txt); font-size: 14px; font-weight: 650; cursor: pointer; }
  .title:hover { color: var(--accent); }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th { text-align: left; color: var(--mut); font-weight: 500; padding: 4px 8px 4px 0; }
  td { padding: 5px 8px 5px 0; border-top: 1px solid var(--line); }
  .badge { background: rgba(248,113,113,.15); color: var(--red, #f87171); font-size: 11px; border-radius: 4px; padding: 1px 6px; }
  .niche-badge { background: rgba(99,102,241,.15); color: var(--accent); font-size: 10.5px; border-radius: 4px; padding: 1px 6px; }
  .err { color: var(--red, #f87171); font-size: 12.5px; }
  .mut { color: var(--mut); font-size: 12.5px; }
  .small { font-size: 11px; word-break: break-all; }
</style>
