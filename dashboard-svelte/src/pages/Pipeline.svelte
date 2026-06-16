<script>
  import { onMount, onDestroy } from 'svelte'
  import { api } from '../lib/api.js'
  import { PIECES, KANBAN_COLS } from '../lib/data.js'
  import { openDrawer } from '../lib/stores.js'

  const pieces = Object.entries(PIECES).map(([k, v]) => ({ key: k, ...v }))
  const byCol = (c) => pieces.filter((p) => p.col === c)

  // ---- live runs ----
  let runs = $state([])
  let selected = $state(null) // run detail
  let artifact = $state(null) // produced script/EDL artifact
  let artLoading = $state(false)
  let timer

  async function loadRuns() {
    const r = await api.runs(15)
    if (r && r.runs) runs = r.runs
  }
  async function openRun(id) {
    selected = await api.run(id)
    artifact = null
  }
  async function loadArtifact() {
    if (!selected) return
    artLoading = true
    artifact = await api.artifact(selected.run_id)
    artLoading = false
  }

  // ---- trigger ----
  let mode = $state('discover') // 'discover' | 'url'
  let niche = $state('')
  let topic = $state('')
  let url = $state('')
  let busy = $state(false)
  let msg = $state('')

  async function trigger() {
    busy = true
    msg = ''
    let res
    if (mode === 'discover') {
      if (!niche.trim()) { msg = 'Isi niche dulu.'; busy = false; return }
      res = await api.discover(niche.trim(), topic.trim())
    } else {
      if (!url.trim()) { msg = 'Isi URL dulu.'; busy = false; return }
      res = await api.research(url.trim(), topic.trim())
    }
    busy = false
    if (res && res.run_id) {
      msg = `Job jalan — run ${res.run_id.slice(0, 8)}…`
      await loadRuns()
      openRun(res.run_id)
    } else {
      msg = 'Gagal start job (cek pipeline-api).'
    }
  }

  const STEP_ORDER = ['discover', 'download', 'analyze', 'audio', 'script', 'footage', 'music', 'assemble', 'save']

  onMount(() => {
    loadRuns()
    timer = setInterval(() => {
      loadRuns()
      if (selected && selected.status === 'running') openRun(selected.run_id)
    }, 5000)
  })
  onDestroy(() => clearInterval(timer))
</script>

<div class="top">
  <div><h1>Pipeline</h1><div class="sub">content_pieces (mock) + live runs dari pipeline-api</div></div>
  <div class="pill">{runs.length} run</div>
</div>

<!-- trigger -->
<div class="card" style="margin-bottom:16px">
  <h3>Trigger pipeline</h3>
  <div class="filters" style="margin-bottom:10px">
    <select bind:value={mode}>
      <option value="discover">Discover (AI cari video dari niche)</option>
      <option value="url">URL (analisa video spesifik)</option>
    </select>
  </div>
  {#if mode === 'discover'}
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <input class="input" style="max-width:240px" placeholder="niche, mis. kuliner viral Indonesia" bind:value={niche} />
      <input class="input" style="max-width:240px" placeholder="topic (opsional)" bind:value={topic} />
      <button class="btn" disabled={busy} onclick={trigger}>{busy ? '…' : 'Cari + produksi'}</button>
    </div>
  {:else}
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <input class="input" style="max-width:320px" placeholder="https://youtube.com/shorts/…" bind:value={url} />
      <input class="input" style="max-width:200px" placeholder="topic (opsional)" bind:value={topic} />
      <button class="btn" disabled={busy} onclick={trigger}>{busy ? '…' : 'Riset video'}</button>
    </div>
  {/if}
  {#if msg}<div class="mut" style="font-size:12px;margin-top:8px">{msg}</div>{/if}
</div>

<!-- live runs + detail -->
<div class="grid2" style="margin-bottom:16px">
  <div class="card">
    <h3>Run terbaru</h3>
    <table>
      <thead><tr><th>Topic / URL</th><th>Step</th><th>Status</th></tr></thead>
      <tbody>
        {#each runs as r}
          <tr onclick={() => openRun(r.run_id)}>
            <td>{r.topic || r.youtube_url || r.run_id.slice(0, 8)}</td>
            <td class="mut">{r.current_step || '-'}</td>
            <td>
              <span class="chip {r.status === 'done' ? 'c-used' : r.status === 'error' ? '' : 'c-analyzed'}"
                    style={r.status === 'error' ? 'background:rgba(248,113,113,.15);color:#f87171' : ''}>{r.status}</span>
            </td>
          </tr>
        {/each}
        {#if !runs.length}<tr><td colspan="3" class="mut">Belum ada run. Trigger di atas.</td></tr>{/if}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h3>Detail run</h3>
    {#if selected}
      <div class="kv" style="border:0;padding:4px 0"><span>{selected.topic || selected.youtube_url || ''}</span></div>

      {#if selected.run?.error || selected.error}
        <div class="note" style="background:rgba(248,113,113,.08);border-color:rgba(248,113,113,.3);color:#fca5a5;margin-top:6px">
          ✖ {selected.run?.error || selected.error}
        </div>
      {/if}

      <div class="steps">
        {#each STEP_ORDER as st}
          {@const s = (selected.steps || []).find((x) => x.step === st)}
          <div class="step {s ? s.status : 'pending'}">
            <span class="dot"></span> {st}
            <span class="st">{s ? s.status : '—'}</span>
          </div>
        {/each}
      </div>

      {#each (selected.steps || []).filter((s) => s.status === 'error' && s.error) as e}
        <div class="mut" style="font-size:11.5px;margin-top:6px"><span class="down">{e.step}:</span> {e.error}</div>
      {/each}

      {#if selected.discover?.picks?.length || Array.isArray(selected.discover)}
        {@const picks = selected.discover.picks || selected.discover}
        <h3 style="margin:14px 0 6px;font-size:13px">Kandidat discover</h3>
        {#each picks.slice(0, 5) as c, i}
          <div class="kv"><span>#{i + 1} {c.title || c.video_id || c.url || '-'}</span><span class="num mut">{c.score ?? c.rank ?? ''}</span></div>
        {/each}
      {/if}

      {#if selected.audio}
        <h3 style="margin:14px 0 6px;font-size:13px">Audio</h3>
        {#if selected.audio.loudness_lufs ?? selected.audio.lufs}<div class="kv"><span>Loudness</span><span class="num">{selected.audio.loudness_lufs ?? selected.audio.lufs} LUFS</span></div>{/if}
        {#if selected.audio.peak_db ?? selected.audio.peak}<div class="kv"><span>Peak</span><span class="num">{selected.audio.peak_db ?? selected.audio.peak} dB</span></div>{/if}
        {#if selected.audio.onsets || selected.audio.silence_count}<div class="kv"><span>Onsets / silence</span><span class="num">{selected.audio.onsets ?? '-'} / {selected.audio.silence_count ?? '-'}</span></div>{/if}
        {#if selected.audio.transcript}<p class="mut" style="font-size:12px;margin-top:6px">{String(selected.audio.transcript).slice(0, 240)}…</p>{/if}
      {/if}

      {#if selected.script}
        <h3 style="margin:14px 0 6px;font-size:13px">Script</h3>
        <div class="kv"><span>Judul</span><span style="text-align:right;max-width:62%">{selected.script.title || '-'}</span></div>
        <div class="kv"><span>Formula</span><span>{selected.script.formula || '-'}</span></div>
        <div class="kv"><span>Hook</span><span style="text-align:right;max-width:62%">{selected.script.hook || '-'}</span></div>
        <div class="kv"><span>Durasi</span><span>{selected.script.target_duration_sec || '-'}s</span></div>
      {/if}

      {#if selected.save?.output_file || selected.status === 'done'}
        <h3 style="margin:14px 0 6px;font-size:13px">Artifact hasil</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn" onclick={loadArtifact} disabled={artLoading}>{artLoading ? '…' : 'Lihat output'}</button>
          <a class="btn" style="background:#1b2433;color:var(--txt)" href={api.artifactDownloadUrl(selected.run_id)} download>⬇ Download JSON</a>
        </div>
        {#if artifact?.content?.beats || artifact?.content?.script?.beats}
          {@const beats = artifact.content.beats || artifact.content.script.beats}
          <div class="steps" style="margin-top:8px">
            {#each beats.slice(0, 8) as b, i}
              <div class="step done"><span class="dot"></span> {b.t ?? i}s — {(b.visual || b.vo || b.caption || '').slice(0, 60)}</div>
            {/each}
          </div>
        {/if}
        {#if artifact?.summary}
          <pre style="white-space:pre-wrap;font-size:11.5px;background:#0c1320;border:1px solid var(--line);border-radius:8px;padding:10px;margin-top:8px;max-height:220px;overflow:auto">{artifact.summary}</pre>
        {/if}
      {/if}
    {:else}
      <p class="mut" style="font-size:12.5px">Klik salah satu run buat lihat step + script + artifact.</p>
    {/if}
  </div>
</div>

<!-- kanban (mock) -->
<div class="card">
  <h3>Board content_pieces <span class="mut">— mock (belum ada endpoint)</span></h3>
  <div class="kanban">
    {#each KANBAN_COLS as col}
      <div class="col">
        <div class="h">{col} <span>{byCol(col).length}</span></div>
        {#each byCol(col) as p}
          <div class="ticket" onclick={() => openDrawer('piece', p)}>
            {p.title}
            <div class="m">{p.kind} · {col === 'QC' && p.fail ? '' : ''}
              {#if p.qc && p.qc.startsWith('PASS')}<span class="up">{p.qc}</span>
              {:else if p.fail}<span class="down">FAIL</span>
              {:else}{p.niche}{/if}
            </div>
            <div class="bar"><i style="width:{p.pct}%{p.fail ? ';background:linear-gradient(90deg,#f87171,#fbbf24)' : ''}"></i></div>
          </div>
        {/each}
      </div>
    {/each}
  </div>
</div>
