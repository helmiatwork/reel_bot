<script>
  import { onDestroy } from 'svelte'
  import { api } from '../lib/api.js'

  let tab = $state('script')  // 'script' | 'corpus'

  // ── Script tab ────────────────────────────────────────────────────────────
  let topic      = $state('')
  let niche      = $state('')
  let top_n      = $state(5)
  let genLoading = $state(false)
  let genError   = $state('')
  let result     = $state(null)   // { script, based_on, niches, topic }

  async function generate() {
    if (!topic.trim()) return
    genLoading = true
    genError = ''
    result = null
    const r = await api.generateScript(topic.trim(), niche.trim(), Number(top_n))
    genLoading = false
    if (!r) { genError = 'Request failed — is the backend running?'; return }
    if (r.detail) { genError = r.detail; return }
    if (r.error)  { genError = r.error;  return }
    if (!r.script) { genError = 'No corpus found for this niche — fill the corpus first.'; return }
    result = r
  }

  function onTopicKey(e) { if (e.key === 'Enter' && !e.shiftKey) generate() }

  // ── Corpus tab ────────────────────────────────────────────────────────────
  let corpusNiche   = $state('')
  let corpusCount   = $state(5)
  let corpusLoading = $state(false)
  let corpusError   = $state('')
  let corpusStatus  = $state(null)   // { status, current, added, failed }
  let corpusTimer   = null

  function stopCorpusPoll() {
    if (corpusTimer) { clearInterval(corpusTimer); corpusTimer = null }
  }

  async function pollCorpus(run_id) {
    const r = await api.discoverCorpusStatus(run_id)
    if (!r) return
    corpusStatus = r
    if (r.status === 'done' || r.status === 'error') {
      stopCorpusPoll()
      corpusLoading = false
    }
  }

  async function startCorpus() {
    if (!corpusNiche.trim()) return
    stopCorpusPoll()
    corpusLoading = true
    corpusError = ''
    corpusStatus = null
    const r = await api.discoverCorpus(corpusNiche.trim(), Number(corpusCount))
    if (!r || !r.run_id) {
      corpusLoading = false
      corpusError = r?.error || r?.detail || 'Failed to start — is the backend running?'
      return
    }
    // poll every 15 s; also fire immediately
    corpusTimer = setInterval(() => pollCorpus(r.run_id), 15000)
    pollCorpus(r.run_id)
  }

  onDestroy(stopCorpusPoll)
</script>

<div class="gen">
  <div class="top">
    <div>
      <h1>Generate</h1>
      <div class="sub">Generate a script from the corpus, or fill the corpus with new sources from a niche.</div>
    </div>
  </div>

  <!-- tabs — same pattern as Discover.svelte -->
  <div class="tabs">
    <button class="tab" class:on={tab === 'script'} onclick={() => { tab = 'script' }}>Script</button>
    <button class="tab" class:on={tab === 'corpus'} onclick={() => { tab = 'corpus' }}>Fill corpus</button>
  </div>

  {#if tab === 'script'}
    <!-- ── Script form ──────────────────────────────────────────────────── -->
    <div class="ctrl-row">
      <label class="field" style="flex:2">
        <span class="ico">✏</span>
        <input
          bind:value={topic}
          onkeydown={onTopicKey}
          placeholder="Topic — e.g. street food viral di Tokyo"
          aria-label="Topic"
          disabled={genLoading}
        />
      </label>
      <label class="field">
        <span class="ico">🏷</span>
        <input
          bind:value={niche}
          placeholder="Niche (optional)"
          aria-label="Niche"
          disabled={genLoading}
        />
      </label>
      <label class="num-label" aria-label="top_n sources">
        <span class="mut" style="font-size:11px">top_n</span>
        <input type="number" class="num-inp" bind:value={top_n} min="1" max="20"
               disabled={genLoading} aria-label="top_n" />
      </label>
      <button class="run-btn" onclick={generate} disabled={genLoading || !topic.trim()}>
        {genLoading ? '…' : 'Generate'}
      </button>
    </div>

    {#if genLoading}
      <div class="state-msg mut">Generating… this can take 1–2 min.</div>
    {/if}

    {#if genError && !genLoading}
      <div class="note">{genError}</div>
    {/if}

    {#if result && !genLoading}
      <div class="result-box card">
        {#if result.niches?.length}
          <div class="niche-row">
            {#each result.niches as n}<span class="tag">{n}</span>{/each}
          </div>
        {/if}

        <pre class="script-pre">{result.script}</pre>

        {#if result.based_on?.length}
          <div class="based-on">
            <div class="based-label mut">Based on {result.based_on.length} source{result.based_on.length !== 1 ? 's' : ''}</div>
            <div class="based-list">
              {#each result.based_on as url}
                <a href={url} target="_blank" rel="noopener noreferrer" class="src-link">{url}</a>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}

    {#if !genLoading && !genError && !result}
      <div class="state-msg mut">Enter a topic and press Generate.</div>
    {/if}

  {:else}
    <!-- ── Corpus form ──────────────────────────────────────────────────── -->
    <div class="ctrl-row">
      <label class="field" style="flex:2">
        <span class="ico">🔖</span>
        <input
          bind:value={corpusNiche}
          placeholder="Niche — e.g. japanese street food"
          aria-label="Niche"
          disabled={corpusLoading}
          onkeydown={(e) => e.key === 'Enter' && startCorpus()}
        />
      </label>
      <label class="num-label" aria-label="Count">
        <span class="mut" style="font-size:11px">count</span>
        <input type="number" class="num-inp" bind:value={corpusCount} min="1" max="50"
               disabled={corpusLoading} aria-label="count" />
      </label>
      <button class="run-btn" onclick={startCorpus} disabled={corpusLoading || !corpusNiche.trim()}>
        {corpusLoading ? '…' : 'Start'}
      </button>
    </div>

    {#if corpusError && !corpusLoading}
      <div class="note">{corpusError}</div>
    {/if}

    {#if corpusStatus}
      {@const st = corpusStatus}
      <div class="corpus-card card">
        <div class="cs-row">
          <span class="chip {st.status === 'done' ? 'c-done' : st.status === 'error' ? 'c-err' : 'c-run'}">{st.status}</span>
          {#if st.current && st.status === 'running'}
            <span class="mut" style="font-size:12px">current: <span style="color:var(--txt)">{st.current}</span></span>
          {/if}
        </div>
        <div class="cs-counts">
          <span class="up">{(st.added || []).length} added</span>
          {#if (st.failed || []).length}
            <span class="down">{st.failed.length} failed</span>
          {/if}
        </div>
        {#if st.status === 'running'}
          <div class="mut" style="font-size:12px;margin-top:6px">Polling every 15 s…</div>
        {/if}
      </div>
    {:else if !corpusLoading}
      <div class="state-msg mut">Enter a niche and press Start to fill the corpus.</div>
    {/if}
  {/if}
</div>

<style>
  .gen { padding-bottom: 60px; }

  /* tabs — mirrors Discover.svelte exactly */
  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--line);
    margin-bottom: 18px;
  }
  .tab {
    padding: 10px 16px;
    font-size: 13.5px;
    color: var(--mut);
    cursor: pointer;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    background: none;
    font-family: inherit;
    border-radius: 0;
  }
  .tab.on { color: var(--txt); border-bottom-color: var(--accent); font-weight: 600; }
  .tab:hover:not(.on) { color: var(--txt); }

  /* controls row — mirrors Discover.svelte */
  .ctrl-row {
    display: flex;
    gap: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
    align-items: stretch;
  }
  .field {
    flex: 1;
    min-width: 200px;
    display: flex;
    align-items: center;
    gap: 9px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 0 14px;
  }
  .field .ico { font-size: 15px; flex: 0 0 auto; }
  .field input {
    flex: 1;
    background: none;
    border: 0;
    color: var(--txt);
    font-size: 14px;
    padding: 12px 0;
    outline: none;
    font-family: inherit;
  }
  .field input::placeholder { color: var(--mut); }
  .field input:disabled { opacity: 0.6; }

  .num-label {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 6px 12px;
    flex: 0 0 auto;
  }
  .num-inp {
    background: none;
    border: none;
    color: var(--txt);
    font-size: 14px;
    width: 52px;
    text-align: center;
    outline: none;
    font-family: inherit;
  }
  .num-inp:disabled { opacity: 0.6; }

  .run-btn {
    background: var(--accent);
    color: #0b0f17;
    border: none;
    border-radius: 10px;
    padding: 0 20px;
    height: 46px;
    font-size: 13.5px;
    font-weight: 650;
    cursor: pointer;
    font-family: inherit;
    flex: 0 0 auto;
  }
  .run-btn:disabled { opacity: 0.45; cursor: default; }

  .state-msg { text-align: center; padding: 48px 0; font-size: 13.5px; }

  /* script result */
  .result-box { margin-top: 6px; }
  .niche-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
  .script-pre {
    white-space: pre-wrap;
    font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
    font-size: 12.5px;
    line-height: 1.6;
    background: #0c1320;
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 14px 16px;
    overflow: auto;
    max-height: 500px;
    color: var(--txt);
    margin: 0 0 14px;
  }
  .based-on { margin-top: 4px; }
  .based-label { font-size: 12px; margin-bottom: 6px; }
  .based-list { display: flex; flex-direction: column; gap: 4px; }
  .src-link {
    color: var(--accent);
    font-size: 12px;
    text-decoration: none;
    word-break: break-all;
  }
  .src-link:hover { text-decoration: underline; }

  /* corpus status */
  .corpus-card { margin-top: 10px; }
  .cs-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
  .cs-counts { display: flex; gap: 16px; font-size: 13.5px; font-weight: 600; }

  /* chip — local so no bleed into global */
  .chip { font-size: 11px; padding: 3px 9px; border-radius: 20px; font-weight: 600; }
  .c-done { background: rgba(52,211,153,.15); color: var(--green); }
  .c-err  { background: rgba(248,113,113,.15); color: var(--red); }
  .c-run  { background: rgba(251,191,36,.15);  color: var(--amber); }

  @media (max-width: 600px) {
    .ctrl-row { flex-direction: column; }
    .run-btn  { width: 100%; height: 42px; }
  }
</style>
