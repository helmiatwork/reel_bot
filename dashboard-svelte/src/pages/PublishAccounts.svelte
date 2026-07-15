<script>
  import { api } from '../lib/api.js'

  const PLATFORMS = [
    { id: 'youtube',      label: 'YouTube',              icon: 'i-yt' },
    { id: 'tiktok',       label: 'TikTok',               icon: 'i-tt' },
    { id: 'instagram',    label: 'Instagram',            icon: 'i-ig' },
    { id: 'xiaohongshu',  label: 'Xiaohongshu (小红书)',  icon: 'i-xhs' },
  ]

  let accounts = $state([])
  let loading  = $state(true)
  let connecting = $state({})  // Track connecting state per account id
  let ui = $state(Object.fromEntries(
    PLATFORMS.map(p => [p.id, { adding: false, handle: '', label: '', saving: false, msg: null }])
  ))

  function accountsForPlatform(pid) {
    return accounts.filter(a => a.platform === pid)
  }

  async function load() {
    loading = true
    const rows = await api.accounts(null, 'publish')
    loading = false
    if (rows) accounts = rows
  }

  $effect(() => { load() })

  async function addAccount(p) {
    const u = ui[p.id]
    const handle = u.handle.trim()
    if (!handle) return
    u.saving = true
    u.msg = null
    const r = await api.accountCreate({ platform: p.id, handle, label: u.label.trim() || handle, role: 'publish' })
    u.saving = false
    if (!r || r.detail) {
      u.msg = { ok: false, text: r?.detail || 'Request failed' }
    } else {
      u.adding = false
      u.handle = ''
      u.label  = ''
      u.msg    = null
      await load()
    }
  }

  async function toggleActive(acct) {
    await api.accountUpdate(acct.id, { active: !acct.active })
    await load()
  }

  async function deleteAccount(acct) {
    if (!confirm(`Delete account @${acct.handle}?`)) return
    await api.accountDelete(acct.id)
    await load()
  }

  async function connectYoutube(acct) {
    connecting[acct.id] = true
    const r = await api.accountConnectYoutube(acct.id)
    connecting[acct.id] = false
    if (r && r.auth_url) {
      // Web OAuth flow: redirect user to Google auth, will return to / with yt_connect=success/error
      window.location.href = r.auth_url
    } else if (r && r.detail) {
      alert(`Connection failed: ${r.detail}`)
    } else {
      alert('Connection failed. Check console and try again.')
    }
  }
</script>

<div class="ac">
  <div class="top">
    <h1>Publish Accounts</h1>
    <div class="sub">Akun earning — untuk scheduling & performance tracking. Cookie tidak pernah dipakai untuk download.</div>
  </div>

  <div class="help">
    Ini adalah akun-akun penghasil uangmu. Tambahkan di sini agar <strong>Jadwal Post</strong> bisa
    memilih channel yang tepat per platform dan <strong>Performance</strong> bisa melacak views &amp; revenue-nya.
    Cookie mereka <em>tidak pernah</em> dipakai untuk scraping — itu tugas Scrape Accounts.
  </div>

  {#if loading}
    <div class="state-msg">Loading…</div>
  {:else}
    {#each PLATFORMS as p}
      {@const list = accountsForPlatform(p.id)}
      {@const u = ui[p.id]}
      <section class="platform">
        <div class="plat-head">
          <svg class="plat-ico"><use href="#{p.icon}"/></svg>
          <span class="plat-label">{p.label}</span>
          <button class="btn-add-toggle" onclick={() => { u.adding = !u.adding; u.msg = null }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M12 5v14M5 12h14"/></svg>
            Tambah akun
          </button>
        </div>

        {#if u.adding}
          <div class="add-form">
            <input
              class="inp"
              placeholder="Handle / username"
              bind:value={u.handle}
              aria-label="Handle"
            />
            <input
              class="inp"
              placeholder="Label (opsional)"
              bind:value={u.label}
              aria-label="Label"
            />
            <div class="add-actions">
              <button class="btn-save" disabled={u.saving || !u.handle.trim()} onclick={() => addAccount(p)}>
                {u.saving ? 'Menyimpan…' : 'Simpan'}
              </button>
              <button class="btn-cancel" onclick={() => { u.adding = false; u.handle = ''; u.label = ''; u.msg = null }}>Batal</button>
            </div>
            {#if u.msg}
              <div class="msg" class:err={!u.msg.ok}>{u.msg.text}</div>
            {/if}
          </div>
        {/if}

        {#if list.length === 0}
          <div class="empty">Belum ada akun earning untuk platform ini.</div>
        {:else}
          <div class="acct-list">
            {#each list as acct}
              <div class="acct-card" class:inactive={!acct.active}>
                <div class="acct-head">
                  <div class="acct-info">
                    <span class="acct-handle">@{acct.handle}</span>
                    {#if acct.label && acct.label !== acct.handle}
                      <span class="acct-label">{acct.label}</span>
                    {/if}
                  </div>
                  <div class="acct-badges">
                    <span class="badge earn">earning</span>
                    {#if p.id === 'youtube'}
                      {#if acct.connected}
                        <span class="badge connected" title="OAuth token saved">connected</span>
                      {:else}
                        <button
                          class="badge connect"
                          disabled={connecting[acct.id]}
                          title="Connect YouTube OAuth"
                          onclick={() => connectYoutube(acct)}
                        >
                          {connecting[acct.id] ? 'Connecting…' : 'Connect'}
                        </button>
                      {/if}
                    {/if}
                    <button
                      class="badge toggle"
                      class:active={acct.active}
                      title={acct.active ? 'Aktif — klik nonaktifkan' : 'Nonaktif — klik aktifkan'}
                      onclick={() => toggleActive(acct)}
                    >{acct.active ? 'aktif' : 'nonaktif'}</button>
                    <button class="btn-icon del" title="Hapus akun" onclick={() => deleteAccount(acct)}>
                      <svg class="ic"><use href="#i-trash"/></svg>
                    </button>
                  </div>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/each}
  {/if}
</div>

<style>
  .ac { padding-bottom: 60px; }

  .top { margin-bottom: 10px; }
  h1   { margin: 0 0 4px; }
  .sub { color: var(--mut); font-size: 13.5px; }

  .help {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 13px;
    color: var(--mut);
    margin-bottom: 24px;
    line-height: 1.55;
  }

  .state-msg { text-align: center; padding: 48px 0; font-size: 13.5px; color: var(--mut); }

  /* ── platform section ───────────────────────────────────────────────────── */
  .platform {
    margin-bottom: 32px;
  }

  .plat-head {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }

  .plat-ico {
    width: 22px;
    height: 22px;
    flex-shrink: 0;
  }

  .plat-label {
    font-size: 15px;
    font-weight: 650;
    flex: 1;
  }

  .btn-add-toggle {
    display: flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 5px 12px;
    font-size: 12.5px;
    color: var(--txt);
    cursor: pointer;
    font-family: inherit;
  }
  .btn-add-toggle:hover { border-color: var(--accent); color: var(--accent); }

  /* ── add form ───────────────────────────────────────────────────────────── */
  .add-form {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .inp {
    background: var(--panel2, #0e1420);
    border: 1px solid var(--line);
    border-radius: 8px;
    color: var(--txt);
    font-size: 13.5px;
    padding: 8px 11px;
    outline: none;
    font-family: inherit;
    width: 100%;
    box-sizing: border-box;
  }
  .inp:focus { border-color: var(--accent); }

  .add-actions {
    display: flex;
    gap: 8px;
  }

  /* ── empty state ────────────────────────────────────────────────────────── */
  .empty {
    font-size: 13px;
    color: var(--mut);
    padding: 10px 2px;
  }

  /* ── account cards ──────────────────────────────────────────────────────── */
  .acct-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .acct-card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .acct-card.inactive { opacity: 0.55; }

  .acct-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }

  .acct-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .acct-handle {
    font-size: 14.5px;
    font-weight: 650;
  }

  .acct-label {
    font-size: 12px;
    color: var(--mut);
  }

  .acct-badges {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  /* ── badges ─────────────────────────────────────────────────────────────── */
  .badge {
    font-size: 11.5px;
    padding: 3px 9px;
    border-radius: 999px;
    border: 1px solid transparent;
  }
  .badge.earn {
    background: rgba(99,102,241,.1);
    border-color: rgba(99,102,241,.3);
    color: #818cf8;
  }
  .badge.connected {
    background: rgba(34,197,94,.1);
    border-color: rgba(34,197,94,.3);
    color: #22c55e;
  }
  .badge.connect {
    cursor: pointer;
    font-family: inherit;
    background: rgba(99,102,241,.1);
    border-color: rgba(99,102,241,.3);
    color: #818cf8;
  }
  .badge.connect:hover:not(:disabled) {
    background: rgba(99,102,241,.2);
    border-color: rgba(99,102,241,.5);
  }
  .badge.connect:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .badge.toggle {
    cursor: pointer;
    font-family: inherit;
    background: var(--panel2, #0e1420);
    border-color: var(--line);
    color: var(--mut);
  }
  .badge.toggle.active {
    background: rgba(99,102,241,.1);
    border-color: rgba(99,102,241,.35);
    color: #818cf8;
  }

  /* ── icon button ────────────────────────────────────────────────────────── */
  .btn-icon {
    background: none;
    border: none;
    cursor: pointer;
    padding: 3px;
    color: var(--mut);
    display: flex;
    align-items: center;
  }
  .btn-icon.del:hover { color: #f87171; }
  .ic { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

  /* ── feedback message ───────────────────────────────────────────────────── */
  .msg {
    font-size: 12.5px;
    padding: 7px 11px;
    border-radius: 8px;
    background: rgba(34,197,94,.08);
    border: 1px solid rgba(34,197,94,.2);
    color: var(--green, #22c55e);
  }
  .msg.err {
    background: rgba(239,68,68,.08);
    border-color: rgba(239,68,68,.25);
    color: #f87171;
  }

  /* ── action buttons ─────────────────────────────────────────────────────── */
  .btn-save {
    background: var(--accent);
    color: #0b0f17;
    border: none;
    border-radius: 9px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 650;
    cursor: pointer;
    font-family: inherit;
  }
  .btn-save:disabled { opacity: 0.45; cursor: default; }

  .btn-cancel {
    background: none;
    border: 1px solid var(--line);
    border-radius: 9px;
    padding: 8px 14px;
    font-size: 13px;
    color: var(--mut);
    cursor: pointer;
    font-family: inherit;
  }

  @media (max-width: 600px) {
    .acct-head { flex-direction: column; align-items: flex-start; }
  }
</style>
