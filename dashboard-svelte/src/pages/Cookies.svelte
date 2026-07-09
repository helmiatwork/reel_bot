<script>
  import { api } from '../lib/api.js'

  const PLATFORMS = [
    { id: 'instagram',   label: 'Instagram' },
    { id: 'tiktok',      label: 'TikTok' },
    { id: 'xiaohongshu', label: 'Xiaohongshu (小红书)' },
  ]

  // ponytail: deep reactive array — mutate .text/.saving/.msg directly in Svelte 5
  let platforms = $state(PLATFORMS.map(p => ({
    ...p,
    text:     '',
    saving:   false,
    deleting: false,
    msg:      null,   // { ok: bool, text: string } | null
    status:   { present: false, cookies: 0, bytes: 0 }
  })))

  let loading = $state(true)

  function fmtBytes(n) {
    n = Number(n) || 0
    if (n >= 1024) return (n / 1024).toFixed(1) + ' KB'
    return n + ' B'
  }

  async function loadStatus() {
    loading = true
    const r = await api.cookiesStatus()
    loading = false
    if (!r) return
    for (const p of platforms) {
      if (r[p.id]) p.status = r[p.id]
    }
  }

  $effect(() => { loadStatus() })

  async function save(p) {
    const content = p.text.trim()
    if (!content) return
    p.saving = true
    p.msg = null
    const r = await api.saveCookies(p.id, content)
    p.saving = false
    if (!r) {
      p.msg = { ok: false, text: 'Request failed — is the backend running?' }
    } else if (r.detail || r.error) {
      p.msg = { ok: false, text: r.detail || r.error }
    } else {
      p.msg = { ok: true, text: `Saved ${r.cookies ?? ''} cookies` }
      p.text = ''
      await loadStatus()
    }
  }

  async function del(p) {
    if (!confirm(`Delete ${p.label} cookies?`)) return
    p.deleting = true
    p.msg = null
    const r = await api.deleteCookies(p.id)
    p.deleting = false
    if (!r) {
      p.msg = { ok: false, text: 'Request failed' }
    } else {
      p.msg = { ok: true, text: `Removed ${r.removed ?? ''} cookies` }
      await loadStatus()
    }
  }
</script>

<div class="ck">
  <div class="top">
    <h1>Cookies</h1>
    <div class="sub">Manage login cookies for social platforms used during scraping.</div>
  </div>

  <div class="help">
    Export with the "Get cookies.txt LOCALLY" browser extension while logged in, then paste here.
    The file must be in Netscape tab-separated format.
  </div>

  {#if loading}
    <div class="state-msg mut">Loading…</div>
  {:else}
    <div class="cards">
      {#each platforms as p}
        <div class="card">
          <div class="card-head">
            <span class="plabel">{p.label}</span>
            {#if p.status.present}
              <span class="badge ok">&#10003; {p.status.cookies} cookie{p.status.cookies !== 1 ? 's' : ''} &middot; {fmtBytes(p.status.bytes)}</span>
            {:else}
              <span class="badge na">not set</span>
            {/if}
          </div>

          <textarea
            class="paste"
            placeholder="Paste Netscape cookies.txt here&#8230;"
            bind:value={p.text}
            rows="6"
            aria-label="{p.label} cookies.txt"
            spellcheck="false"
          ></textarea>

          {#if p.msg}
            <div class="msg" class:err={!p.msg.ok}>{p.msg.text}</div>
          {/if}

          <div class="actions">
            <button
              class="btn-save"
              disabled={p.saving || !p.text.trim()}
              onclick={() => save(p)}
            >{p.saving ? 'Saving…' : 'Save'}</button>
            {#if p.status.present}
              <button
                class="btn-del"
                disabled={p.deleting}
                onclick={() => del(p)}
              >{p.deleting ? 'Deleting…' : 'Delete'}</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .ck { padding-bottom: 60px; }

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
  }

  .state-msg { text-align: center; padding: 48px 0; font-size: 13.5px; color: var(--mut); }

  /* ── card grid ─────────────────────────────────────────────────────────── */
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }

  .card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  /* ── card header ────────────────────────────────────────────────────────── */
  .card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .plabel {
    font-size: 15px;
    font-weight: 650;
  }

  .badge {
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 999px;
    border: 1px solid transparent;
  }
  .badge.ok {
    background: rgba(34,197,94,.1);
    border-color: rgba(34,197,94,.25);
    color: var(--green, #22c55e);
  }
  .badge.na {
    background: var(--panel2, #0e1420);
    border-color: var(--line);
    color: var(--mut);
  }

  /* ── textarea ───────────────────────────────────────────────────────────── */
  .paste {
    width: 100%;
    box-sizing: border-box;
    background: var(--panel2, #0e1420);
    border: 1px solid var(--line);
    border-radius: 9px;
    color: var(--txt);
    font-size: 12px;
    font-family: 'Menlo', 'Consolas', monospace;
    padding: 10px 12px;
    resize: vertical;
    outline: none;
    line-height: 1.5;
  }
  .paste:focus { border-color: var(--accent); }
  .paste::placeholder { color: var(--mut); }

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
  .actions {
    display: flex;
    gap: 8px;
  }

  .btn-save {
    background: var(--accent);
    color: #0b0f17;
    border: none;
    border-radius: 9px;
    padding: 9px 20px;
    font-size: 13.5px;
    font-weight: 650;
    cursor: pointer;
    font-family: inherit;
    flex: 1;
  }
  .btn-save:disabled { opacity: 0.45; cursor: default; }

  .btn-del {
    background: none;
    border: 1px solid rgba(239,68,68,.35);
    color: #f87171;
    border-radius: 9px;
    padding: 9px 16px;
    font-size: 13.5px;
    cursor: pointer;
    font-family: inherit;
  }
  .btn-del:hover:not(:disabled) { border-color: #f87171; }
  .btn-del:disabled { opacity: 0.45; cursor: default; }

  /* ── responsive ─────────────────────────────────────────────────────────── */
  @media (max-width: 600px) {
    .cards { grid-template-columns: 1fr; }
  }
</style>
