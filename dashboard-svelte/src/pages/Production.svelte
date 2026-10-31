<script>
  import { onDestroy } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'
  import { page, atmItemId, pushToast } from '../lib/stores.js'

  const STATUSES = ['idea', 'blueprint', 'shoot', 'edit', 'review', 'ready', 'scheduled', 'posted', 'monitored']
  const TABS = ['blueprint', 'shots', 'narration', 'audio', 'thumbnail', 'upload', 'evaluation']

  let itemId = $state(null)
  atmItemId.subscribe((v) => (itemId = v))

  let item = $state(null)
  let notFound = $state(false)
  let tab = $state('blueprint')
  let msg = $state('')
  let needAnalysis = $state(false)
  let publishedUrl = $state('')
  let scheduledAt = $state('')
  let estimate = $state(null)
  let voiceFiles = $state({}) // beat -> {song_id, url}
  let voiceBusy = $state(false)
  let timer = null

  let bp = $derived(item?.blueprint || null)
  let building = $derived(item?.blueprint_status === 'building')
  let beats = $derived(bp?.narration?.beats || [])

  function detail(r) {
    const d = r.data?.detail
    return typeof d === 'string' ? d : ''
  }

  async function load(id = itemId) {
    if (!id) { item = null; return }
    const r = await api.atmItem(id)
    if (r.status === 404) { notFound = true; item = null; return }
    if (!r.ok) return
    notFound = false
    item = r.data
    publishedUrl = item.published_url || ''
    scheduledAt = item.scheduled_at ? item.scheduled_at.slice(0, 16) : ''
  }

  $effect(() => {
    itemId // reload when another card is opened
    estimate = null
    voiceFiles = {}
    msg = ''
    needAnalysis = false
    load(itemId)
  })

  // poll every 3 s while a blueprint is being built
  $effect(() => {
    if (building && !timer) timer = setInterval(() => load(), 3000)
    if (!building && timer) { clearInterval(timer); timer = null }
  })
  onDestroy(() => timer && clearInterval(timer))

  async function patch(body) {
    const r = await api.atmItemPatch(item.id, body)
    if (r.ok) await load()
    else msg = detail(r) || $_('atm.save_error')
    return r.ok
  }

  async function buildBlueprint(section) {
    msg = ''
    needAnalysis = false
    const r = await api.atmBlueprint(item.id, section)
    if (r.status === 409) { needAnalysis = true; msg = detail(r); return }
    if (!r.ok) { msg = detail(r) || $_('atm.save_error'); return }
    await load()
  }

  async function analyzeReference() {
    const r = await api.analyzeClaudeAsync(item.reference_url)
    if (r) pushToast('info', $_('atm.analyze_started'), item.reference_url.slice(0, 60))
    else msg = $_('atm.save_error')
  }

  async function savePublished() {
    if (await patch({ published_url: publishedUrl.trim() })) pushToast('success', $_('atm.saved'))
  }

  async function saveSchedule() {
    await patch({ scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null })
  }

  async function loadEstimate() {
    const r = await api.atmVoiceEstimate(item.id)
    if (r.ok) estimate = r.data
    else msg = detail(r)
  }

  async function generateVoice(beat) {
    voiceBusy = true
    msg = ''
    const r = await api.atmVoice(item.id, beat)
    voiceBusy = false
    if (!r.ok) { msg = detail(r) || $_('atm.save_error'); return }
    for (const f of r.data.files) voiceFiles[f.beat] = { song_id: f.song_id, url: f.url + '?t=' + Date.now() }
  }

  function copy(text) {
    navigator.clipboard?.writeText(text)
    pushToast('success', $_('atm.copied'))
  }

  async function removeItem() {
    if (!confirm($_('atm.confirm_delete'))) return
    const r = await api.atmItemDelete(item.id)
    if (r.ok) { atmItemId.set(null); page.set('plan') }
  }
</script>

{#snippet regen(section)}
  <button class="btn-ghost sm" disabled={building} onclick={() => buildBlueprint(section)}>{$_('atm.regenerate')}</button>
{/snippet}

<div class="prod">
  {#if !itemId || notFound}
    <div class="empty">
      <div>{$_('atm.no_item')}</div>
      <button class="btn-primary" onclick={() => page.set('plan')}>{$_('atm.go_plan')}</button>
    </div>
  {:else if !item}
    <div class="mut">{$_('atm.loading')}</div>
  {:else}
    <div class="head panel">
      <div class="head-top">
        <h1>{item.title}</h1>
        {#if item.niche}<span class="niche-badge">{item.niche}</span>{/if}
        <span class="niche-badge">{item.format} · {$_('atm.voice_' + item.voice_mode)}</span>
        <div style="flex:1"></div>
        <button class="btn-danger sm" onclick={removeItem}>{$_('atm.delete')}</button>
      </div>
      <div class="head-row">
        <label class="lbl">{$_('atm.h_status')}
          <select class="inp" value={item.status} onchange={(e) => patch({ status: e.currentTarget.value })}>
            {#each STATUSES as s}<option value={s}>{$_('atm.status_' + s)}</option>{/each}
          </select>
        </label>
        <label class="lbl">{$_('atm.h_scheduled')}
          <input class="inp" type="datetime-local" bind:value={scheduledAt} onchange={saveSchedule} />
        </label>
        <label class="lbl grow">{$_('atm.h_published')}
          <span class="inline">
            <input class="inp" placeholder="https://youtube.com/..." bind:value={publishedUrl} />
            <button class="btn-ghost" disabled={!publishedUrl.trim()} onclick={savePublished}>{$_('atm.save')}</button>
          </span>
        </label>
      </div>
      {#if item.reference_url}<div class="mut small">{$_('atm.f_reference')}: {item.reference_url}</div>{/if}
    </div>

    <div class="tabs">
      {#each TABS as t}
        <button class="tab" class:on={tab === t} onclick={() => (tab = t)}>{$_('atm.tab_' + t)}</button>
      {/each}
    </div>

    {#if msg}<div class="err">{msg}</div>{/if}
    {#if needAnalysis}
      <button class="btn-primary" onclick={analyzeReference}>{$_('atm.analyze_first')}</button>
    {/if}

    {#if tab === 'blueprint'}
      <div class="panel">
        <div class="row">
          <button class="btn-primary" disabled={building} onclick={() => buildBlueprint()}>
            {building ? $_('atm.building') : bp ? $_('atm.rebuild_blueprint') : $_('atm.build_blueprint')}
          </button>
          {#if item.blueprint_version}<span class="mut">v{item.blueprint_version}</span>{/if}
          {#if item.blueprint_status === 'error'}<span class="err">{item.blueprint_error}</span>{/if}
        </div>
        {#if bp}
          <div class="sec">
            <div class="sec-head"><h4>{$_('atm.sec_atm')}</h4>{@render regen('atm')}</div>
            {#each [['tiru', 'atm.imitate'], ['modifikasi', 'atm.modify'], ['checklist_orisinalitas', 'atm.originality']] as [k, label]}
              <div class="lbl-s">{$_(label)}</div>
              <ul>{#each bp.atm?.[k] || [] as x}<li>{x}</li>{/each}</ul>
            {/each}
          </div>
          <div class="sec">
            <div class="sec-head"><h4>{$_('atm.sec_titles')}</h4>{@render regen('titles')}</div>
            <ol>{#each bp.titles || [] as t}<li>{t} <button class="link" onclick={() => copy(t)}>{$_('atm.copy')}</button></li>{/each}</ol>
          </div>
          <div class="sec">
            <div class="sec-head"><h4>{$_('atm.sec_hook')}</h4>{@render regen('hook')}</div>
            <p><b>{bp.hook?.line}</b></p>
            <p class="mut">{bp.hook?.visual}</p>
          </div>
        {/if}
      </div>

    {:else if tab === 'shots'}
      <div class="panel">
        {#if bp}
          <div class="sec-head"><h4>{$_('atm.tab_shots')}</h4>{@render regen('shots')}</div>
          <table class="tbl">
            <thead><tr><th>#</th><th>{$_('atm.c_dur')}</th><th>{$_('atm.c_record')}</th><th>{$_('atm.c_framing')}</th><th>{$_('atm.c_text')}</th><th>{$_('atm.c_transition')}</th></tr></thead>
            <tbody>
              {#each bp.shots || [] as s, i}
                <tr><td>{s.n ?? i + 1}</td><td>{s.duration_s}s</td><td>{s.record}</td><td>{[s.framing, s.camera].filter(Boolean).join(' · ')}</td><td>{s.on_screen_text}</td><td>{s.transition}</td></tr>
              {/each}
            </tbody>
          </table>
          <div class="sec-head"><h4>{$_('atm.sec_capcut')}</h4>{@render regen('capcut_steps')}</div>
          <ol>{#each bp.capcut_steps || [] as st}<li>{st}</li>{/each}</ol>
        {:else}<div class="mut">{$_('atm.no_blueprint')}</div>{/if}
      </div>

    {:else if tab === 'narration'}
      <div class="panel">
        {#if bp}
          <div class="sec-head"><h4>{$_('atm.tab_narration')}</h4>{@render regen('narration')}</div>
          {#if item.voice_mode === 'ai'}
            <div class="row">
              <button class="btn-ghost" onclick={loadEstimate}>{$_('atm.estimate')}</button>
              {#if estimate}
                <span class="mut">{$_('atm.estimate_text', { values: { chars: estimate.chars, beats: estimate.beats, provider: estimate.provider } })}</span>
              {/if}
              <button class="btn-primary" disabled={voiceBusy || !estimate} onclick={() => generateVoice()}>{$_('atm.voice_all')}</button>
            </div>
            {#if !estimate}<div class="mut small">{$_('atm.estimate_first')}</div>{/if}
          {/if}
          {#each beats as b, i}
            <div class="beat">
              <div class="beat-t">{b.t} <span class="mut">#{i + 1}</span></div>
              <div class:tele={item.voice_mode === 'self'}>{b.vo}</div>
              {#if b.note}<div class="mut small">{b.note}</div>{/if}
              {#if item.voice_mode === 'ai'}
                <div class="row">
                  <button class="btn-ghost sm" disabled={voiceBusy || !estimate} onclick={() => generateVoice(i + 1)}>
                    {voiceFiles[i + 1] ? $_('atm.voice_redo') : $_('atm.voice_make')}
                  </button>
                  {#if voiceFiles[i + 1]}<audio controls src={voiceFiles[i + 1].url}></audio>{/if}
                </div>
              {/if}
            </div>
          {/each}
          {#if item.voice_mode === 'self'}
            <div class="sec-head"><h4>{$_('atm.sec_rec_tips')}</h4>{@render regen('recording_tips')}</div>
            <ul>{#each bp.recording_tips || [] as t}<li>{t}</li>{/each}</ul>
          {/if}
        {:else}<div class="mut">{$_('atm.no_blueprint')}</div>{/if}
      </div>

    {:else if tab === 'audio'}
      <div class="panel">
        {#if bp}
          <div class="sec-head"><h4>{$_('atm.tab_audio')}</h4>{@render regen('audio')}</div>
          <p>{$_('atm.bgm')}: {bp.audio?.bgm_song_id ? '#' + bp.audio.bgm_song_id : '-'} <span class="mut">{bp.audio?.bgm_reason}</span></p>
          <div class="lbl-s">SFX</div>
          <ul>{#each bp.audio?.sfx || [] as x}<li>{x.moment}: {x.sfx}</li>{/each}</ul>
          <div class="sec-head"><h4>{$_('atm.sec_assets')}</h4>{@render regen('assets')}</div>
          <div class="lbl-s">{$_('atm.assets_have')}</div>
          <ul>{#each bp.assets?.have || [] as x}<li>{x.label}{x.song_id ? ' (#' + x.song_id + ')' : ''}</li>{/each}</ul>
          <div class="lbl-s">{$_('atm.assets_need')}</div>
          <ul>{#each bp.assets?.need || [] as x}<li>{x}</li>{/each}</ul>
        {:else}<div class="mut">{$_('atm.no_blueprint')}</div>{/if}
      </div>

    {:else if tab === 'thumbnail'}
      <div class="panel">
        {#if bp}
          <div class="sec-head"><h4>{$_('atm.tab_thumbnail')}</h4>{@render regen('thumbnail')}</div>
          {#each bp.thumbnail?.concepts || [] as c, i}
            <div class="concept">
              <b>{$_('atm.concept')} {String.fromCharCode(65 + i)}</b>
              <p>{c.prompt} <button class="link" onclick={() => copy(c.prompt)}>{$_('atm.copy')}</button></p>
              <p>{$_('atm.overlay')}: <b>{c.overlay_text}</b> <button class="link" onclick={() => copy(c.overlay_text)}>{$_('atm.copy')}</button></p>
              <p class="mut">{c.why_ctr}</p>
            </div>
          {/each}
          <ul>{#each bp.thumbnail?.rules || [] as r}<li>{r}</li>{/each}</ul>
        {:else}<div class="mut">{$_('atm.no_blueprint')}</div>{/if}
      </div>

    {:else if tab === 'upload'}
      <div class="panel">
        {#if bp?.upload}
          <div class="sec-head"><h4>{$_('atm.tab_upload')}</h4>{@render regen('upload')}</div>
          {#each [['description', bp.upload.description], ['tags', (bp.upload.tags || []).join(', ')], ['hashtags', (bp.upload.hashtags || []).join(' ')], ['pinned_comment', bp.upload.pinned_comment], ['playlist', bp.upload.playlist], ['end_screen', bp.upload.end_screen]] as [k, v]}
            <div class="lbl-s">{$_('atm.u_' + k)} <button class="link" onclick={() => copy(v || '')}>{$_('atm.copy')}</button></div>
            <p class="pre">{v || '-'}</p>
          {/each}
          <div class="lbl-s">{$_('atm.u_checklist')}</div>
          <ul>{#each bp.upload.checklist || [] as x}<li>{x}</li>{/each}</ul>
        {:else}<div class="mut">{$_('atm.no_blueprint')}</div>{/if}
      </div>

    {:else}
      <div class="panel"><div class="mut">{$_('atm.eval_soon')}</div></div>
    {/if}
  {/if}
</div>

<style>
  .prod { padding: 0 2px 32px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
  .head-top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .head-top h1 { font-size: 20px; margin: 0; }
  .head-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
  .lbl { display: flex; flex-direction: column; gap: 3px; font-size: 11.5px; color: var(--mut); }
  .lbl.grow { flex: 1; min-width: 260px; }
  .inline { display: flex; gap: 6px; }
  .inp { background: var(--soft); border: 1px solid var(--line); border-radius: 7px; padding: 7px 10px; color: var(--txt); font-size: 13px; outline: none; flex: 1; }
  .inp:focus { border-color: var(--accent); }
  .niche-badge { background: rgba(99,102,241,.15); color: var(--accent); font-size: 11px; border-radius: 4px; padding: 2px 7px; }
  .tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 12px; }
  .tab { background: transparent; border: 1px solid var(--line); color: var(--mut); border-radius: 16px; padding: 5px 14px; font-size: 12.5px; cursor: pointer; }
  .tab.on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 6px 0; }
  .sec { margin-top: 16px; }
  .sec-head { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; }
  .sec-head h4 { margin: 0; font-size: 14px; }
  .lbl-s { font-size: 11.5px; color: var(--mut); margin-top: 8px; text-transform: uppercase; letter-spacing: .04em; }
  ul, ol { margin: 4px 0 4px 18px; padding: 0; font-size: 13px; line-height: 1.6; }
  p { margin: 4px 0; font-size: 13px; line-height: 1.55; }
  .pre { white-space: pre-wrap; word-break: break-word; }
  .tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 8px; }
  .tbl th, .tbl td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
  .beat { border-bottom: 1px solid var(--line); padding: 10px 0; }
  .beat-t { font-size: 11.5px; color: var(--accent); font-weight: 600; margin-bottom: 3px; }
  .tele { font-size: 20px; line-height: 1.6; }
  .concept { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; margin-top: 8px; }
  .btn-primary { background: var(--accent); color: #fff; border: none; border-radius: 7px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .btn-primary:disabled { opacity: .45; cursor: default; }
  .btn-ghost { background: transparent; border: 1px solid var(--line); color: var(--txt); border-radius: 7px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .btn-ghost:disabled { opacity: .45; cursor: default; }
  .btn-danger { background: transparent; border: 1px solid var(--red, #f87171); color: var(--red, #f87171); border-radius: 7px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .sm { padding: 3px 10px; font-size: 12px; }
  .link { background: none; border: none; color: var(--accent); font-size: 11.5px; cursor: pointer; padding: 0 4px; }
  .err { color: var(--red, #f87171); font-size: 12.5px; margin: 6px 0; }
  .mut { color: var(--mut); font-size: 12.5px; }
  .small { font-size: 11px; }
  .empty { text-align: center; padding: 60px 20px; display: flex; flex-direction: column; align-items: center; gap: 12px; color: var(--mut); }
</style>
