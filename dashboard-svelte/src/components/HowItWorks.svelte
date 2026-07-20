<script>
  import { _ } from 'svelte-i18n'
  import { fade, fly, scale } from 'svelte/transition'
  import { cubicOut } from 'svelte/easing'

  let { open = $bindable(false) } = $props()

  const STEPS = [
    {
      icon: '#i-yt',
      title: 'Ingest',
      body: 'Download source videos from YouTube, TikTok, Instagram, and Xiaohongshu. Cookies are managed per account so you never hit auth walls.',
      brand: true
    },
    {
      icon: '#i-film',
      title: 'Analyze',
      body: 'Frame-by-frame + viral-structure analysis extracts your hook quality, retention curve, structure map, and auto-tags — all stored in the corpus.'
    },
    {
      icon: '#i-search',
      title: 'Discover corpus',
      body: 'Auto-find top-performing competitor videos by niche, pull them in, and analyze them. Your reference library grows without manual hunting.'
    },
    {
      icon: '#i-spark',
      title: 'Studio',
      body: 'Batch-generate ready-to-shoot scripts that clone the winning formula. Track every piece on a Kanban board — idea → script → prep → scheduled → posted.'
    },
    {
      icon: '#i-bot',
      title: 'Prep',
      body: 'Per content piece, gather everything in one place: HD source, clips, chosen BGM, transcript, strategy notes, and the full SEO pack.'
    },
    {
      icon: '#i-film',
      title: 'Rough-cut + captions',
      body: 'Auto-assemble a 9:16 reference draft with burned-in captions and your background music — a preview cut, not the final edit.'
    },
    {
      icon: '#i-expand',
      title: 'Download ZIP → CapCut',
      body: 'One click bundles all assets into a ZIP. Finish the precise edit in CapCut where you have full manual control over every cut.'
    },
    {
      icon: '#i-cal',
      title: 'Schedule (Jadwal Post)',
      body: 'Plan and schedule posts per platform across multiple accounts. Set the calendar once; Reelbot handles the queue.'
    },
    {
      icon: '#i-dollar',
      title: 'Performance',
      body: 'Track views, revenue, and RPM per platform and account over time. See exactly which niches and formats are earning.'
    },
    {
      icon: '#i-spark',
      title: 'Winner-clone',
      body: 'Turn your best-performing videos into fresh variation scripts, dropped back into Studio. The loop repeats — research → produce → publish → measure → double-down.'
    }
  ]

  let step = $state(0)
  let dir = $state(1)   // 1 = forward, -1 = backward
  let visible = $state(true)  // controls transition key

  // focus trap ref
  let panelEl = $state(null)
  let triggerEl = $state(null)

  function close() {
    open = false
    // return focus to opener
    setTimeout(() => triggerEl?.focus(), 50)
  }

  function go(next) {
    if (next === step) return
    dir = next > step ? 1 : -1
    step = next
  }

  function prev() { if (step > 0) go(step - 1) }
  function next() { if (step < STEPS.length - 1) go(step + 1) }

  function onKey(e) {
    if (!open) return
    if (e.key === 'Escape') { close(); return }
    if (e.key === 'ArrowRight') next()
    if (e.key === 'ArrowLeft') prev()
  }

  function trapFocus(e) {
    if (!panelEl) return
    const focusable = panelEl.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.key !== 'Tab') return
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last.focus() }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first.focus() }
    }
  }

  $effect(() => {
    if (open) {
      // store opener reference so we can restore focus
      triggerEl = document.activeElement
      // focus panel on next tick
      setTimeout(() => panelEl?.querySelector('button')?.focus(), 30)
    }
  })
</script>

<svelte:window onkeydown={onKey}/>

{#if open}
  <!-- Backdrop -->
  <div
    class="hiw-backdrop"
    transition:fade={{ duration: 200 }}
    onclick={close}
    aria-hidden="true"
  ></div>

  <!-- Panel -->
  <div
    class="hiw-panel"
    bind:this={panelEl}
    role="dialog"
    aria-modal="true"
    aria-label="How Reelbot works"
    tabindex="-1"
    transition:scale={{ duration: 240, start: 0.94, easing: cubicOut }}
    onkeydown={trapFocus}
  >
    <!-- Header -->
    <div class="hiw-head">
      <div class="hiw-title-row">
        <svg class="ic hiw-logo-icon"><use href="#i-spark"/></svg>
        <span class="hiw-title">How Reelbot works</span>
        <span class="hiw-counter">Step {step + 1} of {STEPS.length}</span>
      </div>
      <button class="hiw-close" onclick={close} aria-label="Close walkthrough">
        <svg class="ic"><use href="#i-x"/></svg>
      </button>
    </div>

    <!-- Progress bar -->
    <div class="hiw-progress-wrap" aria-hidden="true">
      <div class="hiw-progress-bar" style="width:{((step + 1) / STEPS.length) * 100}%"></div>
    </div>

    <!-- Step content — keyed on step so Svelte replaces the node for transitions -->
    <div class="hiw-body">
      {#key step}
        <div
          class="hiw-step-content"
          in:fly={{ x: dir * 40, duration: 240, easing: cubicOut }}
          out:fly={{ x: dir * -40, duration: 200, easing: cubicOut }}
        >
          <div class="hiw-icon-wrap" class:hiw-brand={STEPS[step].brand}>
            <svg class="hiw-step-icon"><use href={STEPS[step].icon}/></svg>
          </div>
          <div class="hiw-step-num">0{step + 1}</div>
          <h2 class="hiw-step-title">{STEPS[step].title}</h2>
          <p class="hiw-step-body">{STEPS[step].body}</p>
        </div>
      {/key}
    </div>

    <!-- Dot nav -->
    <div class="hiw-dots" role="tablist" aria-label="Steps">
      {#each STEPS as _, i}
        <button
          class="hiw-dot"
          class:active={i === step}
          role="tab"
          aria-selected={i === step}
          aria-label="Step {i + 1}"
          onclick={() => go(i)}
        ></button>
      {/each}
    </div>

    <!-- Footer nav -->
    <div class="hiw-foot">
      <button
        class="hiw-btn hiw-btn-ghost"
        onclick={prev}
        disabled={step === 0}
        aria-label="Previous step"
      >← Back</button>

      {#if step < STEPS.length - 1}
        <button class="hiw-btn hiw-btn-primary" onclick={next} aria-label="Next step">
          Next →
        </button>
      {:else}
        <button class="hiw-btn hiw-btn-primary" onclick={close} aria-label="Close walkthrough">
          Got it ✓
        </button>
      {/if}
    </div>
  </div>
{/if}

<style>
  .hiw-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, .55);
    z-index: 100;
    cursor: pointer;
  }

  .hiw-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 101;
    width: min(520px, calc(100vw - 32px));
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    box-shadow: 0 24px 64px rgba(0, 0, 0, .28);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    /* prevent layout jump during slide transitions */
    min-height: 380px;
  }

  /* ── Header ── */
  .hiw-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 20px 14px;
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }

  .hiw-title-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .hiw-logo-icon {
    width: 18px;
    height: 18px;
    color: var(--accent);
  }

  .hiw-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--txt);
  }

  .hiw-counter {
    font-size: 12px;
    color: var(--mut);
    margin-left: 4px;
  }

  .hiw-close {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--mut);
    padding: 4px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color .15s, background .15s;
  }

  .hiw-close:hover {
    color: var(--txt);
    background: var(--soft);
  }

  .hiw-close svg {
    width: 18px;
    height: 18px;
  }

  /* ── Progress bar ── */
  .hiw-progress-wrap {
    height: 3px;
    background: var(--line);
    flex-shrink: 0;
  }

  .hiw-progress-bar {
    height: 100%;
    background: var(--accent);
    transition: width .25s cubic-bezier(0.4, 0, 0.2, 1);
  }

  /* ── Body (overflow hidden so slides clip) ── */
  .hiw-body {
    flex: 1;
    position: relative;
    overflow: hidden;
    padding: 32px 28px 20px;
    /* fixed height so panel doesn't jump between steps */
    min-height: 230px;
  }

  .hiw-step-content {
    position: absolute;
    inset: 32px 28px 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .hiw-icon-wrap {
    width: 56px;
    height: 56px;
    border-radius: 16px;
    background: rgba(64, 81, 137, .1);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 12px;
    flex-shrink: 0;
  }

  /* brand icons (platform logos) get a neutral bg so their self-color shows */
  .hiw-icon-wrap.hiw-brand {
    background: var(--soft);
  }

  .hiw-step-icon {
    width: 28px;
    height: 28px;
    color: var(--accent);
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  /* brand symbols use fill:currentColor internally — override stroke */
  .hiw-brand .hiw-step-icon {
    stroke: none;
    fill: currentColor;
    color: var(--accent);
  }

  .hiw-step-num {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .08em;
    color: var(--accent);
    text-transform: uppercase;
    margin-bottom: 6px;
  }

  .hiw-step-title {
    font-size: 20px;
    font-weight: 700;
    margin: 0 0 10px;
    color: var(--txt);
    line-height: 1.2;
  }

  .hiw-step-body {
    font-size: 14px;
    line-height: 1.65;
    color: var(--mut);
    margin: 0;
    max-width: 380px;
  }

  /* ── Dots ── */
  .hiw-dots {
    display: flex;
    justify-content: center;
    gap: 7px;
    padding: 0 20px 16px;
    flex-shrink: 0;
  }

  .hiw-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    border: none;
    background: var(--line);
    cursor: pointer;
    padding: 0;
    transition: background .2s, transform .2s;
  }

  .hiw-dot.active {
    background: var(--accent);
    transform: scale(1.35);
  }

  .hiw-dot:hover:not(.active) {
    background: var(--mut);
  }

  /* ── Footer ── */
  .hiw-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px 18px;
    border-top: 1px solid var(--line);
    flex-shrink: 0;
  }

  .hiw-btn {
    border: none;
    border-radius: 9px;
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: background .15s, opacity .15s;
  }

  .hiw-btn:disabled {
    opacity: .35;
    cursor: default;
  }

  .hiw-btn-ghost {
    background: var(--soft);
    color: var(--txt);
    border: 1px solid var(--line);
  }

  .hiw-btn-ghost:hover:not(:disabled) {
    background: var(--line);
  }

  .hiw-btn-primary {
    background: var(--accent);
    color: #fff;
  }

  .hiw-btn-primary:hover {
    opacity: .88;
  }

  /* ── Responsive ── */
  @media (max-width: 560px) {
    .hiw-body {
      padding: 24px 18px 16px;
      min-height: 200px;
    }

    .hiw-step-content {
      inset: 24px 18px 16px;
    }

    .hiw-step-title {
      font-size: 17px;
    }

    .hiw-step-body {
      font-size: 13px;
    }

    .hiw-head {
      padding: 14px 16px 12px;
    }

    .hiw-foot {
      padding: 12px 16px 16px;
    }
  }
</style>
