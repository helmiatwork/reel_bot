<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'

  // Map, not object: a lookup on an unknown id must not hit Object.prototype.
  const MODEL_LABELS = new Map([
    ['claude-sonnet-5-5', 'Sonnet 5.5'],
    ['claude-haiku-5-5', 'Haiku 5.5'],
    ['claude-opus-5-5', 'Opus 5.5']
  ])

  let jobs = $state([])
  let loadError = $state('')

  async function load() {
    const r = await api.atmModels()
    if (!r.ok) { loadError = $_('atm.load_error'); return }
    loadError = ''
    jobs = r.data?.jobs ?? []
  }

  onMount(load)
</script>

<div class="models">
  <div class="page-top">
    <h1>{$_('atm.models_title')}</h1>
    <div class="sub">{$_('atm.models_subtitle')}</div>
  </div>
  {#if loadError}<div class="err">{loadError}</div>{/if}

  <div class="tbl-wrap">
    <table class="tbl">
      <thead>
        <tr>
          <th>{$_('atm.models_col_job')}</th>
          <th>{$_('atm.models_col_model')}</th>
          <th>{$_('atm.models_col_effort')}</th>
          <th>{$_('atm.models_col_reason')}</th>
        </tr>
      </thead>
      <tbody>
        {#each jobs as j}
          <tr>
            <td class="job">{j.job}</td>
            <td class="model">{MODEL_LABELS.get(j.model) ?? j.model}</td>
            <td><span class="effort">{j.effort}</span></td>
            <td class="reason">{j.reason}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .models { padding: 0 2px 32px; }
  .page-top { margin-bottom: 18px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }
  .err { color: var(--red, #f87171); font-size: 12.5px; }

  /* Scroll stays inside the table box; the page itself never overflows. */
  .tbl-wrap { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; overflow-x: auto; }
  .tbl { width: 100%; min-width: 560px; border-collapse: collapse; font-size: 13.5px; }
  .tbl thead th { text-align: left; padding: 11px 16px; font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--mut); border-bottom: 1px solid var(--line); white-space: nowrap; }
  .tbl tbody tr { border-bottom: 1px solid var(--line); }
  .tbl tbody tr:last-child { border-bottom: none; }
  .tbl tbody tr:hover { background: var(--soft); }
  .tbl td { padding: 12px 16px; vertical-align: top; overflow-wrap: anywhere; }
  .job { font-weight: 600; }
  .model { white-space: nowrap; }
  .reason { color: var(--mut); line-height: 1.45; min-width: 220px; }
  .effort { display: inline-block; background: rgba(99,102,241,.15); color: var(--accent); font-size: 11.5px; font-weight: 600; border-radius: 6px; padding: 2px 8px; white-space: nowrap; }
</style>
