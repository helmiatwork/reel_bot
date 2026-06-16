<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'

  let rows = $state([])
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

  onMount(async () => {
    const t = await api.table('clips')
    if (t && t.rows) rows = t.rows
    loaded = true
  })
</script>

<div class="top">
  <div><h1>Clips</h1><div class="sub">Engine retrieval — filter atribut → timecode buat dirakit</div></div>
  <div class="pill">{rows.length} clip</div>
</div>

<div class="filters">
  <select bind:value={gender}>
    <option value="">Semua gender</option>
    {#each genders as g}<option value={g}>{g}</option>{/each}
  </select>
  <select bind:value={age}>
    <option value="">Semua umur</option>
    {#each ages as a}<option value={a}>{a}</option>{/each}
  </select>
  <select bind:value={activity}>
    <option value="">Semua aktivitas</option>
    {#each activities as a}<option value={a}>{a}</option>{/each}
  </select>
  <select bind:value={minHook}>
    <option value={0}>Hook ≥ 0</option>
    <option value={5}>Hook ≥ 5</option>
    <option value={7}>Hook ≥ 7</option>
    <option value={9}>Hook ≥ 9</option>
  </select>
</div>

<div class="card">
  <table>
    <thead>
      <tr>
        <th>Source</th><th>Rentang</th><th>Gender</th><th>Umur</th>
        <th>Aktivitas</th><th>Setting</th><th style="text-align:right">Hook</th>
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
          {rows.length ? 'Gak ada clip cocok filter.' : 'Tabel clips masih kosong — engine retrieval belum diisi. UI siap begitu clip masuk.'}
        </td></tr>
      {/if}
    </tbody>
  </table>
</div>

<div class="note">ℹ️ Atribut netral aja (gender-presentation, age-bracket, aktivitas, hair, setting, hook score) — sesuai desain engine. Begitu pipeline analyze ngisi <code>clips</code>, baris muncul + filter live.</div>
