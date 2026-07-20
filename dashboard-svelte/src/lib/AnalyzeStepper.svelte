<script>
  import { _ } from 'svelte-i18n'
  let { logs = [] } = $props()

  let elapsed = $derived(logs.length > 0 ? Math.max(...logs.map(e => e.t)).toFixed(1) : '0.0')

  let stepList = $derived.by(() => {
    const msgs = logs.map(e => e.msg)
    const hasError = msgs.some(m => m.includes('✗'))

    let frameCount = null, segmentCount = null, batchInfo = null
    for (const m of msgs) {
      const fc = m.match(/(\d+)\s*frame/i)
      if (fc) frameCount = fc[1]
      const sc = m.match(/\((\d+)\s*segment/i)
      if (sc) segmentCount = sc[1]
      if (/analisa frame/i.test(m)) {
        const bm = m.match(/analisa frame \d+-(\d+\/\d+)\s*\(([^)]+)\)/i)
        if (bm) batchInfo = `${bm[1]} · ${bm[2]}`
      }
    }

    const DEFS = [
      { label: $_('analyzeStepper.download_video'),
        match: m => /download video/i.test(m) || /terunduh/i.test(m),
        done: m => new RegExp($_('analyzeStepper.downloaded'), 'i').test(m),
        sub: () => null },
      { label: $_('analyzeStepper.extract_frames'),
        match: m => /ekstrak.*frame/i.test(m) || /diekstrak/i.test(m),
        done: m => new RegExp($_('analyzeStepper.extracted'), 'i').test(m),
        sub: () => frameCount ? $_('analyzeStepper.frames', { values: { count: frameCount } }) : null },
      { label: $_('analyzeStepper.transcript'),
        match: m => /transkrip/i.test(m),
        done: m => new RegExp($_('analyzeStepper.transcript_taken'), 'i').test(m),
        sub: () => segmentCount ? $_('analyzeStepper.segments', { values: { count: segmentCount } }) : null },
      { label: $_('analyzeStepper.analyze_frames'),
        match: m => /analisa frame/i.test(m),
        done: () => false,
        sub: () => batchInfo },
      { label: $_('analyzeStepper.synthesize_json'),
        match: m => /sintesis/i.test(m),
        done: () => false,
        sub: () => $_('analyzeStepper.sonnet_model') },
      { label: $_('analyzeStepper.save_database'),
        match: m => /simpan/i.test(m) || /database/i.test(m),
        done: m => new RegExp($_('analyzeStepper.saved'), 'i').test(m),
        sub: () => null },
    ]

    let lastIdx = -1
    for (let i = 0; i < DEFS.length; i++) {
      if (msgs.some(m => DEFS[i].match(m))) lastIdx = i
    }

    return DEFS.map((def, i) => {
      const stepMsgs = msgs.filter(m => def.match(m))
      const hasMatch = stepMsgs.length > 0
      const hasDone = stepMsgs.some(m => def.done(m))
      const laterAppeared = lastIdx > i

      let status = 'pending'
      if (laterAppeared || hasDone) status = 'done'
      else if (hasMatch) status = hasError ? 'error' : 'running'

      return { label: def.label, status, sub: hasMatch ? def.sub() : null }
    })
  })
</script>

<div class="stepper-panel">
  <div class="stepper-hd">
    <span class="stepper-title">{$_('analyzeStepper.title')}</span>
    <span class="stepper-elapsed">{elapsed}s</span>
  </div>
  {#each stepList as step}
    <div class="step-row">
      {#if step.status === 'done'}
        <svg class="step-ic" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="8" fill="#4ade80" fill-opacity="0.15" stroke="#4ade80" stroke-width="1.5"/>
          <polyline points="6,10 9,13 14,7" stroke="#4ade80" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      {:else if step.status === 'running'}
        <span class="step-spinner" role="status" aria-label={$_('analyzeStepper.running_label')}></span>
      {:else if step.status === 'error'}
        <svg class="step-ic" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="8" fill="#f87171" fill-opacity="0.15" stroke="#f87171" stroke-width="1.5"/>
          <line x1="7" y1="7" x2="13" y2="13" stroke="#f87171" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="13" y1="7" x2="7" y2="13" stroke="#f87171" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      {:else}
        <svg class="step-ic" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="8" stroke="#5a5e68" stroke-width="1.5"/>
        </svg>
      {/if}
      <span class="step-label step-{step.status}">{step.label}</span>
      {#if step.sub}
        <span class="step-sub">{step.sub}</span>
      {/if}
    </div>
  {/each}
</div>

<style>
  .stepper-panel {
    background: #1e1f22;
    border-radius: 12px;
    padding: 20px 22px;
  }

  .stepper-hd {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2px;
  }

  .stepper-title {
    color: #e6e7ea;
    font-size: 15px;
    font-weight: 500;
  }

  .stepper-elapsed {
    font-family: 'Monaco', 'Courier New', monospace;
    color: #7a7f8a;
    font-size: 12px;
  }

  .step-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 0;
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 13.5px;
  }

  .step-ic {
    flex-shrink: 0;
  }

  .step-label {
    flex: 1;
  }

  .step-pending { color: #5a5e68; }
  .step-running { color: #e6e7ea; }
  .step-done    { color: #c9cbd1; }
  .step-error   { color: #f87171; }

  .step-sub {
    font-size: 12.5px;
    color: #7a7f8a;
  }

  .step-spinner {
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 2px solid rgba(96, 165, 250, 0.25);
    border-top-color: #60a5fa;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
