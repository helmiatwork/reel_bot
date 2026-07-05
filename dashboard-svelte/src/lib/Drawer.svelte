<script>
  import { drawer, closeDrawer } from './stores.js'
  import { api } from './api.js'

  let d = $state(null)
  let frames = $state([])
  let framesLoading = $state(false)

  drawer.subscribe(async (v) => {
    d = v
    frames = []
    if (v?.type === 'source' && v.data?.youtube_url) {
      framesLoading = true
      const res = await api.sourceFrames(v.data.youtube_url)
      frames = res?.frames ?? []
      framesLoading = false
    }
  })
</script>

{#if d}
  <div class="scrim" onclick={closeDrawer} role="presentation"></div>
  <aside class="drawer">
    <span class="x" onclick={closeDrawer} role="button" tabindex="0">✕</span>

    {#if d.type === 'source'}
      {@const s = d.data}
      <h2>{s.title}</h2>
      <div class="mut" style="font-size:12px;margin-bottom:8px">{s.channel || '-'} · {s.id}</div>
      <div class="frames">
        {#if framesLoading}
          <div class="mut" style="font-size:12px;padding:8px 0">Memuat frames…</div>
        {:else if frames.length}
          {#each frames as src}
            <img {src} alt="frame" loading="lazy" style="width:100%;border-radius:4px;object-fit:cover" />
          {/each}
        {:else if s.youtube_url}
          <div class="mut" style="font-size:12px;padding:8px 0">No frames tersimpan untuk video ini.</div>
        {:else}
          <div class="mut" style="font-size:12px;padding:8px 0">youtube_url tidak tersedia di baris ini — frames tidak dapat dimuat. (Lihat blocker note di kode.)</div>
        {/if}
      </div>
      <div class="kv"><span>Views</span><span class="num">{s.viewsLabel}</span></div>
      <div class="kv"><span>Niche</span><span>{s.niche}</span></div>
      <div class="kv"><span>Formula</span><span>{s.formula}</span></div>
      <div class="kv"><span>Durasi / res</span><span>{s.dur} · {s.res}</span></div>
      <div class="kv"><span>Bahasa</span><span>{s.lang}</span></div>
      <div class="kv"><span>Hook</span><span style="text-align:right;max-width:60%">{s.hook}</span></div>
      <div class="kv"><span>Clippable / wajah</span><span>{s.clip ? 'ya' : 'tidak'} / {s.face ? 'ada' : 'no'}</span></div>
      <div class="kv"><span>Status</span><span>{s.status}</span></div>
      {#if s.tags?.length}
        <div class="kv"><span>Tags</span><span style="text-align:right;max-width:60%">{#each s.tags as t}<span class="tag">{t}</span>{/each}</span></div>
      {/if}
      {#if s.sum}<p class="mut" style="font-size:12.5px;margin-top:12px">{s.sum}</p>{/if}

    {:else if d.type === 'agent'}
      {@const a = d.data}
      <h2>{a.name}</h2>
      <div class="meta" style="margin:8px 0">
        {#each a.model as m, i}<span class="m-chip {a.cls[i]}">{m}</span>{/each}
      </div>
      <div class="kv"><span>Peran</span><span style="text-align:right;max-width:62%">{a.role}</span></div>
      <div class="kv"><span>Model</span><span style="text-align:right;max-width:62%">{a.modelId || '-'}</span></div>
      <div class="kv"><span>Trigger</span><span style="text-align:right;max-width:62%">{a.trig}</span></div>
      <p class="mut" style="font-size:12.5px;margin-top:12px">{a.detail}</p>

    {:else if d.type === 'formula'}
      {@const f = d.data}
      <h2>{f.slug}</h2>
      <div class="meta" style="margin:8px 0">
        {#if f.db}<span class="m-chip s-active">sudah di DB</span>{:else}<span class="m-chip s-mod">usulan baru</span>{/if}
        <span class="m-chip m-cheap">{f.face}</span>
      </div>
      <div class="kv"><span>Best for</span><span style="text-align:right;max-width:60%">{f.best}</span></div>
      <h3 style="margin:14px 0 6px;font-size:13px">Struktur</h3>
      <p style="font-size:12.5px"><code style="display:block;padding:10px;line-height:1.6">{f.struct}</code></p>
      <div class="kv"><span>Hook</span><span style="text-align:right;max-width:60%">{f.hook}</span></div>
      <div class="kv"><span>Retensi</span><span style="text-align:right;max-width:60%">{f.ret}</span></div>
      <div class="kv"><span>Contoh</span><span style="text-align:right;max-width:60%">{f.ex}</span></div>

    {:else if d.type === 'piece'}
      {@const p = d.data}
      <h2>{p.title}</h2>
      <div class="mut" style="font-size:12px;margin-bottom:8px">{p.kind} · {p.niche}</div>
      <div class="kv"><span>Status</span><span>{p.status}</span></div>
      <div class="kv"><span>QC</span><span>{p.qc}</span></div>
      <h3 style="margin:14px 0 6px;font-size:13px">Assets</h3>
      {#each p.assets as x}
        <div class="kv"><span>{x.split(' ')[0]}</span><span>{#if x.includes('✓')}<span class="up">✓</span>{:else if x.includes('⏳')}<span class="mut">⏳</span>{:else}<span class="mut">✗</span>{/if}</span></div>
      {/each}
      <p class="mut" style="font-size:12.5px;margin-top:12px">{p.note}</p>
    {/if}
  </aside>
{/if}
