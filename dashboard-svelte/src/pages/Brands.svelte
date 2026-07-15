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

  let view = $state('list')  // 'list' or 'detail'
  let brands = $state([])
  let selectedBrand = $state(null)
  let brandAccounts = $state([])
  let loading = $state(true)
  let connecting = $state({})

  // Modal state for adding brand
  let brandModalOpen = $state(false)
  let brandName = $state('')
  let brandDesc = $state('')
  let brandModalSaving = $state(false)
  let brandModalError = $state(null)
  let brandPanelEl = $state(null)
  let brandTriggerEl = $state(null)

  // Modal state for adding account
  let acctModalOpen = $state(false)
  let acctPlatform = $state('youtube')
  let acctHandle = $state('')
  let acctLabel = $state('')
  let acctModalSaving = $state(false)
  let acctModalError = $state(null)
  let acctPanelEl = $state(null)
  let acctTriggerEl = $state(null)

  function closeBrandModal() {
    brandModalOpen = false
    setTimeout(() => brandTriggerEl?.focus(), 50)
  }

  function closeAcctModal() {
    acctModalOpen = false
    setTimeout(() => acctTriggerEl?.focus(), 50)
  }

  function onBackdropClick(e) {
    if (e.target === e.currentTarget) {
      if (brandModalOpen) closeBrandModal()
      if (acctModalOpen) closeAcctModal()
    }
  }

  function onKey(e) {
    if (brandModalOpen && e.key === 'Escape') closeBrandModal()
    if (acctModalOpen && e.key === 'Escape') closeAcctModal()
  }

  function trapFocus(e, isAcct) {
    const panel = isAcct ? acctPanelEl : brandPanelEl
    if (!panel || e.key !== 'Tab') return
    const focusable = panel.querySelectorAll(
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

  function openBrandModal() {
    brandTriggerEl = document.activeElement
    brandName = ''
    brandDesc = ''
    brandModalSaving = false
    brandModalError = null
    brandModalOpen = true
  }

  function openAcctModal() {
    acctTriggerEl = document.activeElement
    acctPlatform = 'youtube'
    acctHandle = ''
    acctLabel = ''
    acctModalSaving = false
    acctModalError = null
    acctModalOpen = true
  }

  async function loadBrands() {
    loading = true
    const rows = await api.brands()
    loading = false
    if (rows) brands = rows
  }

  async function loadBrandDetail(id) {
    const brand = await api.brand(id)
    if (brand) selectedBrand = brand
    const accts = await api.accounts(null, null, id)
    if (accts) brandAccounts = accts
  }

  $effect(() => { if (view === 'list') loadBrands() })

  async function saveBrand() {
    const name = brandName.trim()
    if (!name) return
    brandModalSaving = true
    brandModalError = null
    const r = await api.brandCreate({
      name,
      description: brandDesc.trim() || null
    })
    brandModalSaving = false
    if (!r || r.detail) {
      brandModalError = r?.detail || 'Request failed'
    } else {
      closeBrandModal()
      await loadBrands()
    }
  }

  async function deleteBrand(brand) {
    if (!confirm(`Delete brand "${brand.name}"?`)) return
    const r = await api.brandDelete(brand.id)
    if (!r || r.detail) {
      alert(`Delete failed: ${r?.detail || 'Unknown error'}`)
      return
    }
    await loadBrands()
  }

  async function removeAccountFromBrand(acct) {
    if (!confirm(`Remove @${acct.handle} from this brand?`)) return
    const r = await api.accountUpdate(acct.id, { brand_id: null })
    if (!r || r.detail) {
      alert(`Failed to remove from brand: ${r?.detail || 'Unknown error'}`)
      return
    }
    await loadBrandDetail(selectedBrand.id)
  }

  async function saveAccount() {
    const handle = acctHandle.trim()
    if (!handle) return
    acctModalSaving = true
    acctModalError = null
    const r = await api.accountCreate({
      platform: acctPlatform,
      handle,
      label: acctLabel.trim() || handle,
      brand_id: selectedBrand.id
    })
    acctModalSaving = false
    if (!r || r.detail) {
      acctModalError = r?.detail || 'Request failed'
    } else {
      closeAcctModal()
      await loadBrandDetail(selectedBrand.id)
    }
  }

  async function toggleAccountActive(acct) {
    await api.accountUpdate(acct.id, { active: !acct.active })
    await loadBrandDetail(selectedBrand.id)
  }

  async function deleteAccount(acct) {
    if (!confirm(`Delete account @${acct.handle}?`)) return
    await api.accountDelete(acct.id)
    await loadBrandDetail(selectedBrand.id)
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

  function goBack() {
    view = 'list'
    selectedBrand = null
    brandAccounts = []
  }

  function goToDetail(brand) {
    selectedBrand = brand
    view = 'detail'
    loadBrandDetail(brand.id)
  }
</script>

<svelte:window onkeydown={onKey} />

{#if view === 'list'}
  <!-- ── Brand List View ──────────────────────────────────────────────────── -->
  <div class="brands-container">
    <div class="top">
      <h1>Brands</h1>
      <div class="sub">Kelompok akun earning Anda per brand/produk</div>
    </div>

    <div class="help">
      Buat brand baru untuk mengorganisir akun earning Anda di berbagai platform.
      Setiap brand dapat memiliki beberapa akun YouTube, TikTok, Instagram, dan Xiaohongshu.
    </div>

    <div class="brands-header">
      <h2 class="brands-title">Daftar Brand</h2>
      <button class="btn-add" onclick={openBrandModal}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px"><path d="M12 5v14M5 12h14"/></svg>
        Tambah Brand
      </button>
    </div>

    {#if loading}
      <div class="state-msg">Loading…</div>
    {:else if brands.length === 0}
      <div class="empty-state">
        <div class="empty-msg">Belum ada brand</div>
        <button class="btn-add-empty" onclick={openBrandModal}>+ Buat Brand Pertama</button>
      </div>
    {:else}
      <div class="brands-grid">
        {#each brands as brand (brand.id)}
          <div class="brand-card">
            <div class="brand-card-head">
              <div class="brand-info">
                <h3 class="brand-name">{brand.name}</h3>
                {#if brand.description}
                  <p class="brand-desc">{brand.description}</p>
                {/if}
              </div>
              <button
                class="btn-delete-card"
                title="Hapus brand"
                onclick={() => deleteBrand(brand)}
              >
                <svg class="ic-del"><use href="#i-trash"/></svg>
              </button>
            </div>
            <div class="brand-card-body">
              <div class="acct-count">
                <span class="count-number">{brand.account_count}</span>
                <span class="count-label">{brand.account_count === 1 ? 'akun' : 'akun'}</span>
              </div>
            </div>
            <button
              class="brand-card-action"
              onclick={() => goToDetail(brand)}
            >
              Kelola Akun
              <svg style="width:16px;height:16px;"><use href="#i-arrow-right"/></svg>
            </button>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Add Brand Modal -->
  {#if brandModalOpen}
    <div class="backdrop" transition:fade={{ duration: 200 }} onclick={onBackdropClick} aria-hidden="true"></div>
    <div
      class="modal-panel"
      bind:this={brandPanelEl}
      role="dialog"
      aria-modal="true"
      aria-label="Tambah Brand"
      tabindex="-1"
      transition:scale={{ duration: 230, start: 0.94, easing: cubicOut }}
      onkeydown={(e) => trapFocus(e, false)}
    >
      <div class="m-head">
        <span class="m-title">Tambah Brand Baru</span>
        <button class="m-close" onclick={closeBrandModal} aria-label="Tutup modal">
          <svg class="ic-x"><use href="#i-x"/></svg>
        </button>
      </div>
      <div class="m-body">
        <label class="field">
          <span class="field-label">Nama Brand</span>
          <input
            class="inp"
            type="text"
            placeholder="Nama brand/produk"
            bind:value={brandName}
            disabled={brandModalSaving}
          />
        </label>
        <label class="field">
          <span class="field-label">Deskripsi <span class="opt">(opsional)</span></span>
          <input
            class="inp"
            type="text"
            placeholder="Deskripsi singkat"
            bind:value={brandDesc}
            disabled={brandModalSaving}
          />
        </label>
        {#if brandModalError}
          <div class="error-msg" transition:fade={{ duration: 150 }}>
            {brandModalError}
          </div>
        {/if}
      </div>
      <div class="m-footer">
        <button class="btn-cancel" onclick={closeBrandModal} disabled={brandModalSaving}>Batal</button>
        <button
          class="btn-primary"
          onclick={saveBrand}
          disabled={brandModalSaving || !brandName.trim()}
        >
          {#if brandModalSaving}
            <span class="spinner"></span>
            Menyimpan…
          {:else}
            Simpan
          {/if}
        </button>
      </div>
    </div>
  {/if}

{:else if view === 'detail' && selectedBrand}
  <!-- ── Brand Detail View ────────────────────────────────────────────────── -->
  <div class="detail-container">
    <div class="detail-header">
      <button class="btn-back" onclick={goBack}>
        <svg style="width:20px;height:20px;"><use href="#i-chevron-left"/></svg>
        Kembali
      </button>
      <div class="detail-title">
        <h1>{selectedBrand.name}</h1>
        {#if selectedBrand.description}
          <p class="detail-desc">{selectedBrand.description}</p>
        {/if}
      </div>
    </div>

    <div class="accounts-section">
      <div class="accounts-header">
        <h2 class="accounts-title">Akun {selectedBrand.name}</h2>
        <button class="btn-add" onclick={openAcctModal}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px"><path d="M12 5v14M5 12h14"/></svg>
          Tambah Akun
        </button>
      </div>

      {#if brandAccounts.length === 0}
        <div class="empty-state">
          <div class="empty-msg">Belum ada akun di brand ini</div>
          <button class="btn-add-empty" onclick={openAcctModal}>+ Tambah Akun Pertama</button>
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
              {#each brandAccounts as acct (acct.id)}
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
                      onclick={() => toggleAccountActive(acct)}
                    >
                      {acct.active ? 'aktif' : 'nonaktif'}
                    </button>
                  </td>
                  <td class="col-aksi">
                    <div class="acct-actions">
                      <button class="btn-unset" title="Lepaskan dari brand" onclick={() => removeAccountFromBrand(acct)}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M6 18L18 6M6 6l12 12"/></svg>
                      </button>
                      <button class="btn-delete" title="Hapus akun" onclick={() => deleteAccount(acct)}>
                        <svg class="ic-del"><use href="#i-trash"/></svg>
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
  </div>

  <!-- Add Account Modal -->
  {#if acctModalOpen}
    <div class="backdrop" transition:fade={{ duration: 200 }} onclick={onBackdropClick} aria-hidden="true"></div>
    <div
      class="modal-panel"
      bind:this={acctPanelEl}
      role="dialog"
      aria-modal="true"
      aria-label="Tambah Akun"
      tabindex="-1"
      transition:scale={{ duration: 230, start: 0.94, easing: cubicOut }}
      onkeydown={(e) => trapFocus(e, true)}
    >
      <div class="m-head">
        <span class="m-title">Tambah Akun ke {selectedBrand.name}</span>
        <button class="m-close" onclick={closeAcctModal} aria-label="Tutup modal">
          <svg class="ic-x"><use href="#i-x"/></svg>
        </button>
      </div>
      <div class="m-body">
        <label class="field">
          <span class="field-label">Platform</span>
          <select class="inp" bind:value={acctPlatform} disabled={acctModalSaving}>
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
            bind:value={acctHandle}
            disabled={acctModalSaving}
          />
        </label>
        <label class="field">
          <span class="field-label">Label <span class="opt">(opsional)</span></span>
          <input
            class="inp"
            type="text"
            placeholder="Label atau nickname"
            bind:value={acctLabel}
            disabled={acctModalSaving}
          />
        </label>
        {#if acctModalError}
          <div class="error-msg" transition:fade={{ duration: 150 }}>
            {acctModalError}
          </div>
        {/if}
      </div>
      <div class="m-footer">
        <button class="btn-cancel" onclick={closeAcctModal} disabled={acctModalSaving}>Batal</button>
        <button
          class="btn-primary"
          onclick={saveAccount}
          disabled={acctModalSaving || !acctHandle.trim()}
        >
          {#if acctModalSaving}
            <span class="spinner"></span>
            Menyimpan…
          {:else}
            Simpan
          {/if}
        </button>
      </div>
    </div>
  {/if}
{/if}

<style>
  /* ── List view ──────────────────────────────────────────────────────────── */
  .brands-container { padding-bottom: 60px; }
  .top { margin-bottom: 10px; }
  h1 { margin: 0 0 4px; }
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

  .brands-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    gap: 12px;
  }

  .brands-title {
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

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 60px 20px;
    text-align: center;
  }

  .empty-msg { font-size: 14px; color: var(--mut); }

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

  /* ── Brand cards grid ──────────────────────────────────────────────────── */
  .brands-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }

  .brand-card {
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--bg);
    display: flex;
    flex-direction: column;
    transition: all 0.2s;
  }

  .brand-card:hover {
    border-color: var(--accent);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  .brand-card-head {
    padding: 14px;
    border-bottom: 1px solid var(--line);
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }

  .brand-info { flex: 1; }
  .brand-name { margin: 0 0 4px; font-size: 15px; font-weight: 600; }
  .brand-desc { margin: 0; font-size: 12px; color: var(--mut); }

  .btn-delete-card {
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    color: var(--mut);
    display: flex;
    align-items: center;
    transition: color 0.2s;
    flex-shrink: 0;
  }

  .btn-delete-card:hover { color: #f87171; }

  .ic-del {
    width: 16px;
    height: 16px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .brand-card-body {
    padding: 14px;
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .acct-count {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }

  .count-number { font-size: 32px; font-weight: 700; color: var(--accent); }
  .count-label { font-size: 12px; color: var(--mut); }

  .brand-card-action {
    padding: 10px 14px;
    border: none;
    background: var(--panel);
    color: var(--txt);
    border-radius: 0 0 10px 10px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: all 0.2s;
  }

  .brand-card-action:hover {
    background: var(--accent);
    color: white;
  }

  /* ── Detail view ────────────────────────────────────────────────────────── */
  .detail-container { padding-bottom: 60px; }

  .detail-header {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 24px;
  }

  .btn-back {
    display: flex;
    align-items: center;
    gap: 4px;
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--txt);
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s;
    white-space: nowrap;
    margin-top: 2px;
  }

  .btn-back:hover {
    background: var(--line);
  }

  .detail-title { flex: 1; }
  .detail-title h1 { margin: 0 0 4px; font-size: 24px; }
  .detail-desc { margin: 0; font-size: 13px; color: var(--mut); }

  .accounts-section { }

  .accounts-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    gap: 12px;
  }

  .accounts-title {
    font-size: 16px;
    font-weight: 600;
    margin: 0;
  }

  /* ── Table styles (reused from PublishAccounts) ──────────────────────── */
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
  .col-aksi { width: 90px; text-align: center; }

  .acct-actions {
    display: flex;
    gap: 6px;
    justify-content: center;
  }

  .btn-unset {
    background: none;
    border: none;
    cursor: pointer;
    padding: 6px;
    color: var(--mut);
    display: inline-flex;
    align-items: center;
    transition: color 0.2s;
  }

  .btn-unset:hover { color: #f59e0b; }

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

  .status-dash { color: var(--mut); }

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

  /* ── Modal ──────────────────────────────────────────────────────────────── */
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

  .m-title { font-weight: 600; font-size: 1.125rem; }

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

  .m-close:hover { color: var(--txt); }

  .ic-x { width: 20px; height: 20px; }

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

  .opt { font-weight: normal; color: var(--mut); }

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
    .brands-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
  }
</style>
