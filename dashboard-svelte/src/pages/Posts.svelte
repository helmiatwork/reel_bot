<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { POSTS } from '../lib/data.js'

  let rows = $state([])
  let mock = $state(false)

  onMount(async () => {
    const t = await api.table('posts')
    if (t && t.rows && t.rows.length) {
      rows = t.rows.map((r) => ({
        konten: r.url && r.url !== '-' ? r.url : `post ${r.id}`,
        platform: r.platform,
        jadwal: r.scheduled_at || r.posted_at || '—',
        status: r.status
      }))
    } else {
      rows = POSTS.map((p) => ({ konten: p.konten, platform: p.platform, jadwal: p.jadwal, status: p.status }))
      mock = true
    }
  })

  // group by day label (string before time)
  function dayOf(j) {
    if (!j || j === '—') return 'Belum dijadwalkan'
    return String(j).replace(/\s*\d{1,2}:\d{2}.*$/, '').trim() || j
  }
  function timeOf(j) {
    const m = String(j).match(/\d{1,2}:\d{2}/)
    return m ? m[0] : ''
  }
  let groups = $derived(
    [...new Set(rows.map((r) => dayOf(r.jadwal)))].map((day) => ({
      day,
      items: rows.filter((r) => dayOf(r.jadwal) === day)
    }))
  )
  const PRIME = ['12:00', '19:00']
  const chipClass = (s) => (s === 'posted' ? 'c-used' : s === 'scheduled' ? 'c-analyzed' : '')
</script>

<div class="top">
  <div><h1>Posts</h1><div class="sub">Kalender jadwal — slot prime-time disorot</div></div>
  <div class="pill">prime time 12:00 / 19:00 WIB</div>
</div>

<div class="kanban" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr))">
  {#each groups as g}
    <div class="col" style="min-height:auto">
      <div class="h">{g.day} <span>{g.items.length}</span></div>
      {#each g.items as p}
        <div class="ticket">
          {p.konten}
          <div class="m" style="display:flex;justify-content:space-between;align-items:center">
            <span>{p.platform}</span>
            {#if timeOf(p.jadwal)}
              <span class="chip {PRIME.includes(timeOf(p.jadwal)) ? 'c-used' : 'c-analyzed'}">{timeOf(p.jadwal)}{PRIME.includes(timeOf(p.jadwal)) ? ' ★' : ''}</span>
            {/if}
          </div>
          <div class="bar"><i style="width:{p.status === 'posted' ? 100 : p.status === 'scheduled' ? 60 : 20}%"></i></div>
        </div>
      {/each}
    </div>
  {/each}
</div>

{#if mock}<div class="note">⚠️ Tabel posts kosong — kalender menampilkan contoh mock. Begitu ada post terjadwal di DB, kalender ngisi otomatis.</div>{/if}
