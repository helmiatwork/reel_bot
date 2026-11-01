<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { page, atmItemId, pushToast } from '../lib/stores.js'

  let learnings = $state([])
  let evaluations = $state([])
  let loadError = $state('')

  async function load() {
    const r = await api.atmLearn()
    if (!r.ok) { loadError = $_('atm.load_error'); return }
    loadError = ''
    learnings = r.data.learnings
    evaluations = r.data.evaluations
  }

  async function remove(l) {
    if (!confirm($_('atm.learning_delete_confirm'))) return
    const r = await api.atmLearningDelete(l.id)
    if (r.ok) { pushToast('success', $_('atm.learning_deleted')); await load() } else pushToast('error', $_('atm.load_error'))
  }

  function open(id) {
    atmItemId.set(id)
    page.set('production')
  }

  onMount(load)
</script>

<div class="learn">
  <div class="page-top">
    <h1>{$_('atm.learn_title')}</h1>
    <div class="sub">{$_('atm.learn_subtitle')}</div>
  </div>
  {#if loadError}<div class="err">{loadError}</div>{/if}

  <div class="grid2">
    <div class="panel">
      <h3>{$_('atm.learnings')}</h3>
      {#if !learnings.length}<div class="mut">{$_('atm.no_learnings')}</div>{/if}
      {#each learnings as l (l.id)}
        <div class="row">
          <div>
            <span class="niche-badge">{l.kind}</span>
            <span class="mut small">{l.niche} · {$_('atm.learning_hits', { values: { n: l.hits } })}</span>
            <div class="content">{l.content}</div>
          </div>
          <button class="del" onclick={() => remove(l)}>{$_('atm.delete')}</button>
        </div>
      {/each}
    </div>

    <div class="panel">
      <h3>{$_('atm.eval_history')}</h3>
      {#if !evaluations.length}<div class="mut">{$_('atm.no_evals')}</div>{/if}
      {#each evaluations as e (e.id)}
        <button class="row link" onclick={() => open(e.item_id)}>
          <div>
            <div class="content">{e.title}</div>
            <span class="niche-badge">{$_('atm.eval_kind_' + e.kind)}</span>
            <span class="mut small">{$_('atm.eval_round', { values: { n: e.round } })}{e.status === 'error' ? ' · ' + $_('atm.eval_error') : ''}</span>
            {#if e.summary}<div class="mut small">{e.summary}</div>{/if}
          </div>
        </button>
      {/each}
    </div>
  </div>
</div>

<style>
  .learn { padding: 0 2px 32px; }
  .page-top { margin-bottom: 18px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 14px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
  .panel h3 { margin: 0 0 10px; font-size: 14px; font-weight: 650; }
  .row { display: flex; justify-content: space-between; gap: 10px; width: 100%; text-align: left; background: none; border: 0; border-top: 1px solid var(--line); padding: 8px 2px; color: var(--txt); font-size: 13px; }
  .link { cursor: pointer; }
  .link:hover .content { color: var(--accent); }
  .content { font-size: 13px; margin-top: 3px; line-height: 1.4; }
  .del { background: none; border: 1px solid var(--line); border-radius: 6px; color: var(--mut); font-size: 11.5px; padding: 3px 9px; cursor: pointer; align-self: flex-start; }
  .del:hover { color: var(--red, #f87171); border-color: var(--red, #f87171); }
  .niche-badge { background: rgba(99,102,241,.15); color: var(--accent); font-size: 10.5px; border-radius: 4px; padding: 1px 6px; }
  .err { color: var(--red, #f87171); font-size: 12.5px; }
  .mut { color: var(--mut); font-size: 12.5px; }
  .small { font-size: 11px; }
</style>
