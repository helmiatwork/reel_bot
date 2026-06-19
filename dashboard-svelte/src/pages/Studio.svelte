<script>
  import { onDestroy } from 'svelte'
  import { api, extractRunId } from '../lib/api.js'

  // chat transcript — each: { role, text, streaming, runId, run, artifact }
  let messages = $state([])
  let input = $state('')
  let busy = $state(false)
  let scroller
  const timers = new Set()

  const STEP_ORDER = ['discover', 'download', 'analyze', 'audio', 'script', 'footage', 'music', 'assemble', 'save']

  const SUGGEST = [
    'kenapa ramen Jepang enak banget',
    'street food viral di Tokyo',
    'https://youtube.com/shorts/… (analisa video ini)'
  ]

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  function scrollDown() {
    queueMicrotask(() => scroller && (scroller.scrollTop = scroller.scrollHeight))
  }

  async function send(text) {
    const msg = (text ?? input).trim()
    if (!msg || busy) return
    input = ''
    busy = true

    // Snapshot run_ids that already exist, so we only attach a NEW run this
    // turn kicks off (the agent may just chat — same as Telegram — and create none).
    const known = new Set()
    const pre = await api.runs(8)
    if (pre && pre.runs) pre.runs.forEach((r) => known.add(r.run_id))

    messages.push({ role: 'user', text: msg })
    const assistant = { role: 'assistant', text: '', streaming: true, runId: null, run: null, artifact: null }
    messages.push(assistant)
    scrollDown()

    // prior turns as history (exclude the two we just pushed)
    const history = messages.slice(0, -2).map((m) => ({ role: m.role, content: m.text }))

    api.streamChat(msg, history, {
      onDelta: (chunk) => { assistant.text += chunk; scrollDown() },
      onError: (err) => {
        assistant.text += (assistant.text ? '\n\n' : '') + `⚠️ ${err}`
        assistant.streaming = false
        busy = false
      },
      onDone: async () => {
        assistant.streaming = false
        busy = false
        resolveRun(assistant, known)
      }
    })
  }

  // Attach the pipeline run this turn started — a run_id printed in the reply,
  // or a brand-new run that appears within ~40s. If the agent only chatted
  // (no run created), nothing is attached.
  async function resolveRun(assistant, known) {
    let id = extractRunId(assistant.text)
    for (let i = 0; i < 10 && !id; i++) {
      await sleep(4000)
      const r = await api.runs(8)
      const fresh = r && r.runs && r.runs.find((x) => !known.has(x.run_id))
      if (fresh) id = fresh.run_id
    }
    if (!id) return
    assistant.runId = id
    pollRun(assistant)
  }

  async function pollRun(assistant) {
    const tick = async () => {
      const d = await api.run(assistant.runId)
      if (d) assistant.run = d
      if (d && (d.status === 'done' || d.status === 'error')) {
        clearInterval(t)
        timers.delete(t)
        if (d.status === 'done') loadArtifact(assistant)
      }
      scrollDown()
    }
    const t = setInterval(tick, 4000)
    timers.add(t)
    tick()
  }

  async function loadArtifact(assistant) {
    assistant.artifact = await api.artifact(assistant.runId)
    scrollDown()
  }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  onDestroy(() => timers.forEach(clearInterval))
</script>

<div class="studio">
  <div class="top">
    <div><h1>Studio</h1><div class="sub">Ngobrol sama agent — sama kaya Telegram. Ketik topik atau URL, agent yang validasi + jalanin produksi.</div></div>
  </div>

  <div class="chat" bind:this={scroller}>
    {#if !messages.length}
      <div class="empty">
        <div class="hi">Mau bikin video apa?</div>
        <div class="mut" style="font-size:12.5px;margin:6px 0 16px">Tulis topik bebas atau tempel URL YouTube. Contoh:</div>
        <div class="sugg">
          {#each SUGGEST as s}
            <button class="chiprow" onclick={() => send(s)}>{s}</button>
          {/each}
        </div>
      </div>
    {/if}

    {#each messages as m}
      {#if m.role === 'user'}
        <div class="row user"><div class="bubble u">{m.text}</div></div>
      {:else}
        <div class="row bot">
          <div class="bubble b">
            <div class="who"><span class="dot"></span> reelbot {#if m.streaming}<span class="typing">mengetik…</span>{/if}</div>
            {#if m.text}<div class="txt">{m.text}</div>{/if}

            {#if m.runId}
              <div class="runbox">
                <div class="runhdr">Produksi <span class="mut">{m.runId.slice(0, 8)}…</span>
                  {#if m.run}<span class="chip {m.run.status === 'done' ? 'c-done' : m.run.status === 'error' ? 'c-err' : 'c-run'}">{m.run.status}</span>{/if}
                </div>
                <div class="steps">
                  {#each STEP_ORDER as st}
                    {@const s = (m.run?.steps || []).find((x) => x.step === st)}
                    <div class="step {s ? s.status : 'pending'}"><span class="dot"></span> {st}<span class="st">{s ? s.status : '—'}</span></div>
                  {/each}
                </div>
                {#each (m.run?.steps || []).filter((s) => s.status === 'error' && s.error) as e}
                  <div class="mut" style="font-size:11.5px;margin-top:6px"><span class="down">{e.step}:</span> {e.error}</div>
                {/each}

                {#if m.artifact}
                  <div class="arthdr">Hasil</div>
                  <div style="display:flex;gap:8px;flex-wrap:wrap">
                    <a class="btn" style="background:#1b2433;color:var(--txt)" href={api.artifactDownloadUrl(m.runId)} download>⬇ Download JSON</a>
                  </div>
                  {#if m.artifact?.content?.script?.title || m.artifact?.content?.title}
                    <div class="kv" style="margin-top:8px"><span>Judul</span><span style="text-align:right;max-width:62%">{m.artifact.content.script?.title || m.artifact.content.title}</span></div>
                  {/if}
                  {#if m.artifact?.summary}
                    <pre class="summary">{m.artifact.summary}</pre>
                  {/if}
                {/if}
              </div>
            {/if}
          </div>
        </div>
      {/if}
    {/each}
  </div>

  <div class="composer">
    <textarea class="ask" rows="1" placeholder="Ask anything — topik atau URL YouTube…" bind:value={input} onkeydown={onKey} disabled={busy}></textarea>
    <button class="send" onclick={() => send()} disabled={busy || !input.trim()} title="Kirim">{busy ? '…' : '↑'}</button>
  </div>
  <div class="mut foot">Agent ini bisa salah — cek hasilnya sebelum publish.</div>
</div>

<style>
  .studio { display: flex; flex-direction: column; height: calc(100vh - 48px); }
  .chat { flex: 1; overflow-y: auto; padding: 8px 2px 16px; }
  .empty { max-width: 560px; margin: 8vh auto 0; text-align: center; }
  .empty .hi { font-size: 22px; font-weight: 650; }
  .sugg { display: flex; flex-direction: column; gap: 8px; align-items: center; }
  .chiprow { background: var(--panel); border: 1px solid var(--line); color: var(--txt); border-radius: 10px; padding: 10px 14px; font-size: 12.5px; cursor: pointer; width: 100%; max-width: 420px; text-align: left; }
  .chiprow:hover { border-color: var(--accent); }
  .row { display: flex; margin: 10px 0; }
  .row.user { justify-content: flex-end; }
  .bubble { max-width: 80%; border-radius: 14px; padding: 11px 14px; font-size: 13px; line-height: 1.5; }
  .bubble.u { background: linear-gradient(135deg, #6ea8fe, #a78bfa); color: #0b0f17; font-weight: 500; }
  .bubble.b { background: var(--panel); border: 1px solid var(--line); }
  .who { display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: var(--mut); margin-bottom: 6px; }
  .who .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); }
  .typing { color: var(--amber); }
  .txt { white-space: pre-wrap; }
  .runbox { margin-top: 10px; border-top: 1px solid var(--line); padding-top: 10px; }
  .runhdr, .arthdr { font-size: 12px; font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
  .arthdr { margin-top: 12px; }
  .chip.c-done { background: rgba(52,211,153,.15); color: var(--green); }
  .chip.c-err { background: rgba(248,113,113,.15); color: var(--red); }
  .chip.c-run { background: rgba(251,191,36,.15); color: var(--amber); }
  .summary { white-space: pre-wrap; font-size: 11.5px; background: #0c1320; border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin-top: 8px; max-height: 220px; overflow: auto; }
  .composer { display: flex; gap: 8px; align-items: flex-end; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 8px 10px; }
  .ask { flex: 1; background: transparent; border: 0; color: var(--txt); font-size: 13.5px; resize: none; outline: none; max-height: 160px; padding: 6px 4px; font-family: inherit; }
  .send { flex: 0 0 auto; width: 36px; height: 36px; border-radius: 50%; border: 0; background: linear-gradient(135deg, #6ea8fe, #a78bfa); color: #0b0f17; font-size: 16px; font-weight: 700; cursor: pointer; }
  .send:disabled { opacity: .4; cursor: default; }
  .foot { text-align: center; font-size: 11px; margin-top: 8px; }
</style>
