<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api, extractRunId } from '../lib/api.js'

  // ── Session sidebar state ─────────────────────────────────────────────────
  let sessions = $state([])          // [{key, title, model, updated}]
  let activeKey = $state(null)       // OpenClaw UUID of the active session
  let sidebarLoading = $state(false)

  // Persist active session key across page refreshes.
  const STORAGE_KEY = 'oc_active_session'

  function saveActiveKey(k) {
    try { localStorage.setItem(STORAGE_KEY, k || '') } catch (_) {}
  }
  function loadActiveKey() {
    try { return localStorage.getItem(STORAGE_KEY) || null } catch (_) { return null }
  }

  // Generate a random UUID v4 for new sessions (frontend-side key).
  // OpenClaw won't use this value as the filename — it assigns its own UUID —
  // but passing it consistently on every request for the same "new chat" pins
  // that exchange to one OpenClaw session. Once a reply arrives we refresh the
  // session list and adopt the OpenClaw UUID as the canonical key.
  function genUUID() {
    return crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
          const r = (Math.random() * 16) | 0
          return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
        })
  }

  // Pending key used while a new chat is in progress (before the first reply
  // lands and we can identify the OpenClaw UUID).
  let pendingKey = $state(null)

  async function fetchSessions() {
    sidebarLoading = true
    try {
      const data = await api.chatSessions()
      if (data && data.sessions) sessions = data.sessions
    } finally {
      sidebarLoading = false
    }
  }

  async function newChat() {
    pendingKey = genUUID()
    activeKey = null
    saveActiveKey(null)
    messages = [WELCOME_MSG()]
    scrollDown()
  }

  async function switchSession(key) {
    if (key === activeKey) return
    activeKey = key
    pendingKey = null
    saveActiveKey(key)
    messages = [WELCOME_MSG()]
    scrollDown()
    // Load existing transcript
    const data = await api.chatSession(key)
    if (data && data.messages) {
      messages = data.messages.map((m) => ({
        role: m.role,
        text: m.content,
        streaming: false,
        runId: null
      }))
      if (messages.length === 0) messages = [WELCOME_MSG()]
      scrollDown()
    }
  }

  async function deleteSession(e, key) {
    e.stopPropagation()
    if (!window.confirm($_('openclaw.delete_session_confirmation'))) return
    const res = await api.chatSessionDelete(key)
    if (res && (res.deleted >= 1 || res.sid)) {
      // Remove from list immediately
      sessions = sessions.filter((s) => s.key !== key)
      // If deleted session was active, start fresh
      if (activeKey === key) {
        await newChat()
      }
    }
  }

  // Relative time formatting for sidebar item age labels
  function relAge(isoStr) {
    if (!isoStr) return ''
    const diff = (Date.now() - new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z')).getTime()) / 1000
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  }

  // ── Chat state ────────────────────────────────────────────────────────────
  function WELCOME_MSG() {
    return {
      role: 'assistant',
      text: $_('openclaw.welcome_message') || 'Halo! Kirim URL YouTube atau topik. Untuk video panjang, aku bisa cariin momen clippable terbaik. 🎬',
      streaming: false,
      runId: null
    }
  }

  let messages = $state([WELCOME_MSG()])
  let input = $state('')
  let busy = $state(false)
  let connStatus = $state('connecting') // 'connected' | 'down' | 'connecting'
  let selectedAgent = $state('reelbot')
  let scroller

  const AGENTS = ['reelbot', 'clipfinder', 'clipper', 'longvideo']

  // NOTE: streamChat POSTs {message, session_key} when session is active.
  // The backend forwards x-openclaw-session-key and does NOT resend history.
  // The agent dropdown is cosmetic; backend uses a fixed OPENCLAW_MODEL.
  // Tooltip on select reads "agent routing pending backend support".

  // Chips will be initialized with translations in effect
  let CHIPS = $state([])

  $effect(() => {
    CHIPS = [
      { label: $_('openclaw.chip_find_clips'), prompt: $_('openclaw.chip_find_clips_prompt') },
      { label: $_('openclaw.chip_write_script'), prompt: $_('openclaw.chip_write_script_prompt') },
      { label: $_('openclaw.chip_analyze_video'), prompt: $_('openclaw.chip_analyze_video_prompt') },
      { label: $_('openclaw.chip_viral_formula'), prompt: $_('openclaw.chip_viral_formula_prompt') }
    ]
  })

  const timers = new Set()
  let abortChat = null

  // -- Health check --
  async function checkConnection() {
    try {
      const r = await api.services()
      if (r && r.services) {
        const oc = r.services.find((s) => s.name && s.name.toLowerCase().includes('openclaw'))
        if (oc) {
          connStatus = oc.up ? 'connected' : 'down'
        } else {
          connStatus = r.live > 0 ? 'connected' : 'down'
        }
      } else {
        connStatus = 'down'
      }
    } catch {
      connStatus = 'down'
    }
  }

  // -- Scroll helpers --
  function scrollDown() {
    queueMicrotask(async () => {
      await tick()
      if (scroller) scroller.scrollTop = scroller.scrollHeight
    })
  }

  // -- Auto-grow textarea --
  function autoGrow(node) {
    function resize() {
      node.style.height = 'auto'
      node.style.height = Math.min(node.scrollHeight, 140) + 'px'
    }
    node.addEventListener('input', resize)
    return { destroy: () => node.removeEventListener('input', resize) }
  }

  // -- Chip: prefill composer --
  function chipClick(prompt) {
    input = prompt
    const ta = document.querySelector('.oc-textarea')
    if (ta) {
      ta.focus()
      ta.style.height = 'auto'
      ta.style.height = Math.min(ta.scrollHeight, 140) + 'px'
    }
  }

  // -- Send message --
  async function send(textOverride) {
    const msg = (textOverride ?? input).trim()
    if (!msg || busy) return
    input = ''
    const ta = document.querySelector('.oc-textarea')
    if (ta) ta.style.height = 'auto'
    busy = true

    messages.push({ role: 'user', text: msg, streaming: false, runId: null })
    messages.push({ role: 'assistant', text: '', streaming: true, runId: null })
    const ai = messages.length - 1
    scrollDown()

    // Use activeKey (existing session) or pendingKey (new chat in progress).
    const sessionKey = activeKey || pendingKey

    // In stateless mode (no session key) build history from in-browser log.
    const history = sessionKey
      ? null
      : messages.slice(0, -2).map((m) => ({ role: m.role, content: m.text }))

    abortChat = api.streamChat(
      msg,
      history,
      {
        onDelta: (chunk) => {
          messages[ai].text += chunk
          scrollDown()
        },
        onError: (err) => {
          const errorPrefix = $_('openclaw.error_message_prefix')
          messages[ai].text += (messages[ai].text ? '\n\n' : '') + `${errorPrefix} ${err}`
          messages[ai].streaming = false
          busy = false
          abortChat = null
        },
        onDone: () => {
          messages[ai].streaming = false
          busy = false
          abortChat = null
          const id = extractRunId(messages[ai].text)
          if (id) messages[ai].runId = id
          scrollDown()
          // After the first reply in a new chat, refresh the session list so
          // the new OpenClaw session UUID shows up in the sidebar.
          fetchSessions().then(() => {
            // If we were on a pending key (new chat), adopt the newest session
            // as active so subsequent messages stay in the same session.
            if (!activeKey && pendingKey && sessions.length > 0) {
              activeKey = sessions[0].key
              pendingKey = null
              saveActiveKey(activeKey)
            }
          })
        }
      },
      sessionKey
    )
  }

  // -- Keyboard handler --
  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  // -- Lifecycle --
  onMount(async () => {
    checkConnection()
    await fetchSessions()

    // Restore active session from localStorage
    const saved = loadActiveKey()
    if (saved && sessions.some((s) => s.key === saved)) {
      await switchSession(saved)
    } else if (sessions.length > 0) {
      // Auto-select newest session on first load
      await switchSession(sessions[0].key)
    }

    const t = setInterval(checkConnection, 30000)
    timers.add(t)
  })

  onDestroy(() => {
    timers.forEach(clearInterval)
    if (abortChat) abortChat()
  })
</script>

<div class="oc-layout">
  <!-- ── Session Sidebar ──────────────────────────────────────────────── -->
  <aside class="oc-sidebar">
    <button class="oc-new-btn" onclick={newChat} aria-label="New chat">
      <span class="oc-new-icon">＋</span> {$_('openclaw.new_chat_btn')}
    </button>

    <div class="oc-session-list" role="list" aria-label="Chat sessions">
      {#if sidebarLoading && sessions.length === 0}
        <div class="oc-sidebar-empty">{$_('openclaw.session_list_loading')}</div>
      {:else if sessions.length === 0}
        <div class="oc-sidebar-empty">{$_('openclaw.session_list_empty')}</div>
      {:else}
        {#each sessions as s}
          <div
            class="oc-session-item"
            class:active={s.key === activeKey}
            role="listitem"
          >
            <button
              class="oc-session-select"
              onclick={() => switchSession(s.key)}
              aria-current={s.key === activeKey ? 'true' : undefined}
              title={s.title}
            >
              <span class="oc-session-title">{s.title}</span>
              <span class="oc-session-meta">
                {#if s.model}
                  <span class="oc-model-badge">{s.model.split('/').pop()}</span>
                {/if}
                <span class="oc-session-age">{relAge(s.updated)}</span>
              </span>
            </button>
            <button
              class="oc-session-del"
              onclick={(e) => deleteSession(e, s.key)}
              title="Delete session"
              aria-label="Delete session"
            >🗑</button>
          </div>
        {/each}
      {/if}
    </div>

    <!-- Footer: active session short-id -->
    {#if activeKey}
      <div class="oc-sidebar-footer" title={activeKey}>
        {$_('openclaw.session_footer')} {activeKey.slice(0, 8)}
      </div>
    {/if}
  </aside>

  <!-- ── Main Chat Column ─────────────────────────────────────────────── -->
  <div class="oc-page">
    <!-- Header -->
    <div class="oc-top">
      <h1 class="oc-title">{$_('openclaw.title')}</h1>
      <span class="oc-status" class:down={connStatus === 'down'} class:connecting={connStatus === 'connecting'}>
        <span class="oc-dot"></span>
        {connStatus === 'connected' ? $_('openclaw.status_connected') : connStatus === 'down' ? $_('openclaw.status_down') : $_('openclaw.status_connecting')}
      </span>
      <span class="oc-agent-wrap" title="agent routing pending backend support">
        <span class="oc-agent-label">{$_('openclaw.agent_label')}</span>
        <select class="oc-select" bind:value={selectedAgent} aria-label="Select agent">
          {#each AGENTS as a}
            <option value={a}>{a}</option>
          {/each}
        </select>
      </span>
    </div>

    <!-- Thread -->
    <div class="oc-thread" bind:this={scroller} role="log" aria-live="polite" aria-label="Chat thread">
      {#each messages as m}
        {#if m.role === 'user'}
          <div class="oc-row oc-row-me">
            <div class="oc-av" aria-hidden="true">🙂</div>
            <div class="oc-bubble oc-bubble-user">
              <div class="oc-who">{$_('openclaw.user_name')}</div>
              <p class="oc-text">{m.text}</p>
            </div>
          </div>
        {:else}
          <div class="oc-row">
            <div class="oc-av" aria-hidden="true">🦅</div>
            <div class="oc-bubble oc-bubble-bot">
              <div class="oc-who">
                {$_('openclaw.assistant_name')} · {selectedAgent}
                {#if m.runId}<span class="oc-badge">{$_('openclaw.run_badge')} {m.runId.slice(0, 8)}</span>{/if}
              </div>
              {#if m.streaming && !m.text}
                <span class="oc-typing" aria-label="Typing">
                  <i></i><i></i><i></i>
                </span>
              {:else}
                <p class="oc-text">{m.text}</p>
                {#if m.streaming}
                  <span class="oc-typing" aria-label="Typing">
                    <i></i><i></i><i></i>
                  </span>
                {/if}
              {/if}
            </div>
          </div>
        {/if}
      {/each}
    </div>

    <!-- Quick-action chips -->
    <div class="oc-chips" role="group" aria-label="Quick actions">
      {#each CHIPS as c}
        <button class="oc-chip" onclick={() => chipClick(c.prompt)} aria-label={c.label}>
          {c.label}
        </button>
      {/each}
    </div>

    <!-- Composer -->
    <div class="oc-composer">
      <div class="oc-box" class:focused={false}>
        <textarea
          class="oc-textarea"
          rows="1"
          placeholder={$_('openclaw.textarea_placeholder')}
          bind:value={input}
          onkeydown={onKey}
          disabled={busy}
          use:autoGrow
          aria-label={$_('openclaw.send_aria')}
          aria-multiline="true"
        ></textarea>
        <button
          class="oc-send"
          onclick={() => send()}
          disabled={busy || !input.trim()}
          aria-label={$_('openclaw.send_aria')}
        >{busy ? '…' : '↑'}</button>
      </div>
      <div class="oc-hint">
        <span>{$_('openclaw.hint_send')}</span>
        <span>{$_('openclaw.hint_via')}</span>
      </div>
    </div>
  </div>
</div>

<style>
  /* Outer layout: sidebar + chat column */
  .oc-layout {
    display: flex;
    height: calc(100vh - 48px);
    overflow: hidden;
  }

  /* ── Sidebar ─────────────────────────────────────────────────────────── */
  .oc-sidebar {
    width: 268px;
    min-width: 268px;
    max-width: 268px;
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--line);
    background: var(--bg);
    overflow: hidden;
  }

  .oc-new-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 12px 10px 8px;
    padding: 9px 14px;
    background: var(--accent);
    color: #fff;
    border: 0;
    border-radius: 10px;
    font-size: 13.5px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
    flex-shrink: 0;
  }
  .oc-new-btn:hover { opacity: 0.87; }
  .oc-new-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .oc-new-icon { font-size: 16px; line-height: 1; }

  .oc-session-list {
    flex: 1;
    overflow-y: auto;
    padding: 4px 6px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .oc-sidebar-empty {
    font-size: 12.5px;
    color: var(--mut);
    padding: 10px 8px;
    text-align: center;
  }

  .oc-session-item {
    display: flex;
    flex-direction: row;
    align-items: stretch;
    border-radius: 8px;
    border: 1px solid transparent;
    background: none;
    color: var(--txt);
    transition: background 0.1s, border-color 0.1s;
    width: 100%;
  }
  .oc-session-item:hover {
    background: var(--panel);
    border-color: var(--line);
  }
  .oc-session-item.active {
    background: var(--panel);
    border-color: var(--accent);
  }

  .oc-session-select {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
    text-align: left;
    padding: 8px 6px 8px 10px;
    border: 0;
    border-radius: 8px 0 0 8px;
    background: none;
    cursor: pointer;
    color: var(--txt);
  }
  .oc-session-select:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }

  .oc-session-del {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 8px;
    border: 0;
    border-radius: 0 8px 8px 0;
    background: none;
    cursor: pointer;
    font-size: 13px;
    color: var(--mut);
    opacity: 0;
    transition: opacity 0.15s, color 0.15s;
  }
  .oc-session-item:hover .oc-session-del {
    opacity: 1;
  }
  .oc-session-del:hover {
    color: var(--red);
  }
  .oc-session-del:focus-visible {
    outline: 2px solid var(--red);
    outline-offset: 1px;
    opacity: 1;
  }

  .oc-session-title {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 220px;
    display: block;
  }

  .oc-session-meta {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .oc-model-badge {
    font-size: 10.5px;
    background: var(--panel2, #2a2a3a);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 1px 5px;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100px;
  }

  .oc-session-age {
    font-size: 11px;
    color: var(--mut);
    white-space: nowrap;
  }

  .oc-sidebar-footer {
    padding: 8px 12px;
    font-size: 11px;
    color: var(--mut);
    border-top: 1px solid var(--line);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
  }

  /* ── Chat column ─────────────────────────────────────────────────────── */
  .oc-page {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }

  /* Header */
  .oc-top {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 16px 14px;
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }
  .oc-title {
    font-size: 19px;
    margin: 0;
    letter-spacing: -0.01em;
    display: flex;
    align-items: center;
    gap: 9px;
  }

  /* Status badge */
  .oc-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    color: var(--mut);
    background: var(--panel);
    border: 1px solid var(--line);
    padding: 4px 10px;
    border-radius: 999px;
  }
  .oc-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 0 3px rgba(52, 214, 160, 0.15);
    flex-shrink: 0;
  }
  .oc-status.down .oc-dot {
    background: var(--red);
    box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.15);
  }
  .oc-status.connecting .oc-dot {
    background: var(--amber);
    box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.15);
  }

  /* Agent dropdown */
  .oc-agent-wrap {
    margin-left: auto;
    font-size: 12.5px;
    color: var(--mut);
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: help;
  }
  .oc-agent-label { font-size: 12px; }
  .oc-select {
    background: var(--panel);
    color: var(--txt);
    border: 1px solid var(--line);
    border-radius: 9px;
    padding: 6px 9px;
    font-size: 12.5px;
    cursor: pointer;
  }
  .oc-select:focus {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }

  /* Thread */
  .oc-thread {
    flex: 1;
    overflow-y: auto;
    padding: 22px 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .oc-row {
    display: flex;
    gap: 11px;
    max-width: 88%;
    align-self: flex-start;
  }
  .oc-row-me {
    align-self: flex-end;
    flex-direction: row-reverse;
  }
  .oc-av {
    flex: none;
    width: 30px;
    height: 30px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    font-size: 15px;
    background: var(--panel);
    border: 1px solid var(--line);
  }
  .oc-row-me .oc-av { background: #1f3a5f; }

  /* Bubbles */
  .oc-bubble {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 13px;
    padding: 11px 14px;
    font-size: 14px;
    line-height: 1.55;
  }
  .oc-bubble-user {
    background: #1f3a5f;
    border-color: #2c4a6e;
  }
  .oc-who {
    font-size: 11.5px;
    color: var(--mut);
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .oc-text {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* run_id badge */
  .oc-badge {
    display: inline-block;
    font-size: 11px;
    background: var(--panel2);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 1px 7px;
    color: var(--mut);
  }

  /* Typing dots */
  .oc-typing {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    color: var(--mut);
    font-size: 13px;
    margin-top: 4px;
  }
  .oc-typing i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--mut);
    display: inline-block;
    animation: oc-bounce 1s infinite;
  }
  .oc-typing i:nth-child(2) { animation-delay: 0.15s; }
  .oc-typing i:nth-child(3) { animation-delay: 0.3s; }
  @keyframes oc-bounce {
    0%, 60%, 100% { opacity: 0.25; }
    30% { opacity: 1; }
  }

  /* Quick chips */
  .oc-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    padding: 10px 16px 8px;
    flex-shrink: 0;
  }
  .oc-chip {
    font-size: 12.5px;
    color: var(--txt);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 6px 12px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .oc-chip:hover { border-color: var(--accent); }
  .oc-chip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Composer */
  .oc-composer {
    padding: 8px 16px 18px;
    border-top: 1px solid var(--line);
    flex-shrink: 0;
  }
  .oc-box {
    display: flex;
    gap: 10px;
    align-items: flex-end;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 8px 8px 8px 14px;
    transition: border-color 0.15s;
  }
  .oc-box:focus-within { border-color: var(--accent); }
  .oc-textarea {
    flex: 1;
    background: none;
    border: 0;
    color: var(--txt);
    font-size: 14.5px;
    resize: none;
    outline: none;
    max-height: 140px;
    padding: 6px 0;
    font-family: inherit;
    line-height: 1.5;
  }
  .oc-textarea:disabled { opacity: 0.6; }
  .oc-send {
    flex: none;
    background: var(--accent);
    color: #fff;
    border: 0;
    border-radius: 10px;
    width: 40px;
    height: 40px;
    font-size: 17px;
    cursor: pointer;
    font-weight: 700;
    transition: opacity 0.15s;
  }
  .oc-send:disabled { opacity: 0.35; cursor: default; }
  .oc-send:not(:disabled):hover { opacity: 0.85; }
  .oc-send:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .oc-hint {
    font-size: 11.5px;
    color: var(--mut);
    margin: 7px 2px 0;
    display: flex;
    justify-content: space-between;
  }

  /* Responsive: collapse sidebar on narrow screens */
  @media (max-width: 760px) {
    .oc-sidebar {
      display: none;
    }
    .oc-chips { gap: 6px; padding: 10px 8px 8px; }
    .oc-chip { font-size: 12px; padding: 5px 10px; }
    .oc-thread { padding: 14px 8px; }
    .oc-composer { padding: 8px 8px 18px; }
    .oc-top { padding: 4px 8px 14px; }
  }
</style>
