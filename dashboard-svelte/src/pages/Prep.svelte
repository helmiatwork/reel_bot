<script>
  import { onMount, onDestroy } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'

  let list          = $state([])
  let selectedId    = $state(null)
  let bundle        = $state(null)
  let loading       = $state(true)
  let loadingBundle = $state(false)
  let songs         = $state([])
  let settingBgm    = $state(false)
  let roughcutBuilding = $state(false)
  let pollTimer     = null
  const POLL_CAP    = 24  // 24 × 5 s ≈ 2 min

  // ── Formatters ──────────────────────────────────────────────────────────────
  function fmtSize(bytes) {
    if (!bytes) return '—'
    const mb = bytes / 1024 / 1024
    return mb >= 1 ? `${mb.toFixed(0)} MB` : `${(bytes / 1024).toFixed(0)} KB`
  }

  function fmtTC(sec) {
    if (sec == null) return '—'
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  function fmtDur(sec) {
    if (!sec) return ''
    return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
  }

  // ── Data loading ─────────────────────────────────────────────────────────────
  async function loadList() {
    loading = true
    const data = await api.prepList()
    if (Array.isArray(data) && data.length) {
      list = data
      selectedId = data[0].source_id
      await loadBundle(selectedId)
    }
    loading = false
  }

  async function loadBundle(id) {
    loadingBundle = true
    const data = await api.prepGet(id)
    bundle = data
    loadingBundle = false
    // Resume polling if roughcut was already building
    if (data?.roughcut?.status === 'building' && !roughcutBuilding) {
      startPolling()
    }
  }

  async function loadSongs() {
    const data = await api.getSongs(100, 0)
    if (data?.songs) songs = data.songs
  }

  // ── Picker ───────────────────────────────────────────────────────────────────
  async function onPickerChange(e) {
    stopPolling()
    selectedId = Number(e.currentTarget.value)
    await loadBundle(selectedId)
  }

  // ── BGM ──────────────────────────────────────────────────────────────────────
  async function onBgmChange(e) {
    const val = e.currentTarget.value
    settingBgm = true
    await api.prepSetBgm(selectedId, val ? Number(val) : null)
    await loadBundle(selectedId)
    settingBgm = false
  }

  // ── Rough-cut ─────────────────────────────────────────────────────────────────
  async function startRoughcut() {
    roughcutBuilding = true
    await api.prepRoughcut(selectedId)
    startPolling()
  }

  function startPolling() {
    roughcutBuilding = true
    let polls = 0
    pollTimer = setInterval(async () => {
      polls++
      const b = await api.prepGet(selectedId)
      if (b) bundle = b
      if (b?.roughcut?.status === 'ready' || polls >= POLL_CAP) stopPolling()
    }, 5000)
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    roughcutBuilding = false
  }

  // ── Clipboard ─────────────────────────────────────────────────────────────────
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text) } catch { /* noop */ }
  }

  onMount(() => { loadList(); loadSongs() })
  onDestroy(stopPolling)
</script>

<!-- ── Page header ────────────────────────────────────────────────────────── -->
<div class="top">
  <div>
    <h1>{$_('prep.title')}</h1>
    <div class="sub">{$_('prep.subtitle')}</div>
  </div>
</div>

{#if loading}
  <p class="mut">{$_('prep.loading_list')}</p>
{:else if !list.length}
  <div class="card" style="text-align:center;padding:40px 20px">
    <p class="mut" style="font-size:13.5px;margin:0">
      {$_('prep.no_content')}
    </p>
  </div>
{:else}

<!-- ── Picker ──────────────────────────────────────────────────────────────── -->
<div class="picker-row">
  <span class="mut" style="font-size:12.5px;white-space:nowrap">{$_('prep.pick_content')}</span>
  <select class="sel" aria-label={$_('prep.select_content')} onchange={onPickerChange}>
    {#each list as item}
      <option value={item.source_id} selected={item.source_id === selectedId}>
        {item.title || `Source #${item.source_id}`}{item.platform ? ` · ${item.platform}` : ''}
      </option>
    {/each}
  </select>
</div>

{#if loadingBundle}
  <p class="mut">{$_('prep.loading_bundle')}</p>
{:else if bundle}

<!-- ── Two-column grid ──────────────────────────────────────────────────────── -->
<div class="prep-grid">

  <!-- ── LEFT: preview + rough-cut ────────────────────────────────────────── -->
  <div class="left-col">

    <!-- Preview card -->
    <div class="card" style="margin-bottom:14px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <h3 style="margin:0">{$_('prep.preview')}</h3>
        <span class="pill" style="font-size:11.5px;padding:4px 10px">
          {$_('prep.aspect_ratio', { values: { duration: bundle.preview?.duration_sec ? ` · ${fmtDur(bundle.preview.duration_sec)}` : '' } })}
        </span>
      </div>

      {#if bundle.preview?.video_url}
        <video
          controls
          class="preview-player"
          src={bundle.preview.video_url}
          aria-label="Source preview"
        ><track kind="captions" /></video>
      {:else}
        <div class="media-placeholder mut">{$_('prep.no_preview')}</div>
      {/if}

      <!-- BGM player -->
      {#if bundle.bgm?.url}
        <div class="bgm-row">
          <div class="bgm-meta">
            <span class="mut" style="font-size:11px">{$_('prep.bgm')}</span>
            <strong style="font-size:12.5px">{bundle.bgm.title || 'BGM'}</strong>
            {#if bundle.bgm.music_key || bundle.bgm.bpm}
              <span class="mut" style="font-size:11px">
                {[bundle.bgm.music_key, bundle.bgm.bpm ? `${bundle.bgm.bpm} BPM` : ''].filter(Boolean).join(' · ')}
              </span>
            {/if}
          </div>
          <audio
            controls
            src={bundle.bgm.url}
            style="height:28px;flex:1;min-width:0;max-width:200px"
            aria-label="BGM preview"
          ></audio>
        </div>
      {/if}

      <!-- BGM picker -->
      <div class="bgm-picker-row">
        <label for="bgm-sel" class="mut" style="font-size:11.5px;white-space:nowrap">{$_('prep.change_bgm')}</label>
        <select
          id="bgm-sel"
          class="sel"
          style="flex:1;min-width:0"
          aria-label={$_('prep.select_bgm')}
          disabled={settingBgm}
          onchange={onBgmChange}
        >
          <option value="">{$_('prep.no_bgm_option')}</option>
          {#each songs as s}
            <option value={s.id} selected={s.id === bundle.bgm?.song_id}>
              {s.title || `Song #${s.id}`}{s.bpm ? ` · ${Math.round(s.bpm)} BPM` : ''}
            </option>
          {/each}
        </select>
        {#if settingBgm}<span class="mut" style="font-size:11.5px;white-space:nowrap">{$_('prep.saving')}</span>{/if}
      </div>
    </div>

    <!-- Rough-cut reference card -->
    <div class="card">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px">
        <h3 style="margin:0">{$_('prep.roughcut_title')}</h3>
        <span
          class="pill"
          style="font-size:10.5px;padding:3px 9px;background:rgba(247,184,75,.15);color:var(--amber);border-color:rgba(247,184,75,.3)"
        >{$_('prep.roughcut_note')}</span>
      </div>

      {#if bundle.roughcut?.status === 'ready' && bundle.roughcut?.url}
        <video
          controls
          class="roughcut-player"
          src={bundle.roughcut.url}
          aria-label="Rough-cut reference"
        ><track kind="captions" /></video>
        <p class="mut" style="margin:10px 0 0;font-size:11.5px">
          {@html $_('prep.roughcut_desc')}
        </p>

      {:else if bundle.roughcut?.status === 'building' || roughcutBuilding}
        <div class="media-placeholder mut" style="max-height:160px">
          <svg class="ic" style="width:18px;height:18px"><use href="#i-clock"/></svg>
          {$_('prep.roughcut_building')}
        </div>

      {:else}
        <div class="media-placeholder mut" style="max-height:120px">{$_('prep.no_roughcut')}</div>
        <button class="btn" style="margin-top:10px;font-size:12.5px" onclick={startRoughcut}>
          {$_('prep.generate_roughcut')}
        </button>
        <p class="mut" style="margin:8px 0 0;font-size:11.5px">
          {@html $_('prep.roughcut_note2')}
        </p>
      {/if}
    </div>

  </div>

  <!-- ── RIGHT: assets ─────────────────────────────────────────────────────── -->
  <div class="right-col">

    <!-- Source & Clips -->
    <div class="card" style="margin-bottom:14px">
      <h3>{$_('prep.source_clips')}</h3>

      {#if bundle.source_hd}
        <div class="clip-row">
          <div class="clip-thumb"></div>
          <div style="flex:1;min-width:0">
            <div class="clip-name">{$_('prep.source_hd')}</div>
            <div class="mut tc-line">
              {[bundle.source_hd.resolution, fmtSize(bundle.source_hd.size_bytes), $_('prep.full_download')].filter(Boolean).join(' · ')}
            </div>
          </div>
          <a href={bundle.source_hd.url} download class="dl-a" title={$_('prep.download_source')} aria-label={$_('prep.download_source')}>⬇</a>
        </div>
      {/if}

      {#each (bundle.clips || []) as clip (clip.index)}
        <div class="clip-row">
          <div class="clip-thumb"></div>
          <div style="flex:1;min-width:0">
            <div class="clip-name">
              {$_('prep.clip_item', { values: { index: clip.index + 1, label: clip.label ? ` — ${clip.label}` : '' } })}
            </div>
            <div class="mut tc-line num">{fmtTC(clip.start)} → {fmtTC(clip.end)}</div>
          </div>
          <a href={clip.url} download class="dl-a" title={$_('prep.download_clip', { values: { index: clip.index + 1 } })} aria-label={$_('prep.download_clip', { values: { index: clip.index + 1 } })}>⬇</a>
        </div>
      {/each}

      {#if !bundle.source_hd && !bundle.clips?.length}
        <p class="mut" style="font-size:12.5px;margin:0">{$_('prep.no_files')}</p>
      {/if}
    </div>

    <!-- Transcript -->
    {#if bundle.transcript}
    <div class="card" style="margin-bottom:14px">
      <h3>{$_('prep.transcript')}</h3>
      <div class="transcript-box">{bundle.transcript}</div>
    </div>
    {/if}

    <!-- Strategy -->
    {#if bundle.strategy}
    <div class="card" style="margin-bottom:14px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <h3 style="margin:0">{$_('prep.strategy')}</h3>
        {#if bundle.strategy.retention_score != null}
          <span
            class="pill"
            style="font-size:11px;padding:3px 9px;background:rgba(10,179,156,.12);color:var(--green);border-color:transparent"
          >{$_('prep.retention_score', { values: { score: bundle.strategy.retention_score } })}</span>
        {/if}
      </div>

      {#if bundle.strategy.hook}
        <div class="strat-lbl">{$_('prep.hook')}</div>
        <div style="font-size:12.5px;margin-bottom:6px">{bundle.strategy.hook}</div>
      {/if}
      {#if bundle.strategy.structure}
        <div class="strat-lbl">{$_('prep.structure')}</div>
        <div style="font-size:12.5px;margin-bottom:6px">{bundle.strategy.structure}</div>
      {/if}
      {#if bundle.strategy.retention}
        <div class="strat-lbl">{$_('prep.retention')}</div>
        <div style="font-size:12.5px">{bundle.strategy.retention}</div>
      {/if}
    </div>
    {/if}

    <!-- SEO Pack -->
    {#if bundle.seo}
    <div class="card">
      <h3>{$_('prep.seo_pack')}</h3>

      {#if bundle.seo.titles?.length}
        <ul class="titles-list">
          {#each bundle.seo.titles as title}
            <li>
              <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{title}</span>
              <button
                class="copy-btn"
                onclick={() => copyText(title)}
                title={$_('prep.copy_title')}
                aria-label={$_('prep.copy_title')}
              >⧉</button>
            </li>
          {/each}
        </ul>
      {/if}

      {#if bundle.seo.hashtags?.length}
        <div class="hashtag-row">
          {#each bundle.seo.hashtags as tag}
            <span class="htag">{tag}</span>
          {/each}
        </div>
      {/if}

      {#if bundle.seo.description}
        <div class="desc-box">{bundle.seo.description}</div>
      {/if}

      {#if !bundle.seo.titles?.length && !bundle.seo.hashtags?.length && !bundle.seo.description}
        <p class="mut" style="font-size:12.5px;margin:0">{$_('prep.no_seo_data')}</p>
      {/if}
    </div>
    {/if}

  </div>
</div>

<!-- ── Sticky download bar ──────────────────────────────────────────────────── -->
<div class="download-bar" role="region" aria-label={$_('prep.download_all_aria')}>
  <div>
    <div style="font-weight:600;font-size:13.5px">{$_('prep.download_all')}</div>
    <div class="asset-row">
      {#if bundle.source_hd}
        <span class="asset-chip">
          <svg class="ic" style="color:var(--green);width:12px;height:12px"><use href="#i-check"/></svg>
          {$_('prep.source_hd_chip', { values: { clips: bundle.clips?.length ? ` + ${bundle.clips.length} clip` : '' } })}
        </span>
      {/if}
      {#if bundle.bgm}
        <span class="asset-chip">
          <svg class="ic" style="color:var(--green);width:12px;height:12px"><use href="#i-check"/></svg>
          {$_('prep.bgm_chip')}
        </span>
      {/if}
      {#if bundle.transcript || bundle.strategy}
        <span class="asset-chip">
          <svg class="ic" style="color:var(--green);width:12px;height:12px"><use href="#i-check"/></svg>
          {$_('prep.transcript_strategy_chip')}
        </span>
      {/if}
      {#if bundle.seo}
        <span class="asset-chip">
          <svg class="ic" style="color:var(--green);width:12px;height:12px"><use href="#i-check"/></svg>
          {$_('prep.seo_pack_chip')}
        </span>
      {/if}
      {#if bundle.roughcut?.status === 'ready'}
        <span class="asset-chip">
          <svg class="ic" style="color:var(--green);width:12px;height:12px"><use href="#i-check"/></svg>
          {$_('prep.roughcut_chip')}
        </span>
      {/if}
    </div>
  </div>

  <a
    href={api.prepZipUrl(selectedId)}
    download
    class="dl-btn"
    aria-label={$_('prep.download_all_aria')}
  >{$_('prep.download_zip')}</a>
</div>

{/if}
{/if}

<style>
  /* ── Picker ──────────────────────────────────────────────────────────────── */
  .picker-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }

  .sel {
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--txt);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12.5px;
    cursor: pointer;
    font-family: inherit;
    min-width: 260px;
  }

  /* ── Grid ────────────────────────────────────────────────────────────────── */
  .prep-grid {
    display: grid;
    grid-template-columns: 1.15fr 0.85fr;
    gap: 16px;
    margin-bottom: 74px;  /* room for sticky bar */
  }

  @media (max-width: 880px) {
    .prep-grid { grid-template-columns: 1fr; }
  }

  /* ── Preview player ──────────────────────────────────────────────────────── */
  .preview-player {
    display: block;
    width: 100%;
    max-height: 340px;
    aspect-ratio: 9 / 16;
    object-fit: contain;
    background: #000;
    border-radius: 8px;
    margin: 0 auto;
  }

  .media-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    aspect-ratio: 9 / 16;
    max-height: 200px;
    background: var(--soft);
    border-radius: 8px;
    font-size: 12.5px;
  }

  .roughcut-player {
    display: block;
    width: 100%;
    max-height: 240px;
    aspect-ratio: 9 / 16;
    object-fit: contain;
    background: #000;
    border-radius: 8px;
  }

  /* ── BGM ─────────────────────────────────────────────────────────────────── */
  .bgm-row {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--soft);
    border-radius: 7px;
    padding: 9px 11px;
    margin-top: 10px;
    flex-wrap: wrap;
  }

  .bgm-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    flex: 1;
  }

  .bgm-picker-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
  }

  /* ── Clips ───────────────────────────────────────────────────────────────── */
  .clip-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid var(--line);
  }

  .clip-row:last-child { border-bottom: 0; }

  .clip-thumb {
    width: 52px;
    height: 30px;
    background: linear-gradient(135deg, var(--accent), var(--green));
    border-radius: 5px;
    flex-shrink: 0;
    opacity: 0.65;
  }

  .clip-name {
    font-size: 12.5px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--txt);
  }

  .tc-line { font-size: 11.5px; margin-top: 2px; }

  .dl-a {
    color: var(--mut);
    font-size: 14px;
    flex-shrink: 0;
    padding: 2px 4px;
  }
  .dl-a:hover { color: var(--accent); }

  /* ── Transcript ──────────────────────────────────────────────────────────── */
  .transcript-box {
    max-height: 160px;
    overflow: auto;
    font-size: 12px;
    white-space: pre-wrap;
    background: var(--soft);
    border-radius: 7px;
    padding: 10px 12px;
    color: var(--txt);
    line-height: 1.6;
  }

  /* ── Strategy ────────────────────────────────────────────────────────────── */
  .strat-lbl {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
    color: var(--mut);
    margin: 10px 0 3px;
  }

  /* ── SEO ─────────────────────────────────────────────────────────────────── */
  .titles-list {
    list-style: none;
    padding: 0;
    margin: 0 0 10px;
  }

  .titles-list li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 10px;
    background: var(--soft);
    border-radius: 6px;
    margin-bottom: 5px;
    font-size: 12.5px;
  }

  .copy-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--mut);
    padding: 0 2px;
    flex-shrink: 0;
    font-size: 14px;
    line-height: 1;
  }
  .copy-btn:hover { color: var(--accent); }

  .hashtag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin: 6px 0;
  }

  .htag {
    font-size: 11.5px;
    background: var(--soft);
    color: var(--accent);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 3px 9px;
    font-weight: 500;
  }

  .desc-box {
    background: var(--soft);
    border-radius: 7px;
    padding: 10px 12px;
    font-size: 12px;
    margin-top: 4px;
    line-height: 1.6;
  }

  /* ── Download bar ────────────────────────────────────────────────────────── */
  .download-bar {
    position: sticky;
    bottom: 0;
    z-index: 4;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.08);
    padding: 12px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }

  .asset-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 5px;
  }

  .asset-chip {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    color: var(--mut);
  }

  .dl-btn {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: var(--green);
    color: #fff;
    border: 0;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
    text-decoration: none;
    flex-shrink: 0;
    white-space: nowrap;
  }
  .dl-btn:hover { filter: brightness(0.95); }
</style>
