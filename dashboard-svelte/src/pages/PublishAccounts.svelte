<script>
  import { fade, scale } from 'svelte/transition'
  import { cubicOut } from 'svelte/easing'
  import { api } from '../lib/api.js'

  const PLATFORMS = [
    { id: 'youtube',      label: 'YouTube',              icon: 'i-yt' },
    { id: 'tiktok',       label: 'TikTok',               icon: 'i-tt' },
    { id: 'instagram',    label: 'Instagram',            icon: 'i-ig' },
    { id: 'xiaohongshu',  label: 'Xiaohongshu (小红书)',  icon: 'i-xhs' },
  ]

  let accounts = $state([])
  let loading = $state(true)
  let connecting = $state({})  // Track connecting state per account id

  // Modal state
  let modalOpen = $state(false)
  let modalPlatform = $state('youtube')
  let modalHandle = $state('')
  let modalLabel = $state('')
  let modalSaving = $state(false)
  let modalError = $state(null)
  let panelEl = $state(null)
  let triggerEl = $state(null)

  // ponytail: modal focus trap & backdrop close borrowed from SourceUploadModal pattern
  function closeModal() {
    modalOpen = false
    setTimeout(() => triggerEl?.focus(), 50)
  }

  function onBackdropClick(e) {
    if (e.target === e.currentTarget) closeModal()
  }

  function onKey(e) {
    if (!modalOpen) return
    if (e.key === 'Escape') closeModal()
  }

  function trapFocus(e) {
    if (!panelEl || e.key !== 'Tab') return
    const focusable = panelEl.querySelectorAll(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last?.focus() }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first?.focus() }
    }
  }

  // Reset modal state when opening
  function openAddModal() {
    triggerEl = document.activeElement
    modalPlatform = 'youtube'
    modalHandle = ''
    modalLabel = ''
    modalSaving = false
    modalError = null
    modalOpen = true
  }

  async function load() {
    loading = true
    const rows = await api.accounts(null, 'publish')
    loading = false
    if (rows) accounts = rows
  }

  $effect(() => { load() })

  async function saveAccount() {
    const handle = modalHandle.trim()
    if (!handle) return
    modalSaving = true
    modalError = null
    const r = await api.accountCreate({
      platform: modalPlatform,
      handle,
      label: modalLabel.trim() || handle,
      role: 'publish'
    })
    modalSaving = false
    if (!r || r.detail) {
      modalError = r?.detail || 'Request failed'
    } else {
      closeModal()
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
      window.location.href = r.auth_url
    } else if (r && r.detail) {
      alert(`Connection failed: ${r.detail}`)
    } else {
      alert('Connection failed. Check console and try again.')
    }
  }

  function getPlatformLabel(platformId) {
    return PLATFORMS.find(p => p.id === platformId)?.label || platformId
  }

  function getPlatformIcon(platformId) {
    return PLATFORMS.find(p => p.id === platformId)?.icon || ''
  }
</script>

<svelte:window onkeydown={onKey} />

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

  <div class="table-header">
    <h2 class="table-title">Daftar Akun</h2>
    <button class="btn-add" onclick={openAddModal}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px"><path d="M12 5v14M5 12h14"/></svg>
      Tambah Akun
    </button>
  </div>

  {#if loading}
    <div class="state-msg">Loading…</div>
  {:else if accounts.length === 0}
    <div class="empty-state">
      <div class="empty-msg">Belum ada akun</div>
      <button class="btn-add-empty" onclick={openAddModal}>+ Tambah Akun Pertama</button>
    </div>
  {:else}
    <div class="table-wrapper">
      <table class="tbl">
        <thead>
          <tr>
            <th class="col-platform">Platform</th>
            <th class="col-handle">Handle</th>
            <th class="col-label">Label</th>
            <th class="col-status">Status</th>
            <th class="col-aktif">Aktif</th>
            <th class="col-aksi">Aksi</th>
          </tr>
        </thead>
        <tbody>
          {#each accounts as acct (acct.id)}
            <tr class:inactive={!acct.active}>
              <td class="col-platform">
                <div class="platform-cell">
                  <svg class="plat-ico"><use href="#{getPlatformIcon(acct.platform)}"/></svg>
                  <span>{getPlatformLabel(acct.platform)}</span>
                </div>
              </td>
              <td class="col-handle">@{acct.handle}</td>
              <td class="col-label">{acct.label && acct.label !== acct.handle ? acct.label : '—'}</td>
              <td class="col-status">
                {#if acct.platform === 'youtube'}
                  {#if acct.connected}
                    <span class="badge connected" title="OAuth token saved">connected</span>
                  {:else}
                    <button
                      class="btn-connect"
                      disabled={connecting[acct.id]}
                      title="Connect YouTube OAuth"
                      onclick={() => connectYoutube(acct)}
                    >
                      {connecting[acct.id] ? 'Connecting…' : 'Connect'}
                    </button>
                  {/if}
                {:else}
                  <span class="status-dash">—</span>
                {/if}
              </td>
              <td class="col-aktif">
                <button
                  class="btn-toggle"
                  class:active={acct.active}
                  title={acct.active ? 'Aktif — klik nonaktifkan' : 'Nonaktif — klik aktifkan'}
                  onclick={() => toggleActive(acct)}
                >
                  {acct.active ? 'aktif' : 'nonaktif'}
                </button>
              </td>
              <td class="col-aksi">
                <button class="btn-delete" title="Hapus akun" onclick={() => deleteAccount(acct)}>
                  <svg class="ic-del"><use href="#i-trash"/></svg>
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<!-- Add Account Modal -->
{#if modalOpen}
  <!-- Backdrop -->
  <div
    class="backdrop"
    transition:fade={{ duration: 200 }}
    onclick={onBackdropClick}
    aria-hidden="true"
  ></div>

  <!-- Modal Panel -->
  <div
    class="modal-panel"
    bind:this={panelEl}
    role="dialog"
    aria-modal="true"
    aria-label="Tambah Akun"
    tabindex="-1"
    transition:scale={{ duration: 230, start: 0.94, easing: cubicOut }}
    onkeydown={trapFocus}
  >
    <!-- Header -->
    <div class="m-head">
      <span class="m-title">Tambah Akun Earning</span>
      <button class="m-close" onclick={closeModal} aria-label="Tutup modal">
        <svg class="ic-x"><use href="#i-x"/></svg>
      </button>
    </div>

    <!-- Body -->
    <div class="m-body">
      <label class="field">
        <span class="field-label">Platform</span>
        <select class="inp" bind:value={modalPlatform} disabled={modalSaving}>
          {#each PLATFORMS as p}
            <option value={p.id}>{p.label}</option>
          {/each}
        </select>
      </label>

      <label class="field">
        <span class="field-label">Handle / Username</span>
        <input
          class="inp"
          type="text"
          placeholder="@username"
          bind:value={modalHandle}
          disabled={modalSaving}
        />
      </label>

      <label class="field">
        <span class="field-label">Label <span class="opt">(opsional)</span></span>
        <input
          class="inp"
          type="text"
          placeholder="Label atau nickname untuk akun ini"
          bind:value={modalLabel}
          disabled={modalSaving}
        />
      </label>

      {#if modalError}
        <div class="error-msg" transition:fade={{ duration: 150 }}>
          {modalError}
        </div>
      {/if}
    </div>

    <!-- Footer -->
    <div class="m-footer">
      <button class="btn-cancel" onclick={closeModal} disabled={modalSaving}>Batal</button>
      <button
        class="btn-primary"
        onclick={saveAccount}
        disabled={modalSaving || !modalHandle.trim()}
      >
        {#if modalSaving}
          <span class="spinner"></span>
          Menyimpan…
        {:else}
          Simpan
        {/if}
      </button>
    </div>
  </div>
{/if}

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

  /* ── table header ───────────────────────────────────────────────────────── */
  .table-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    gap: 12px;
  }

  .table-title {
    font-size: 16px;
    font-weight: 600;
    margin: 0;
  }

  .btn-add {
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: opacity 0.2s;
  }

  .btn-add:hover { opacity: 0.9; }

  /* ── empty state ────────────────────────────────────────────────────────── */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 60px 20px;
    text-align: center;
  }

  .empty-msg {
    font-size: 14px;
    color: var(--mut);
  }

  .btn-add-empty {
    display: inline-flex;
    align-items: center;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 13.5px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: opacity 0.2s;
  }

  .btn-add-empty:hover { opacity: 0.9; }

  /* ── table ──────────────────────────────────────────────────────────────── */
  .table-wrapper {
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
  }

  .tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }

  .tbl thead {
    background: var(--panel);
    border-bottom: 1px solid var(--line);
  }

  .tbl th {
    padding: 12px 14px;
    text-align: left;
    font-weight: 600;
    color: var(--txt);
  }

  .tbl tbody tr {
    border-bottom: 1px solid var(--line);
    background: var(--bg);
  }

  .tbl tbody tr:last-child {
    border-bottom: none;
  }

  .tbl tbody tr:hover {
    background: var(--panel);
  }

  .tbl tbody tr.inactive {
    opacity: 0.55;
  }

  .tbl td {
    padding: 12px 14px;
    vertical-align: middle;
  }

  .col-platform { width: 140px; }
  .col-handle { width: 140px; }
  .col-label { width: 140px; }
  .col-status { width: 120px; }
  .col-aktif { width: 100px; }
  .col-aksi { width: 60px; text-align: center; }

  .platform-cell {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .plat-ico {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }

  /* ── badges ─────────────────────────────────────────────────────────────── */
  .badge {
    font-size: 11.5px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid transparent;
    display: inline-block;
  }

  .badge.connected {
    background: rgba(34,197,94,.1);
    border-color: rgba(34,197,94,.3);
    color: #22c55e;
  }

  .status-dash {
    color: var(--mut);
  }

  /* ── buttons in table ───────────────────────────────────────────────────── */
  .btn-connect {
    background: rgba(99,102,241,.1);
    border: 1px solid rgba(99,102,241,.3);
    color: #818cf8;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s;
  }

  .btn-connect:hover:not(:disabled) {
    background: rgba(99,102,241,.2);
    border-color: rgba(99,102,241,.5);
  }

  .btn-connect:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .btn-toggle {
    background: var(--panel2, #0e1420);
    border: 1px solid var(--line);
    color: var(--mut);
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s;
  }

  .btn-toggle.active {
    background: rgba(99,102,241,.1);
    border-color: rgba(99,102,241,.35);
    color: #818cf8;
  }

  .btn-delete {
    background: none;
    border: none;
    cursor: pointer;
    padding: 6px;
    color: var(--mut);
    display: inline-flex;
    align-items: center;
    transition: color 0.2s;
  }

  .btn-delete:hover { color: #f87171; }

  .ic-del {
    width: 16px;
    height: 16px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  /* ── modal ──────────────────────────────────────────────────────────────── */
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999;
  }

  .modal-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: var(--bg);
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    z-index: 1000;
    max-width: 450px;
    width: 90%;
    display: flex;
    flex-direction: column;
  }

  .m-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem;
    border-bottom: 1px solid var(--line);
  }

  .m-title {
    font-weight: 600;
    font-size: 1.125rem;
  }

  .m-close {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--mut);
    transition: color 0.2s;
  }

  .m-close:hover {
    color: var(--txt);
  }

  .ic-x {
    width: 20px;
    height: 20px;
  }

  .m-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .field-label {
    font-weight: 500;
    font-size: 13px;
    color: var(--txt);
  }

  .opt {
    font-weight: normal;
    color: var(--mut);
  }

  .inp {
    padding: 0.625rem 0.75rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--panel2, #0e1420);
    color: var(--txt);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 0.2s;
  }

  .inp:focus {
    outline: none;
    border-color: var(--accent);
  }

  .inp:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .error-msg {
    padding: 0.75rem 1rem;
    background: rgba(239, 68, 68, 0.1);
    color: #dc2626;
    border-radius: 4px;
    font-size: 13px;
    margin-bottom: 0.5rem;
  }

  .m-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid var(--line);
    justify-content: flex-end;
  }

  .btn-cancel,
  .btn-primary {
    padding: 0.625rem 1rem;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
  }

  .btn-cancel {
    background: var(--panel);
    color: var(--txt);
    border: 1px solid var(--line);
  }

  .btn-cancel:hover:not(:disabled) {
    background: var(--line);
  }

  .btn-primary {
    background: var(--accent);
    color: white;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .btn-primary:hover:not(:disabled) {
    opacity: 0.9;
  }

  .btn-cancel:disabled,
  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: white;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 768px) {
    .col-label { display: none; }
    .col-platform { width: 110px; }
    .col-handle { width: 120px; }
    .col-status { width: 100px; }
    .col-aktif { width: 80px; }
  }
</style>
