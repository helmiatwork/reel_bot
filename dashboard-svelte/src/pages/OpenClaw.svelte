<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import { api, extractRunId } from '../lib/api.js'

  // -- State --
  let messages = $state([
    {
      role: 'assistant',
      text: 'Halo! Kirim URL YouTube atau topik. Untuk video panjang, aku bisa cariin momen clippable terbaik. 🎬',
      streaming: false,
      runId: null
    }
  ])
  let input = $state('')
  let busy = $state(false)
  let connStatus = $state('connecting') // 'connected' | 'down' | 'connecting'
  let selectedAgent = $state('reelbot')
  let scroller

  const AGENTS = ['reelbot', 'clipfinder', 'clipper', 'longvideo']

  // NOTE: streamChat POSTs {message, history} — no agent field is sent to the backend.
  // The backend uses a server-side fixed OPENCLAW_MODEL and does NOT route per-agent.
  // The dropdown is wired and the selected value is visible in the UI, but the backend
  // ignores it until agent-routing support is added server-side.
  // Tooltip on select reads "agent routing pending backend support".

  const CHIPS = [
    { label: '📋 Cari clip dari URL', prompt: 'tolong cari clip terbaik dari video ini: ' },
    { label: '✍️ Tulis script Short', prompt: 'tolong tulis script Short viral untuk topik: ' },
    { label: '📊 Analisa video', prompt: 'tolong analisa video ini dan berikan insight: ' },
    { label: '🎯 Saran formula viral', prompt: 'berikan saran formula konten viral untuk niche: ' }
  ]

  const timers = new Set()
  let abortChat = null

  // -- Health check --
  async function checkConnection() {
    try {
      const r = await api.services()
      if (r && r.services) {
        // Check if openclaw service specifically is up
        const oc = r.services.find((s) => s.name && s.name.toLowerCase().includes('openclaw'))
        if (oc) {
          connStatus = oc.up ? 'connected' : 'down'
        } else {
          // Fall back: if any services respond, consider connected
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
    // Focus textarea
    const ta = document.querySelector('.oc-textarea')
    if (ta) { ta.focus(); ta.dispatchEvent(new Event('input')) }
  }

  // -- Send message --
  async function send(textOverride) {
    const msg = (textOverride ?? input).trim()
    if (!msg || busy) return
    input = ''
    // Reset textarea height
    const ta = document.querySelector('.oc-textarea')
    if (ta) ta.style.height = 'auto'
    busy = true

    messages.push({ role: 'user', text: msg, streaming: false, runId: null })
    const assistant = { role: 'assistant', text: '', streaming: true, runId: null }
    messages.push(assistant)
    scrollDown()

    // Build history from all prior messages (exclude the two just pushed)
    const history = messages.slice(0, -2).map((m) => ({ role: m.role, content: m.text }))

    abortChat = api.streamChat(msg, history, {
      onDelta: (chunk) => {
        assistant.text += chunk
        scrollDown()
      },
      onError: (err) => {
        assistant.text += (assistant.text ? '\n\n' : '') + `Gagal: ${err}`
        assistant.streaming = false
        busy = false
        abortChat = null
      },
      onDone: () => {
        assistant.streaming = false
        busy = false
        abortChat = null
        // Try to extract run_id from the reply
        const id = extractRunId(assistant.text)
        if (id) assistant.runId = id
        scrollDown()
      }
    })
  }

  // -- Keyboard handler --
  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  // -- Lifecycle --
  onMount(() => {
    checkConnection()
    // Re-check every 30s (best-effort, no crash if fails)
    const t = setInterval(checkConnection, 30000)
    timers.add(t)
  })

  onDestroy(() => {
    timers.forEach(clearInterval)
    if (abortChat) abortChat()
  })
</script>

<div class="oc-page">
  <!-- Header -->
  <div class="oc-top">
    <h1 class="oc-title">🦅 OpenClaw</h1>
    <span class="oc-status" class:down={connStatus === 'down'} class:connecting={connStatus === 'connecting'}>
      <span class="oc-dot"></span>
      {connStatus === 'connected' ? 'connected' : connStatus === 'down' ? 'down' : 'connecting…'}
    </span>
    <span class="oc-agent-wrap" title="agent routing pending backend support">
      <span class="oc-agent-label">agent</span>
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
            <div class="oc-who">Kamu</div>
            <p class="oc-text">{m.text}</p>
          </div>
        </div>
      {:else}
        <div class="oc-row">
          <div class="oc-av" aria-hidden="true">🦅</div>
          <div class="oc-bubble oc-bubble-bot">
            <div class="oc-who">
              OpenClaw · {selectedAgent}
              {#if m.runId}<span class="oc-badge">run {m.runId.slice(0, 8)}</span>{/if}
            </div>
            {#if m.streaming && !m.text}
              <!-- Typing indicator: awaiting first token -->
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
        placeholder="Kirim URL atau perintah ke OpenClaw…"
        bind:value={input}
        onkeydown={onKey}
        disabled={busy}
        use:autoGrow
        aria-label="Message input"
        aria-multiline="true"
      ></textarea>
      <button
        class="oc-send"
        onclick={() => send()}
        disabled={busy || !input.trim()}
        aria-label="Send message"
      >{busy ? '…' : '↑'}</button>
    </div>
    <div class="oc-hint">
      <span>Enter kirim · Shift+Enter baris baru</span>
      <span>via /dash/chat (streaming)</span>
    </div>
  </div>
</div>

<style>
  /* Page layout — fills the .main area */
  .oc-page {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 48px);
    max-width: 860px;
    margin: 0 auto;
  }

  /* Header */
  .oc-top {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 4px 14px;
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
  .oc-agent-label {
    font-size: 12px;
  }
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
    padding: 22px 4px;
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
  .oc-row-me .oc-av {
    background: #1f3a5f;
  }

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
    padding: 10px 4px 8px;
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
  .oc-chip:hover {
    border-color: var(--accent);
  }
  .oc-chip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Composer */
  .oc-composer {
    padding: 8px 0 18px;
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
  .oc-box:focus-within {
    border-color: var(--accent);
  }
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
  .oc-textarea:disabled {
    opacity: 0.6;
  }
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
  .oc-send:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .oc-send:not(:disabled):hover {
    opacity: 0.85;
  }
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

  /* Responsive */
  @media (max-width: 640px) {
    .oc-chips { gap: 6px; }
    .oc-chip { font-size: 12px; padding: 5px 10px; }
    .oc-thread { padding: 14px 2px; }
  }
</style>
