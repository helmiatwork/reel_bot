<script>
  import { api } from '../lib/api.js'

  let topic    = $state('')
  let platform = $state('youtube')
  let niche    = $state('')
  let loading  = $state(false)
  let error    = $state('')
  let result   = $state(null)

  async function analyze() {
    if (!topic.trim()) return
    loading = true
    error = ''
    result = null
    const r = await api.seoAnalyze(topic.trim(), platform, niche.trim())
    loading = false
    if (!r)        { error = 'Request failed — is the backend running?'; return }
    if (r.detail)  { error = r.detail; return }
    if (r.error)   { error = r.error;  return }
    result = r
  }

  function onTopicKey(e) { if (e.key === 'Enter' && !e.shiftKey) analyze() }

  // ponytail: native clipboard, no library needed
  let copied = $state(null)
  async function copy(text, key) {
    try {
      await navigator.clipboard.writeText(text)
      copied = key
      setTimeout(() => { if (copied === key) copied = null }, 1500)
    } catch { /* silent — clipboard blocked in non-secure context */ }
  }

  const SOURCE_LABEL = {
    autocomplete:   'suggest',
    trends_rising:  'rising',
    trends_top:     'top',
  }
</script>

<div class="seo">
  <div class="top">
    <div>
      <h1>SEO</h1>
      <div class="sub">Keyword research, trending queries, and content suggestions for a topic.</div>
    </div>
  </div>

  <!-- ── Search form ───────────────────────────────────────────────────────── -->
  <div class="ctrl-row">
    <label class="field" style="flex:3">
      <span class="ico">
        <svg class="ic" aria-hidden="true"><use href="#i-search"/></svg>
      </span>
      <input
        bind:value={topic}
        onkeydown={onTopicKey}
        placeholder="Topic — e.g. japanese street food"
        aria-label="Topic"
        disabled={loading}
      />
    </label>

    <label class="field sel-field">
      <select bind:value={platform} disabled={loading} aria-label="Platform">
        <option value="youtube">YouTube</option>
        <option value="tiktok">TikTok</option>
        <option value="instagram">Instagram</option>
        <option value="xiaohongshu">Xiaohongshu</option>
      </select>
    </label>

    <label class="field">
      <input
        bind:value={niche}
        placeholder="Niche (optional)"
        aria-label="Niche"
        disabled={loading}
      />
    </label>

    <button class="run-btn" onclick={analyze} disabled={loading || !topic.trim()}>
      {loading ? '…' : 'Analyze'}
    </button>
  </div>

  <!-- ── States ────────────────────────────────────────────────────────────── -->
  {#if loading}
    <div class="state-msg mut">Analyzing… fetching keywords and trends.</div>
  {/if}

  {#if error && !loading}
    <div class="note">{error}</div>
  {/if}

  {#if !loading && !error && !result}
    <div class="state-msg mut">Enter a topic and press Analyze to get keyword ideas and trends.</div>
  {/if}

  <!-- ── Results ───────────────────────────────────────────────────────────── -->
  {#if result && !loading}
    <div class="results">

      <!-- Suggested titles -->
      {#if result.suggestions?.titles?.length}
        <div class="card section">
          <div class="section-head">Suggested Titles</div>
          <ul class="title-list">
            {#each result.suggestions.titles as title, i}
              <li class="title-row">
                <span class="title-text">{title}</span>
                <button
                  class="copy-btn"
                  onclick={() => copy(title, `title-${i}`)}
                  aria-label="Copy title"
                >{copied === `title-${i}` ? 'copied' : 'copy'}</button>
              </li>
            {/each}
          </ul>
        </div>
      {/if}

      <!-- Hashtags + Description side by side on wide screens -->
      <div class="two-col">
        {#if result.suggestions?.hashtags?.length}
          <div class="card section">
            <div class="section-head">Hashtags</div>
            <div class="chip-row">
              {#each result.suggestions.hashtags as tag}
                <span
                  class="chip c-hash"
                  role="button"
                  tabindex="0"
                  onclick={() => copy(tag, `tag-${tag}`)}
                  onkeydown={(e) => e.key === 'Enter' && copy(tag, `tag-${tag}`)}
                  title="Click to copy"
                >{copied === `tag-${tag}` ? 'copied!' : tag}</span>
              {/each}
            </div>
          </div>
        {/if}

        {#if result.suggestions?.description}
          <div class="card section">
            <div class="section-head-row">
              <span class="section-head">Description</span>
              <button
                class="copy-btn"
                onclick={() => copy(result.suggestions.description, 'desc')}
                aria-label="Copy description"
              >{copied === 'desc' ? 'copied' : 'copy'}</button>
            </div>
            <p class="desc-text">{result.suggestions.description}</p>
          </div>
        {/if}
      </div>

      <!-- Keywords -->
      {#if result.keywords?.length}
        <div class="card section">
          <div class="section-head">Keywords <span class="mut" style="font-weight:400;font-size:12px">({result.keywords.length})</span></div>
          <div class="kw-grid">
            {#each result.keywords as kw}
              <div class="kw-row">
                <span class="kw-term">{kw.term}</span>
                <span class="chip {kw.source === 'trends_rising' ? 'c-rise' : kw.source === 'trends_top' ? 'c-top' : 'c-auto'}">
                  {SOURCE_LABEL[kw.source] ?? kw.source}
                </span>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Trends -->
      {#if result.trends?.related_top?.length || result.trends?.related_rising?.length}
        <div class="two-col">
          {#if result.trends.related_top?.length}
            <div class="card section">
              <div class="section-head">Trending — Top</div>
              <ul class="trend-list">
                {#each result.trends.related_top as t}
                  <li class="trend-row">
                    <span class="trend-q">{t.query}</span>
                    {#if t.value != null}<span class="trend-val mut">{t.value}</span>{/if}
                  </li>
                {/each}
              </ul>
            </div>
          {/if}

          {#if result.trends.related_rising?.length}
            <div class="card section">
              <div class="section-head">Trending — Rising</div>
              <ul class="trend-list">
                {#each result.trends.related_rising as t}
                  <li class="trend-row">
                    <span class="trend-q">{t.query}</span>
                    {#if t.value != null}<span class="trend-val c-rise-txt">{t.value === 'Breakout' ? 'Breakout' : t.value}</span>{/if}
                  </li>
                {/each}
              </ul>
            </div>
          {/if}
        </div>
      {/if}

    </div>
  {/if}
</div>

<style>
  .seo { padding-bottom: 60px; }

  /* mirrors Generate.svelte ctrl-row exactly */
  .ctrl-row {
    display: flex;
    gap: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
    align-items: stretch;
  }
  .field {
    flex: 1;
    min-width: 160px;
    display: flex;
    align-items: center;
    gap: 9px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 0 14px;
  }
  .field .ico { flex: 0 0 auto; display: flex; align-items: center; }
  .field .ic  { width: 15px; height: 15px; color: var(--mut); }
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
  .field input:disabled     { opacity: 0.6; }

  /* select inherits the .field wrapper */
  .sel-field { flex: 0 0 auto; padding: 0 10px; }
  .sel-field select {
    background: none;
    border: none;
    color: var(--txt);
    font-size: 14px;
    padding: 12px 0;
    outline: none;
    font-family: inherit;
    cursor: pointer;
    appearance: auto;
  }
  .sel-field select:disabled { opacity: 0.6; }
  /* dark-mode option bg fix */
  .sel-field select option { background: var(--card, #fff); color: var(--txt); }

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
  .note {
    background: rgba(248,113,113,.1);
    border: 1px solid rgba(248,113,113,.3);
    color: var(--red);
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 13.5px;
    margin-bottom: 10px;
  }

  /* ── Results layout ──────────────────────────────────────────────────────── */
  .results { display: flex; flex-direction: column; gap: 12px; margin-top: 6px; }

  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .section { padding: 16px 18px; }

  .section-head {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--mut);
    margin-bottom: 12px;
  }
  .section-head-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .section-head-row .section-head { margin-bottom: 0; }

  /* Titles */
  .title-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
  .title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 9px 12px;
    background: var(--soft, rgba(0,0,0,.04));
    border-radius: 8px;
  }
  .title-text { font-size: 13.5px; line-height: 1.4; flex: 1; }

  /* copy button — small text button */
  .copy-btn {
    background: none;
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 11px;
    color: var(--mut);
    cursor: pointer;
    font-family: inherit;
    flex: 0 0 auto;
    white-space: nowrap;
  }
  .copy-btn:hover { color: var(--txt); border-color: var(--accent); }

  /* Hashtag chips */
  .chip-row { display: flex; flex-wrap: wrap; gap: 7px; }
  .chip {
    font-size: 11.5px;
    padding: 4px 10px;
    border-radius: 20px;
    font-weight: 600;
    white-space: nowrap;
  }
  .c-hash  { background: rgba(139,92,246,.12); color: #a78bfa; cursor: pointer; }
  .c-hash:hover { background: rgba(139,92,246,.22); }
  .c-auto  { background: rgba(100,116,139,.12); color: var(--mut); }
  .c-rise  { background: rgba(251,191,36,.15); color: var(--amber); }
  .c-top   { background: rgba(52,211,153,.15); color: var(--green); }

  /* Description */
  .desc-text { font-size: 13px; line-height: 1.6; color: var(--txt); margin: 0; }

  /* Keywords */
  .kw-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 6px;
  }
  .kw-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 10px;
    background: var(--soft, rgba(0,0,0,.04));
    border-radius: 8px;
  }
  .kw-term { font-size: 13px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* Trends */
  .trend-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
  .trend-row  { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; padding: 6px 0; border-bottom: 1px solid var(--line); }
  .trend-row:last-child { border-bottom: none; }
  .trend-q    { flex: 1; }
  .trend-val  { font-size: 12px; }
  .c-rise-txt { color: var(--amber); font-weight: 600; font-size: 11.5px; }

  @media (max-width: 700px) {
    .ctrl-row   { flex-direction: column; }
    .run-btn    { width: 100%; height: 42px; }
    .two-col    { grid-template-columns: 1fr; }
    .kw-grid    { grid-template-columns: 1fr; }
  }
</style>
