<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import Pagination from '../lib/Pagination.svelte'

  let rows = $state([])
  let total = $state(0)
  let offset = $state(0)
  const limit = 25
  let loading = $state(true)

  const PLATFORM_ICON = {
    youtube: 'i-yt', tiktok: 'i-tt', instagram: 'i-ig', xiaohongshu: 'i-xhs'
  }

  function fmtFollowers(n) {
    if (n == null || n === '') return '—'
    const num = Number(n)
    if (isNaN(num)) return '—'
    return num.toLocaleString('id-ID')
  }

  function fmtDate(s) {
    if (!s) return '—'
    const d = new Date(s)
    if (isNaN(d.getTime())) return '—'
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  function fmtPlatform(p) {
    if (!p) return { icon: null, label: '—' }
    const labels = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram', xiaohongshu: 'Xiaohongshu' }
    return { icon: PLATFORM_ICON[p], label: labels[p] || p }
  }

  async function load() {
    loading = true
    const data = await api.getCreators(limit, offset)
    if (data && data.creators) {
      rows = data.creators
      total = data.total ?? rows.length
    }
    loading = false
  }

  onMount(load)

  function prev() { offset = Math.max(0, offset - limit); load() }
  function next() { offset = offset + limit; load() }
</script>

<div class="top">
  <div><h1>Creators</h1><div class="sub">Daftar creator yang dipantau</div></div>
  <div class="pill">{total || rows.length} creator</div>
</div>

<div class="card">
  <table>
    <thead>
      <tr>
        <th>Channel</th>
        <th>Creator Name</th>
        <th class="num" style="text-align:right">Total Followers</th>
        <th>Platform</th>
        <th>Gender</th>
        <th>Created</th>
        <th>Last Updated</th>
      </tr>
    </thead>
    <tbody>
      {#each rows as r}
        {@const plat = fmtPlatform(r.platform)}
        <tr>
          <td>{r.channel || r.channel_id || '—'}</td>
          <td>{r.creator_name || '—'}</td>
          <td class="num" style="text-align:right">{fmtFollowers(r.total_followers)}</td>
          <td>
            {#if plat.icon}
              <div style="display:flex;align-items:center;gap:0.25rem">
                <svg class="plat-ico {r.platform}" style="width:14px;height:14px"><use href="#{plat.icon}"/></svg>
                <span>{plat.label}</span>
              </div>
            {:else}
              {plat.label}
            {/if}
          </td>
          <td>{r.gender || '—'}</td>
          <td>{fmtDate(r.created_at)}</td>
          <td>{fmtDate(r.last_updated)}</td>
        </tr>
      {/each}
      {#if !loading && !rows.length}
        <tr><td colspan="7" class="mut">Belum ada creator.</td></tr>
      {/if}
      {#if loading}
        <tr><td colspan="7" class="mut">Memuat…</td></tr>
      {/if}
    </tbody>
  </table>
</div>

<Pagination {offset} {limit} {total} onprev={prev} onnext={next} />
