<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { AGENT_DETAIL } from '../lib/data.js'
  import { openDrawer } from '../lib/stores.js'

  let agents = $state([])

  function enrich(a) {
    const d = AGENT_DETAIL[a.name] || {}
    return {
      name: a.name,
      role: a.role,
      modelId: a.model,
      model: d.model || ['modul'],
      cls: d.cls || ['s-mod'],
      trig: d.trig || '-',
      detail: d.detail || a.role
    }
  }

  onMount(async () => {
    const r = await api.agents()
    if (r && r.agents) agents = r.agents.map(enrich)
  })
</script>

<div class="top">
  <div><h1>{$_('agents.title')}</h1><div class="sub">{$_('agents.subtitle')}</div></div>
  <div class="pill">{agents.length} agent</div>
</div>

<div class="card">
  <div class="agrid">
    {#each agents as a}
      <div class="agent" onclick={() => openDrawer('agent', a)}>
        <div class="nm"><span class="led"></span> {a.name}</div>
        <div class="role">{a.role}</div>
        <div class="meta">{#each a.model as m, i}<span class="m-chip {a.cls[i]}">{m}</span>{/each}</div>
      </div>
    {/each}
  </div>
</div>
