<script>
  import { fade, scale } from 'svelte/transition'
  import { cubicOut } from 'svelte/easing'
  import { api } from '../lib/api.js'

  const PLATFORMS = [
    { id: 'youtube',     label: 'YouTube',             icon: 'i-yt' },
    { id: 'tiktok',     label: 'TikTok',              icon: 'i-tt' },
    { id: 'instagram',  label: 'Instagram',           icon: 'i-ig' },
    { id: 'xiaohongshu',label: 'Xiaohongshu (小红书)', icon: 'i-xhs' },
  ]

  const PLAT = Object.fromEntries(PLATFORMS.map(p => [p.id, p]))

  let accounts = $state([])
  let loading  = $state(true)

  // modal state
  let modal = $state(null)  // null | { mode:'add'|'edit', acct?:{} }
  let mPlatform = $state('youtube')
  let mHandle   = $state('')
  let mLabel    = $state('')
  let mCookies  = $state('')
  let mSaving   = $state(false)
  let mMsg      = $state(null) // { ok:bool, text:string }

  let panelEl = $state(null)
  let triggerEl = $state(null)

  function fmtLastUsed(iso) {
    if (!iso) return null
    const d = new Date(iso)
    const diffDays = Math.floor((Date.now() - d) / 86400000)
    if (diffDays === 0) return 'hari ini'
    if (diffDays === 1) return 'kemarin'
    if (diffDays < 7) return `${diffDays} hari lalu`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} minggu lalu`
    return `${Math.floor(diffDays / 30)} bulan lalu`
  }

  async function load() {
    loading = true
    const rows = await api.accounts(null, 'scrape')
    loading = false
    if (rows) accounts = rows
  }

  $effect(() => { load() })

  // ── modal open/close ─────────────────────────────────────────────────────────

  function openAdd() {
    triggerEl = document.activeElement
    mPlatform = 'youtube'
    mHandle   = ''
    mLabel    = ''
    mCookies  = ''
    mMsg      = null
    mSaving   = false
    modal     = { mode: 'add' }
  }

  function openEdit(acct) {
    triggerEl = document.activeElement
    mPlatform = acct.platform
    mHandle   = acct.handle
    mLabel    = acct.label && acct.label !== acct.handle ? acct.label : ''
    mCookies  = ''
    mMsg      = null
    mSaving   = false
    modal     = { mode: 'edit', acct }
  }

  function closeModal() {
    modal = null
    setTimeout(() => triggerEl?.focus(), 50)
  }

  function onBackdropClick(e) {
    if (e.target === e.currentTarget) closeModal()
  }

  function onKey(e) {
    if (!modal) return
    if (e.key === 'Escape') closeModal()
  }

  function trapFocus(e) {
    if (!panelEl || e.key !== 'Tab') return
    const focusable = panelEl.querySelectorAll(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
    const first = focusable[0]
    const last  = focusable[focusable.length - 1]
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last?.focus() }
    } else {
      if (document.activeElement === last)  { e.preventDefault(); first?.focus() }
    }
  }

  $effect(() => {
    if (modal) {
      setTimeout(() => {
        const el = panelEl?.querySelector('select, input, textarea')
        el?.focus()
      }, 30)
    }
  })

  // ── save ─────────────────────────────────────────────────────────────────────

  async function save() {
    mMsg    = null
    mSaving = true
    const handle = mHandle.trim()
    const label  = mLabel.trim() || handle
    const cookies = mCookies.trim()

    if (modal.mode === 'add') {
      const r = await api.accountCreate({ platform: mPlatform, handle, label, role: 'scrape' })
      if (!r || r.detail) {
        mMsg    = { ok: false, text: r?.detail || 'Gagal membuat akun' }
        mSaving = false
        return
      }
      // account created — now cookies if provided
      if (cookies) {
        const cr = await api.accountSaveCookies(r.id, cookies)
        if (!cr || cr.detail) {
          // account created but cookie failed — surface it, don't delete account
          mMsg    = { ok: false, text: `Akun dibuat, tapi cookies gagal: ${cr?.detail || 'error'}` }
          mSaving = false
          await load()
          return
        }
      }
      mSaving = false
      closeModal()
      await load()

    } else {
      // edit
      const acct = modal.acct
      const pr = await api.accountUpdate(acct.id, { handle, label })
      if (!pr || pr.detail) {
        mMsg    = { ok: false, text: pr?.detail || 'Gagal menyimpan' }
        mSaving = false
        return
      }
      if (cookies) {
        const cr = await api.accountSaveCookies(acct.id, cookies)
        if (!cr || cr.detail) {
          mMsg    = { ok: false, text: `Profil disimpan, cookies gagal: ${cr?.detail || 'error'}` }
          mSaving = false
          await load()
          return
        }
      }
      mSaving = false
      closeModal()
      await load()
    }
  }

  // ── delete account ────────────────────────────────────────────────────────────

  async function deleteAccount(acct) {
    if (!confirm(`Hapus akun @${acct.handle}?`)) return
    await api.accountDelete(acct.id)
    await load()
  }
</script>

<svelte:window onkeydown={onKey}/>

<div class="ac">
  <div class="top">
    <div class="top-row">
      <div>
        <h1>Scrape Accounts</h1>
        <div class="sub">Burner accounts untuk download/scraping. Download dirotasi otomatis antar akun aktif.</div>
      </div>
      <button class="btn-primary" onclick={openAdd}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M12 5v14M5 12h14"/></svg>
        Tambah akun
      </button>
    </div>
  </div>

  <div class="help">
    Akun-akun ini dirotasi saat download video. Export cookies dengan ekstensi
    "Get cookies.txt LOCALLY" saat login, lalu tempel per akun dalam format Netscape tab-separated.
    Akun earning ada di menu <strong>Publish Accounts</strong> — terpisah dan tidak dipakai untuk download.
  </div>

  {#if loading}
    <div class="state-msg">Loading…</div>
  {:else if accounts.length === 0}
    <div class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="width:32px;height:32px;color:var(--mut)"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
      </div>
      <div class="empty-txt">Belum ada akun scraping</div>
      <button class="btn-primary" onclick={openAdd}>+ Tambah akun pertama</button>
    </div>
  {:else}
    <div class="tbl-wrap">
      <table class="tbl">
        <thead>
          <tr>
            <th>Channel</th>
            <th>Platform</th>
            <th>Status</th>
            <th>Terakhir dipakai</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each accounts as acct}
            <tr class:row-inactive={!acct.active}>
              <td>
                <div class="chan-cell">
                  <span class="chan-handle">@{acct.handle}</span>
                  {#if acct.label && acct.label !== acct.handle}
                    <span class="chan-label">{acct.label}</span>
                  {/if}
                </div>
              </td>
              <td>
                <div class="plat-cell">
                  <svg class="plat-ico"><use href="#{PLAT[acct.platform]?.icon ?? 'i-yt'}"/></svg>
                  <span class="plat-name">{PLAT[acct.platform]?.label ?? acct.platform}</span>
                </div>
              </td>
              <td>
                {#if acct.has_cookies}
                  <span class="badge ok" title="Cookies tersedia">✅ Cookies</span>
                {:else}
                  <span class="badge na" title="Belum ada cookies">❌ Belum ada</span>
                {/if}
              </td>
              <td>
                <span class="used-txt">
                  {#if fmtLastUsed(acct.last_used_at)}
                    {fmtLastUsed(acct.last_used_at)}
                  {:else}
                    <span style="color:var(--mut)">—</span>
                  {/if}
                </span>
              </td>
              <td>
                <div class="row-actions">
                  <button class="btn-row" onclick={() => openEdit(acct)}>Edit</button>
                  <button class="btn-row danger" onclick={() => deleteAccount(acct)} title="Hapus akun">
                    <svg class="ic"><use href="#i-trash"/></svg>
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<!-- ── Modal ──────────────────────────────────────────────────────────────────── -->
{#if modal}
  <!-- ponytail: single modal state var, no component split — one instance, no re-use -->
  <div
    class="backdrop"
    transition:fade={{ duration: 200 }}
    onclick={onBackdropClick}
    aria-hidden="true"
  ></div>

  <div
    class="modal-panel"
    bind:this={panelEl}
    role="dialog"
    aria-modal="true"
    aria-label={modal.mode === 'add' ? 'Tambah akun scraping' : 'Edit akun scraping'}
    tabindex="-1"
    transition:scale={{ duration: 230, start: 0.94, easing: cubicOut }}
    onkeydown={trapFocus}
  >
    <!-- header -->
    <div class="m-head">
      <span class="m-title">{modal.mode === 'add' ? 'Tambah akun scraping' : 'Edit akun'}</span>
      <button class="m-close" onclick={closeModal} aria-label="Tutup modal">
        <svg class="ic"><use href="#i-x"/></svg>
      </button>
    </div>

    <!-- body -->
    <div class="m-body">
      <!-- Platform -->
      <label class="field">
        <span class="field-label">Platform</span>
        {#if modal.mode === 'add'}
          <select class="inp" bind:value={mPlatform}>
            {#each PLATFORMS as p}
              <option value={p.id}>{p.label}</option>
            {/each}
          </select>
        {:else}
          <!-- edit: platform shown read-only, bind firstInput to handle -->
          <div class="inp-readonly">
            <svg class="plat-ico-sm"><use href="#{PLAT[mPlatform]?.icon ?? 'i-yt'}"/></svg>
            {PLAT[mPlatform]?.label ?? mPlatform}
          </div>
        {/if}
      </label>

      <!-- Handle -->
      <label class="field">
        <span class="field-label">Handle / username</span>
        <input
          class="inp"
          placeholder="contoh: @burner_akun_yt"
          bind:value={mHandle}
          spellcheck="false"
          autocomplete="off"
        />
      </label>

      <!-- Label -->
      <label class="field">
        <span class="field-label">Label <span class="opt">(opsional)</span></span>
        <input
          class="inp"
          placeholder="Nama mudah diingat, misal: Burner YT 1"
          bind:value={mLabel}
          spellcheck="false"
          autocomplete="off"
        />
      </label>

      <!-- Cookies -->
      <label class="field">
        <span class="field-label">
          Cookies
          {#if modal.mode === 'edit'}
            <span class="opt"> — biarkan kosong untuk mempertahankan cookies lama</span>
          {/if}
        </span>
        <textarea
          class="inp inp-mono"
          rows="7"
          placeholder="Tempel Netscape cookies.txt di sini…"
          bind:value={mCookies}
          spellcheck="false"
        ></textarea>
      </label>

      {#if mMsg}
        <div class="msg" class:err={!mMsg.ok}>{mMsg.text}</div>
      {/if}
    </div>

    <!-- footer -->
    <div class="m-foot">
      <button class="btn-ghost" onclick={closeModal}>Batal</button>
      <button
        class="btn-primary"
        disabled={mSaving || !mHandle.trim()}
        onclick={save}
      >{mSaving ? 'Menyimpan…' : 'Simpan'}</button>
    </div>
  </div>
{/if}

<style>
  .ac { padding-bottom: 60px; }

  /* ── header ──────────────────────────────────────────────────────────────────── */
  .top { margin-bottom: 10px; }
  h1   { margin: 0 0 4px; }
  .sub { color: var(--mut); font-size: 13.5px; }

  .top-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }

  /* ── help note ───────────────────────────────────────────────────────────────── */
  .help {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 13px;
    color: var(--mut);
    margin-bottom: 24px;
  }

  /* ── loading / empty ─────────────────────────────────────────────────────────── */
  .state-msg { text-align: center; padding: 48px 0; font-size: 13.5px; color: var(--mut); }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 56px 0;
    color: var(--mut);
  }
  .empty-icon { opacity: .5; }
  .empty-txt  { font-size: 14px; }

  /* ── table ───────────────────────────────────────────────────────────────────── */
  .tbl-wrap {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    overflow-x: auto;
  }

  .tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }

  .tbl thead th {
    text-align: left;
    padding: 11px 16px;
    font-size: 11.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .05em;
    color: var(--mut);
    border-bottom: 1px solid var(--line);
    white-space: nowrap;
  }

  .tbl tbody tr {
    border-bottom: 1px solid var(--line);
    transition: background .12s;
  }
  .tbl tbody tr:last-child { border-bottom: none; }
  .tbl tbody tr:hover { background: var(--soft); }
  .tbl tbody tr.row-inactive { opacity: .5; }

  .tbl td {
    padding: 12px 16px;
    vertical-align: middle;
  }

  /* ── channel cell ────────────────────────────────────────────────────────────── */
  .chan-cell { display: flex; flex-direction: column; gap: 2px; }
  .chan-handle { font-weight: 650; }
  .chan-label  { font-size: 11.5px; color: var(--mut); }

  /* ── platform cell ───────────────────────────────────────────────────────────── */
  .plat-cell {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .plat-ico {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }
  .plat-name { font-size: 13px; color: var(--mut); }

  /* ── status badges ───────────────────────────────────────────────────────────── */
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    padding: 3px 9px;
    border-radius: 999px;
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .badge.ok {
    background: rgba(10,179,156,.1);
    border-color: rgba(10,179,156,.25);
    color: var(--green);
  }
  .badge.na {
    background: var(--soft);
    border-color: var(--line);
    color: var(--mut);
  }

  /* ── last used ───────────────────────────────────────────────────────────────── */
  .used-txt { font-size: 12.5px; color: var(--mut); }

  /* ── row action buttons ──────────────────────────────────────────────────────── */
  .row-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    justify-content: flex-end;
  }

  .btn-row {
    background: none;
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 5px 12px;
    font-size: 12.5px;
    color: var(--txt);
    cursor: pointer;
    font-family: inherit;
    white-space: nowrap;
    transition: border-color .12s, color .12s;
  }
  .btn-row:hover { border-color: var(--accent); color: var(--accent); }
  .btn-row.danger {
    padding: 5px 8px;
    color: var(--mut);
  }
  .btn-row.danger:hover { border-color: var(--red); color: var(--red); }

  /* ── primary button (shared between table header + modal footer) ─────────────── */
  .btn-primary {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 9px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 650;
    cursor: pointer;
    font-family: inherit;
    white-space: nowrap;
    transition: opacity .15s;
  }
  .btn-primary:hover:not(:disabled) { opacity: .88; }
  .btn-primary:disabled { opacity: .45; cursor: default; }

  .btn-ghost {
    background: var(--soft);
    color: var(--txt);
    border: 1px solid var(--line);
    border-radius: 9px;
    padding: 8px 18px;
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
    transition: background .12s;
  }
  .btn-ghost:hover { background: var(--line); }

  /* ── modal backdrop ──────────────────────────────────────────────────────────── */
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, .55);
    z-index: 100;
    cursor: pointer;
  }

  /* ── modal panel ─────────────────────────────────────────────────────────────── */
  .modal-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 101;
    width: min(520px, calc(100vw - 32px));
    max-height: calc(100vh - 48px);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    box-shadow: 0 24px 64px rgba(0, 0, 0, .28);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .m-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }

  .m-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--txt);
  }

  .m-close {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--mut);
    padding: 4px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color .15s, background .15s;
  }
  .m-close:hover { color: var(--txt); background: var(--soft); }
  .m-close svg { width: 18px; height: 18px; }

  .m-body {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .m-foot {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    padding: 14px 20px;
    border-top: 1px solid var(--line);
    flex-shrink: 0;
  }

  /* ── form fields ─────────────────────────────────────────────────────────────── */
  .field {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .field-label {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--txt);
  }

  .opt {
    font-weight: 400;
    color: var(--mut);
  }

  .inp {
    background: var(--soft);
    border: 1px solid var(--line);
    border-radius: 8px;
    color: var(--txt);
    font-size: 13.5px;
    padding: 8px 11px;
    outline: none;
    font-family: inherit;
    width: 100%;
    box-sizing: border-box;
    transition: border-color .12s;
  }
  .inp:focus { border-color: var(--accent); }
  .inp::placeholder { color: var(--mut); }

  .inp-mono {
    font-family: 'Menlo', 'Consolas', monospace;
    font-size: 12px;
    line-height: 1.5;
    resize: vertical;
  }

  /* read-only platform row (edit mode) */
  .inp-readonly {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 11px;
    background: var(--soft);
    border: 1px solid var(--line);
    border-radius: 8px;
    font-size: 13.5px;
    color: var(--mut);
  }
  .plat-ico-sm { width: 18px; height: 18px; }

  /* ── feedback message ────────────────────────────────────────────────────────── */
  .msg {
    font-size: 12.5px;
    padding: 8px 12px;
    border-radius: 8px;
    background: rgba(10,179,156,.08);
    border: 1px solid rgba(10,179,156,.2);
    color: var(--green);
  }
  .msg.err {
    background: rgba(240,101,72,.08);
    border-color: rgba(240,101,72,.25);
    color: var(--red);
  }

  /* ── ic helper (in-component, same as global but scoped) ────────────────────── */
  .ic {
    width: 1em;
    height: 1em;
    display: inline-block;
    vertical-align: -0.14em;
    stroke: currentColor;
    fill: none;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  /* ── responsive ──────────────────────────────────────────────────────────────── */
  @media (max-width: 600px) {
    .tbl thead th:nth-child(4) { display: none; }
    .tbl tbody td:nth-child(4) { display: none; }
    .plat-name { display: none; }
    .top-row { flex-direction: column; }
  }
</style>
