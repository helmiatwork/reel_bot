<script>
  import { onMount } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import Pagination from '../lib/Pagination.svelte'

  let rows = $state([])
  let total = $state(0)
  let offset = $state(0)
  const limit = 25
  let loaded = $state(false)

  // filters — mirror the retrieval-engine columns
  let gender = $state('')
  let age = $state('')
  let activity = $state('')
  let minHook = $state(0)

  let genders = $derived([...new Set(rows.map((r) => r.gender))].filter((g) => g && g !== '-'))
  let ages = $derived([...new Set(rows.map((r) => r.age))].filter((a) => a && a !== '-'))
  let activities = $derived([...new Set(rows.map((r) => r.activity))].filter((a) => a && a !== '-'))

  let filtered = $derived(
    rows.filter(
      (r) =>
        (!gender || r.gender === gender) &&
        (!age || r.age === age) &&
        (!activity || r.activity === activity) &&
        (Number(r.hook) || 0) >= minHook
    )
  )

  function fmtRange(r) {
    const s = Math.floor(r.start_sec || 0)
    const e = Math.floor(r.end_sec || 0)
    const mm = (n) => String(Math.floor(n / 60)).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0')
    return `${mm(s)}–${mm(e)}`
  }

  async function load() {
    const t = await api.table('clips', limit, offset)
    if (t && t.rows) {
      rows = t.rows
      total = t.total ?? 0
    }
    loaded = true
  }

  onMount(load)

  function prev() { offset = Math.max(0, offset - limit); load() }
  function next() { offset = offset + limit; load() }
</script>

<div class="top">
  <div><h1>{$_('clips.title')}</h1><div class="sub">{$_('clips.subtitle')}</div></div>
  <div class="pill">{total || rows.length} clip</div>
</div>

<div class="filters">
  <select bind:value={gender}>
    <option value="">{$_('clips.all_genders')}</option>
    {#each genders as g}<option value={g}>{g}</option>{/each}
  </select>
  <select bind:value={age}>
    <option value="">{$_('clips.all_ages')}</option>
    {#each ages as a}<option value={a}>{a}</option>{/each}
  </select>
  <select bind:value={activity}>
    <option value="">{$_('clips.all_activities')}</option>
    {#each activities as a}<option value={a}>{a}</option>{/each}
  </select>
  <select bind:value={minHook}>
    <option value={0}>{$_('clips.hook_gte_0')}</option>
    <option value={5}>{$_('clips.hook_gte_5')}</option>
    <option value={7}>{$_('clips.hook_gte_7')}</option>
    <option value={9}>{$_('clips.hook_gte_9')}</option>
  </select>
</div>

<div class="card">
  <table>
    <thead>
      <tr>
        <th>{$_('clips.source_header')}</th><th>{$_('clips.range_header')}</th><th>{$_('clips.gender_header')}</th><th>{$_('clips.age_header')}</th>
        <th>{$_('clips.activity_header')}</th><th>{$_('clips.setting_header')}</th><th style="text-align:right">{$_('clips.hook_header')}</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as c}
        <tr>
          <td class="num">#{c.source_id}</td>
          <td class="num">{fmtRange(c)}</td>
          <td>{c.gender}</td>
          <td>{c.age}</td>
          <td>{c.activity}</td>
          <td>{c.setting || '-'}</td>
          <td class="num" style="text-align:right">{c.hook || 0}</td>
        </tr>
      {/each}
      {#if loaded && !filtered.length}
        <tr><td colspan="7" class="mut">
          {rows.length ? $_('clips.no_matching_clips') : $_('clips.empty_clips_table')}
        </td></tr>
      {/if}
    </tbody>
  </table>
</div>

<Pagination {offset} {limit} {total} onprev={prev} onnext={next} />

<div class="note">{$_('clips.info_note')}</div>
