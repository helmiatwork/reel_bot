<script>
  import { api } from '../lib/api.js'

  // ── tab state ─────────────────────────────────────────────────────────────
  let tab = $state('search')   // 'search' | 'trending' | 'channel'

  // ── search tab ────────────────────────────────────────────────────────────
  let searchQuery    = $state('')
  let searchDuration = $state('')       // '' | 'short' | 'medium' | 'long'
  let searchOrder    = $state('')       // '' | 'viewCount' | 'date'

  // ── trending tab ──────────────────────────────────────────────────────────
  let region = $state('US')
  const REGIONS = ['US','JP','GB','AU','CA','ID','SG','MY','TH','PH','VN','KR','BR','DE','FR','IN']

  // ── channel tab ───────────────────────────────────────────────────────────
  let channelInput = $state('')

  // ── shared result state ───────────────────────────────────────────────────
  let items  = $state([])
  let source = $state('')    // 'v3' | 'yt-dlp' | 'unavailable' | ''
  let loading = $state(false)
  let error   = $state('')

  // ── quota meter ───────────────────────────────────────────────────────────
  let quota = $state(null)          // {used, limit, remaining, reset_at, day} | null
  let quotaError = $state(false)    // true if fetch failed — hide meter gracefully

  async function refreshQuota() {
    const r = await api.youtubeQuota()
    if (r && typeof r.used === 'number') {
      quota = r
      quotaError = false
    } else {
      quotaError = true
    }
  }

  // relative time helper — "in 5h", "in 2h 30m", "in <1m", "expired"
  function fmtResetIn(isoStr) {
    if (!isoStr) return ''
    try {
      const diffMs = new Date(isoStr) - Date.now()
      if (diffMs <= 0) return 'expired'
      const totalMin = Math.floor(diffMs / 60000)
      const h = Math.floor(totalMin / 60)
      const m = totalMin % 60
      if (h === 0 && m === 0) return 'in <1m'
      if (h === 0) return `in ${m}m`
      if (m === 0) return `in ${h}h`
      return `in ${h}h ${m}m`
    } catch { return '' }
  }

  // ── "Send to clip pipeline" feedback ─────────────────────────────────────
  let sentIds = $state(new Set())   // video_ids already sent — maps to label text
  let sendingId = $state('')
  let runLabels = $state({})        // video_id → short run_id label

  // ── on mount: prime the quota meter ──────────────────────────────────────
  $effect(() => { refreshQuota() })

  // ── helpers ──────────────────────────────────────────────────────────────
  function ytUrl(video_id) {
    return `https://www.youtube.com/watch?v=${video_id}`
  }

  function fmtDuration(s) {
    if (!s && s !== 0) return ''
    s = Math.round(Number(s))
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    const pad = (n) => String(n).padStart(2, '0')
    if (h > 0) return `${h}:${pad(m)}:${pad(sec)}`
    return `${m}:${pad(sec)}`
  }

  function fmtNum(n) {
    n = Number(n) || 0
    if (n >= 1e9) return (n / 1e9).toFixed(1).replace('.0', '') + 'B'
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.0', '') + 'M'
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace('.0', '') + 'K'
    return String(n)
  }

  function fmtDate(iso) {
    if (!iso) return ''
    try {
      return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    } catch { return '' }
  }

  // ── fetch actions ─────────────────────────────────────────────────────────
  async function runSearch() {
    if (!searchQuery.trim()) return
    loading = true; error = ''; items = []; source = ''
    const r = await api.youtubeSearch(searchQuery.trim(), 20, searchOrder, searchDuration)
    loading = false
    if (!r) { error = 'Request failed — is the backend running?'; return }
    items  = r.items || []
    source = r.source || ''
    refreshQuota()
  }

  async function runTrending() {
    loading = true; error = ''; items = []; source = ''
    const r = await api.youtubeTrending(region, 20)
    loading = false
    if (!r) { error = 'Request failed — is the backend running?'; return }
    if (r.source === 'unavailable') {
      source = 'unavailable'
      error = 'Trending requires a YouTube Data API key. Add YOUTUBE_API_KEY to your .env and restart.'
      return
    }
    items  = r.items || []
    source = r.source || ''
    refreshQuota()
  }

  async function runChannel() {
    const id = channelInput.trim()
    if (!id) return
    loading = true; error = ''; items = []; source = ''
    const r = await api.youtubeChannelUploads(id, 20)
    loading = false
    if (!r) { error = 'Request failed — is the backend running?'; return }
    if (r.source === 'unavailable') {
      source = 'unavailable'
      error = 'Channel mining requires a YouTube Data API key. Add YOUTUBE_API_KEY to your .env and restart.'
      return
    }
    items  = r.items || []
    source = r.source || ''
    refreshQuota()
  }

  function switchTab(t) {
    tab = t
    items = []; source = ''; error = ''; loading = false
  }

  // ── "Send to clip pipeline" ───────────────────────────────────────────────
  // Calls api.clipThis(video_id) — dedicated Discover → clip pipeline endpoint.
  // On success labels the card with run_id (first 8 chars). On failure falls
  // back to clipboard copy + alert (same UX as before).
  async function sendToClip(item) {
    if (sendingId === item.video_id) return
    sendingId = item.video_id
    const url = ytUrl(item.video_id)
    const r = await api.clipThis(item.video_id)
    sendingId = ''
    if (r && r.run_id) {
      const next = new Set(sentIds)
      next.add(item.video_id)
      sentIds = next
      const shortId = String(r.run_id).slice(0, 8)
      runLabels = { ...runLabels, [item.video_id]: shortId }
    } else {
      // Fallback: copy YouTube URL to clipboard
      try { await navigator.clipboard.writeText(url) } catch (_) {}
      alert(`Could not queue automatically. URL copied to clipboard:\n${url}`)
    }
  }

  // keyboard: press Enter in inputs
  function onSearchKey(e) { if (e.key === 'Enter') runSearch() }
  function onChannelKey(e) { if (e.key === 'Enter') runChannel() }
</script>

<div class="disc">
  <!-- ── header ─────────────────────────────────────────────────────────── -->
  <div class="top">
    <div>
      <h1>Discover</h1>
      <div class="sub">Find source videos via YouTube Data API v3 — search, trending, channel mining — then send any pick into the clip pipeline.</div>
    </div>

    <!-- quota meter — only shown when data available and no persistent error -->
    {#if quota && !quotaError}
      {@const pct = quota.limit > 0 ? quota.used / quota.limit : 0}
      {@const barClass = pct >= 0.95 ? 'bar-red' : pct >= 0.8 ? 'bar-amber' : 'bar-ok'}
      <div class="quota-meter" aria-label="API quota usage">
        <div class="quota-label">
          <span class="quota-used">{quota.used.toLocaleString()} / {quota.limit.toLocaleString()} units</span>
          {#if quota.reset_at}
            <span class="quota-reset">resets {fmtResetIn(quota.reset_at)}</span>
          {/if}
        </div>
        <div class="quota-track" role="progressbar" aria-valuenow={quota.used} aria-valuemin={0} aria-valuemax={quota.limit}>
          <div class="quota-bar {barClass}" style="width: {Math.min(pct * 100, 100)}%"></div>
        </div>
      </div>
    {/if}
  </div>

  <!-- ── tabs ───────────────────────────────────────────────────────────── -->
  <div class="tabs">
    <button class="tab" class:on={tab === 'search'}  onclick={() => switchTab('search')}>Search</button>
    <button class="tab" class:on={tab === 'trending'} onclick={() => switchTab('trending')}>
      Trending
      {#if tab === 'trending' && source === 'v3'}<span class="src-badge v3">v3</span>{/if}
    </button>
    <button class="tab" class:on={tab === 'channel'} onclick={() => switchTab('channel')}>Channel mining</button>
  </div>

  <!-- ── controls ───────────────────────────────────────────────────────── -->
  {#if tab === 'search'}
    <div class="ctrl-row">
      <label class="field">
        <span class="ico">🔍</span>
        <input
          bind:value={searchQuery}
          onkeydown={onSearchKey}
          placeholder="e.g. satisfying cheese pull asmr"
          aria-label="Search query"
        />
      </label>
      <select bind:value={searchDuration} aria-label="Duration filter">
        <option value="">Any duration</option>
        <option value="short">Under 4 min</option>
        <option value="medium">4–20 min</option>
        <option value="long">Over 20 min</option>
      </select>
      <select bind:value={searchOrder} aria-label="Sort order">
        <option value="">Relevance</option>
        <option value="viewCount">View count</option>
        <option value="date">Newest</option>
      </select>
      <button class="run-btn" onclick={runSearch} disabled={loading || !searchQuery.trim()}>
        {loading ? '…' : 'Search'}
      </button>
    </div>

  {:else if tab === 'trending'}
    <div class="ctrl-row">
      <select bind:value={region} aria-label="Region">
        {#each REGIONS as r}
          <option value={r}>{r}</option>
        {/each}
      </select>
      <button class="run-btn" onclick={runTrending} disabled={loading}>
        {loading ? '…' : 'Load trending'}
      </button>
    </div>

  {:else}
    <div class="ctrl-row">
      <label class="field" style="flex:1">
        <span class="ico">📺</span>
        <input
          bind:value={channelInput}
          onkeydown={onChannelKey}
          placeholder="Channel ID — e.g. UCxxxxxxxxxxxxxxxxxxxxxx"
          aria-label="Channel ID"
        />
      </label>
      <button class="run-btn" onclick={runChannel} disabled={loading || !channelInput.trim()}>
        {loading ? '…' : 'Load uploads'}
      </button>
    </div>
  {/if}

  <!-- ── meta row (count + source badge) ───────────────────────────────── -->
  {#if items.length || source}
    <div class="meta-row">
      <span>{items.length} result{items.length !== 1 ? 's' : ''}</span>
      {#if source === 'v3'}
        <span class="pill"><span class="dot v3"></span> served by API v3</span>
      {:else if source === 'yt-dlp'}
        <span class="pill"><span class="dot dlp"></span> yt-dlp fallback</span>
      {:else if source === 'unavailable'}
        <span class="pill"><span class="dot na"></span> unavailable</span>
      {/if}
    </div>
  {/if}

  <!-- ── loading ────────────────────────────────────────────────────────── -->
  {#if loading}
    <div class="state-msg mut">Loading…</div>
  {/if}

  <!-- ── error / unavailable ────────────────────────────────────────────── -->
  {#if error && !loading}
    <div class="note">{error}</div>
  {/if}

  <!-- ── empty state ────────────────────────────────────────────────────── -->
  {#if !loading && !error && items.length === 0 && !source}
    <div class="state-msg mut">
      {#if tab === 'search'}Enter a search term and press Search.
      {:else if tab === 'trending'}Select a region and press Load trending.
      {:else}Enter a Channel ID and press Load uploads.{/if}
    </div>
  {/if}

  <!-- ── card grid ──────────────────────────────────────────────────────── -->
  {#if items.length}
    <div class="vgrid">
      {#each items as item, i}
        {@const dur = fmtDuration(item.duration_s)}
        {@const views = item.view_count ? fmtNum(item.view_count) : null}
        {@const likes = item.like_count ? fmtNum(item.like_count) : null}
        {@const sent = sentIds.has(item.video_id)}
        <div class="vcard">
          <!-- thumbnail -->
          <a
            class="thumb"
            href={ytUrl(item.video_id)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Watch {item.title} on YouTube"
          >
            {#if item.thumbnail}
              <img src={item.thumbnail} alt="" loading="lazy" />
            {:else}
              <div class="thumb-placeholder"></div>
            {/if}
            {#if tab !== 'search'}
              <span class="rank">{i + 1}</span>
            {/if}
            {#if dur}
              <span class="dur">{dur}</span>
            {/if}
          </a>

          <!-- body -->
          <div class="vbody">
            <div class="vtitle" title={item.title}>{item.title}</div>
            <div class="vchan">{item.channel_title || ''}</div>

            {#if views || likes || item.published_at}
              <div class="vstats">
                {#if views}<span><b>{views}</b> views</span>{/if}
                {#if likes}<span><b>{likes}</b> likes</span>{/if}
                {#if item.published_at && !views}
                  <span>{fmtDate(item.published_at)}</span>
                {/if}
              </div>
            {/if}

            <button
              class="send-btn"
              class:sent
              onclick={() => sendToClip(item)}
              disabled={sendingId === item.video_id || sent}
              aria-label={sent ? 'Already queued in clip pipeline' : 'Send to clip pipeline'}
            >
              {#if sendingId === item.video_id}
                Sending…
              {:else if sent && runLabels[item.video_id]}
                Queued (run {runLabels[item.video_id]})
              {:else if sent}
                ✓ Queued
              {:else}
                ✂ Send to clip pipeline
              {/if}
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- ── legend ─────────────────────────────────────────────────────────── -->
  <div class="legend">
    <span><span class="dot v3"></span> Served by YouTube Data API v3</span>
    <span><span class="dot dlp"></span> Fell back to yt-dlp (quota exhausted / key missing)</span>
    <span class="mut">Each search costs ~100 units. Trending / channel: ~1–3 units.</span>
  </div>
</div>

<style>
  /* ── layout ────────────────────────────────────────────────────────────── */
  .disc { padding-bottom: 60px; }

  /* header row: title left, quota right */
  .top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }

  /* ── quota meter ────────────────────────────────────────────────────────── */
  .quota-meter {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 200px;
    max-width: 280px;
    flex: 0 0 auto;
    padding-top: 4px;
  }
  .quota-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    font-size: 11.5px;
    color: var(--mut);
  }
  .quota-used { font-variant-numeric: tabular-nums; color: var(--txt); }
  .quota-reset { white-space: nowrap; }
  .quota-track {
    height: 5px;
    background: var(--line);
    border-radius: 999px;
    overflow: hidden;
    width: 100%;
  }
  .quota-bar {
    height: 100%;
    border-radius: 999px;
    transition: width 0.4s ease, background 0.3s ease;
  }
  .bar-ok    { background: var(--accent); }
  .bar-amber { background: var(--amber, #f59e0b); }
  .bar-red   { background: #ef4444; }

  /* ── tabs ──────────────────────────────────────────────────────────────── */
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
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .tab.on { color: var(--txt); border-bottom-color: var(--accent); font-weight: 600; }
  .tab:hover:not(.on) { color: var(--txt); }
  .src-badge { font-size: 10.5px; color: var(--green); }

  /* ── controls ──────────────────────────────────────────────────────────── */
  .ctrl-row {
    display: flex;
    gap: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
    align-items: stretch;
  }
  .field {
    flex: 1;
    min-width: 240px;
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
  .ctrl-row select {
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--txt);
    border-radius: 10px;
    padding: 0 12px;
    height: 46px;
    font-size: 13.5px;
    cursor: pointer;
    font-family: inherit;
  }
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

  /* ── meta row ──────────────────────────────────────────────────────────── */
  .meta-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: var(--mut);
    font-size: 12.5px;
    margin: 12px 2px 16px;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 4px 12px;
    color: var(--txt);
    font-size: 12px;
  }
  .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    display: inline-block;
    flex: 0 0 auto;
  }
  .dot.v3  { background: var(--accent); }
  .dot.dlp { background: var(--amber); }
  .dot.na  { background: var(--mut); }

  /* ── states ────────────────────────────────────────────────────────────── */
  .state-msg { text-align: center; padding: 48px 0; font-size: 13.5px; }
  .note {
    background: rgba(251,191,36,.08);
    border: 1px solid rgba(251,191,36,.25);
    color: #f3d27a;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 13px;
    margin-bottom: 16px;
  }

  /* ── card grid ─────────────────────────────────────────────────────────── */
  .vgrid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }
  .vcard {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: border-color 0.15s, transform 0.15s;
  }
  .vcard:hover { border-color: #34507f; transform: translateY(-2px); }

  /* thumbnail */
  .thumb {
    position: relative;
    display: block;
    aspect-ratio: 16 / 9;
    background: linear-gradient(135deg, #1b2433, #0e1420);
    overflow: hidden;
    text-decoration: none;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .thumb-placeholder { width: 100%; height: 100%; }
  .dur {
    position: absolute; right: 7px; bottom: 7px;
    background: rgba(0,0,0,.75);
    color: #fff;
    font-size: 11.5px;
    padding: 2px 6px;
    border-radius: 5px;
    font-variant-numeric: tabular-nums;
  }
  .rank {
    position: absolute; left: 8px; top: 8px;
    background: var(--accent);
    color: #0b0f17;
    font-size: 10.5px;
    font-weight: 750;
    width: 21px; height: 21px;
    border-radius: 50%;
    display: grid;
    place-items: center;
  }

  /* card body */
  .vbody { padding: 11px 12px 13px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
  .vtitle {
    font-size: 13.5px;
    font-weight: 600;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    min-height: 36px;
  }
  .vchan { color: var(--mut); font-size: 12px; }
  .vstats {
    display: flex;
    gap: 12px;
    color: var(--mut);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    margin-top: auto;
  }
  .vstats b { color: var(--txt); font-weight: 600; }

  /* send button */
  .send-btn {
    margin-top: 9px;
    background: var(--panel2, #0e1420);
    border: 1px solid var(--line);
    color: var(--green);
    border-radius: 9px;
    padding: 9px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    width: 100%;
    text-align: center;
  }
  .send-btn:hover:not(:disabled) { border-color: var(--green); }
  .send-btn.sent { color: var(--mut); cursor: default; }
  .send-btn:disabled { opacity: 0.5; cursor: default; }

  /* ── legend ────────────────────────────────────────────────────────────── */
  .legend {
    color: var(--mut);
    font-size: 12px;
    margin-top: 24px;
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
    border-top: 1px solid var(--line);
    padding-top: 14px;
    align-items: center;
  }
  .legend span { display: flex; align-items: center; gap: 7px; }

  /* ── responsive ────────────────────────────────────────────────────────── */
  @media (max-width: 600px) {
    .ctrl-row { flex-direction: column; }
    .run-btn  { width: 100%; }
    .vgrid    { grid-template-columns: 1fr 1fr; }
  }
  @media (max-width: 400px) {
    .vgrid { grid-template-columns: 1fr; }
  }
</style>
