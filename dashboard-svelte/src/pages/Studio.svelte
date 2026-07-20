<script>
  import { onDestroy } from 'svelte'
  import { _ } from 'svelte-i18n'
  import { api } from '../lib/api.js'

  const STAGES = ['idea', 'script', 'prep', 'scheduled', 'posted']
  const STAGE_LABELS = {
    idea: 'Idea',
    script: 'Script',
    prep: 'Prep',
    scheduled: 'Scheduled',
    posted: 'Posted'
  }

  // ── Board state ───────────────────────────────────────────────────────────────
  let board = $state({ idea: [], script: [], prep: [], scheduled: [], posted: [] })
  let boardError = $state('')
  let boardLoading = $state(false)

  async function loadBoard() {
    boardLoading = true
    boardError = ''
    const r = await api.studioBoard()
    boardLoading = false
    if (!r) { boardError = $_('studio.board_load_error'); return }
    board = r
  }

  // ── Batch generate form ───────────────────────────────────────────────────────
  let batchNiche = $state('')
  let batchTopic = $state('')
  let batchCount = $state(10)
  let batchBusy  = $state(false)
  let batchError = $state('')
  let batchProgress = $state(null)   // { status, done, total, created_ids }
  let batchTimer = null

  function stopBatchPoll() {
    if (batchTimer) { clearInterval(batchTimer); batchTimer = null }
  }

  async function pollBatch(run_id) {
    const r = await api.generateBatchStatus(run_id)
    if (!r) return
    batchProgress = r
    if (r.status === 'done' || r.status === 'error') {
      stopBatchPoll()
      batchBusy = false
      if (r.status === 'done') loadBoard()
    }
  }

  async function startBatch() {
    if (!batchNiche.trim()) return
    stopBatchPoll()
    batchBusy = true
    batchError = ''
    batchProgress = null
    const r = await api.generateBatch(batchNiche.trim(), batchTopic.trim(), Number(batchCount))
    if (!r || !r.run_id) {
      batchBusy = false
      batchError = r?.detail || r?.error || 'Failed to start — is the backend running?'
      return
    }
    batchTimer = setInterval(() => pollBatch(r.run_id), 8000)
    pollBatch(r.run_id)
  }

  // ── Card modal ────────────────────────────────────────────────────────────────
  let modal = $state(null)      // null | { item, editTitle, editScript, saving, deleting }
  let modalLoading = $state(false)

  async function openCard(card) {
    modalLoading = true
    modal = { item: card, editTitle: card.title, editScript: card.script_preview || '', saving: false, deleting: false }
    const full = await api.studioGet(card.id)
    modalLoading = false
    if (full && !full.detail) {
      modal = { ...modal, item: full, editTitle: full.title, editScript: full.script || '' }
    }
  }

  function closeModal() { modal = null }

  async function saveModal() {
    if (!modal) return
    modal = { ...modal, saving: true }
    const r = await api.studioUpdate(modal.item.id, {
      title: modal.editTitle,
      script: modal.editScript,
    })
    modal = { ...modal, saving: false }
    if (r && !r.detail) {
      closeModal()
      loadBoard()
    }
  }

  async function deleteCard(id) {
    if (!confirm('Delete this item?')) return
    if (modal) modal = { ...modal, deleting: true }
    await api.studioDelete(id)
    closeModal()
    loadBoard()
  }

  async function moveCard(id, stage) {
    await api.studioUpdate(id, { stage })
    loadBoard()
  }

  // ── Add idea ──────────────────────────────────────────────────────────────────
  let addTitle = $state('')
  let addBusy  = $state(false)

  async function addIdea() {
    if (!addTitle.trim()) return
    addBusy = true
    await api.studioCreate({ title: addTitle.trim(), stage: 'idea' })
    addTitle = ''
    addBusy = false
    loadBoard()
  }

  function onAddKey(e) { if (e.key === 'Enter') addIdea() }

  // Load board on mount
  loadBoard()
  onDestroy(stopBatchPoll)

  // ── Derived: total cards across all stages ────────────────────────────────────
  let totalCards = $derived(STAGES.reduce((s, st) => s + (board[st]?.length ?? 0), 0))

  // ── Stage navigation helpers ──────────────────────────────────────────────────
  function prevStage(stage) {
    const i = STAGES.indexOf(stage)
    return i > 0 ? STAGES[i - 1] : null
  }
  function nextStage(stage) {
    const i = STAGES.indexOf(stage)
    return i < STAGES.length - 1 ? STAGES[i + 1] : null
  }
</script>

<div class="studio">
  <div class="page-top">
    <div>
      <h1>{$_('studio.title')}</h1>
      <div class="sub">{$_('studio.subtitle')}</div>
    </div>
  </div>

  <!-- Batch generate form -->
  <div class="batch-form panel">
    <div class="form-row">
      <input class="inp" placeholder={$_('studio.niche_placeholder')} bind:value={batchNiche} disabled={batchBusy} />
      <input class="inp" placeholder={$_('studio.topic_placeholder')} bind:value={batchTopic} disabled={batchBusy} />
      <input class="inp num" type="number" min="1" max="20" bind:value={batchCount} disabled={batchBusy} title={$_('studio.count_title')} />
      <button class="btn-primary" onclick={startBatch} disabled={batchBusy || !batchNiche.trim()}>
        {batchBusy ? $_('studio.generating_btn') : $_('studio.generate_btn')}
      </button>
    </div>
    {#if batchError}<div class="err">{batchError}</div>{/if}
    {#if batchProgress}
      <div class="progress-row">
        <div class="prog-bar"><div class="prog-fill" style="width:{batchProgress.total > 0 ? Math.round(batchProgress.done / batchProgress.total * 100) : 0}%"></div></div>
        <span class="prog-label">
          {#if batchProgress.status === 'done'}
            {$_('studio.done_progress', { values: { count: batchProgress.created_ids?.length ?? 0 } })}
          {:else if batchProgress.status === 'error'}
            {$_('studio.error_progress', { values: { error: batchProgress.error || 'unknown' } })}
          {:else}
            {$_('studio.progress_generating', { values: { done: batchProgress.done, total: batchProgress.total } })}
          {/if}
        </span>
      </div>
    {/if}
  </div>

  <!-- Kanban board -->
  {#if boardError}<div class="err board-err">{boardError}</div>{/if}

  {#if !boardLoading && totalCards === 0}
    <div class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
          <rect x="3" y="3" width="18" height="4" rx="1"/><rect x="3" y="10" width="18" height="4" rx="1"/><rect x="3" y="17" width="18" height="4" rx="1"/>
        </svg>
      </div>
      <div class="empty-title">{$_('studio.board_empty_title')}</div>
      <div class="mut">{$_('studio.board_empty_msg')}</div>
    </div>
  {:else}
    <div class="board">
      {#each STAGES as stage}
        <div class="column">
          <div class="col-header">
            <span class="col-title">{STAGE_LABELS[stage]}</span>
            <span class="col-count">{board[stage]?.length ?? 0}</span>
          </div>
          <div class="col-cards">
            {#each (board[stage] ?? []) as card (card.id)}
              <div class="card" role="button" tabindex="0" onclick={() => openCard(card)} onkeydown={(e) => e.key === 'Enter' && openCard(card)}>
                <div class="card-title">{card.title}</div>
                {#if card.niche}<span class="niche-badge">{card.niche}</span>{/if}
                {#if card.script_preview}
                  <div class="card-preview">{card.script_preview}</div>
                {/if}
                <div class="card-actions" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="group" aria-label="Move card">
                  {#if prevStage(stage)}
                    <button class="move-btn" title={$_('studio.move_to', { values: { stage: STAGE_LABELS[prevStage(stage)] } })} onclick={() => moveCard(card.id, prevStage(stage))}>←</button>
                  {/if}
                  {#if nextStage(stage)}
                    <button class="move-btn" title={$_('studio.move_to', { values: { stage: STAGE_LABELS[nextStage(stage)] } })} onclick={() => moveCard(card.id, nextStage(stage))}>→</button>
                  {/if}
                </div>
              </div>
            {/each}

            {#if stage === 'idea'}
              <div class="add-idea">
                <input class="inp add-inp" placeholder={$_('studio.add_idea_placeholder')} bind:value={addTitle} onkeydown={onAddKey} disabled={addBusy} />
                <button class="btn-ghost" onclick={addIdea} disabled={addBusy || !addTitle.trim()}>{$_('studio.add_idea_btn')}</button>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Card modal -->
{#if modal}
  <div class="overlay" role="dialog" aria-modal="true" onclick={closeModal} onkeydown={(e) => e.key === 'Escape' && closeModal()}>
    <div class="modal" role="document" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
      <div class="modal-head">
        <input class="modal-title-inp" bind:value={modal.editTitle} placeholder={$_('studio.title_placeholder')} />
        <button class="icon-btn" onclick={closeModal} title={$_('studio.close_btn')} aria-label={$_('studio.close_btn')}>✕</button>
      </div>

      {#if modalLoading}
        <div class="mut" style="padding:16px">{$_('studio.modal_loading')}</div>
      {:else}
        <div class="modal-meta">
          {#if modal.item.niche}<span class="niche-badge">{modal.item.niche}</span>{/if}
          {#if modal.item.stage}<span class="stage-badge">{STAGE_LABELS[modal.item.stage] ?? modal.item.stage}</span>{/if}
          {#if modal.item.created_at}<span class="mut" style="font-size:11px">{modal.item.created_at.slice(0,10)}</span>{/if}
        </div>
        <textarea class="modal-script" rows="14" bind:value={modal.editScript} placeholder="Script will appear here…"></textarea>
        <div class="modal-foot">
          <button class="btn-danger" onclick={() => deleteCard(modal.item.id)} disabled={modal.deleting}>
            {modal.deleting ? $_('studio.deleting_btn') : $_('studio.delete_btn')}
          </button>
          <div style="flex:1"></div>
          <button class="btn-ghost" onclick={closeModal}>{$_('studio.cancel_btn')}</button>
          <button class="btn-primary" onclick={saveModal} disabled={modal.saving}>
            {modal.saving ? $_('studio.saving_btn') : $_('studio.save_btn')}
          </button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .studio { padding: 0 2px 32px; }
  .page-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
  .page-top h1 { font-size: 22px; font-weight: 700; margin: 0 0 2px; }
  .sub { font-size: 13px; color: var(--mut); }

  /* Batch form */
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 20px; }
  .form-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .inp { flex: 1; min-width: 140px; background: var(--soft); border: 1px solid var(--line); border-radius: 7px; padding: 8px 10px; color: var(--txt); font-size: 13px; outline: none; }
  .inp.num { flex: 0 0 64px; min-width: 64px; }
  .inp:focus { border-color: var(--accent); }

  /* Progress */
  .progress-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
  .prog-bar { flex: 1; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
  .prog-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width .3s; }
  .prog-label { font-size: 12px; color: var(--mut); white-space: nowrap; }

  /* Board */
  .board { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; }
  .column { flex: 0 0 220px; display: flex; flex-direction: column; }
  .col-header { display: flex; align-items: center; justify-content: space-between; padding: 6px 4px 8px; }
  .col-title { font-size: 12.5px; font-weight: 600; color: var(--txt); text-transform: uppercase; letter-spacing: .04em; }
  .col-count { font-size: 11px; background: var(--soft); border-radius: 10px; padding: 1px 7px; color: var(--mut); }
  .col-cards { display: flex; flex-direction: column; gap: 8px; }

  /* Card */
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 10px 12px; cursor: pointer; transition: border-color .15s; }
  .card:hover { border-color: var(--accent); }
  .card-title { font-size: 13px; font-weight: 600; line-height: 1.4; margin-bottom: 4px; }
  .niche-badge { display: inline-block; background: rgba(99,102,241,.15); color: var(--accent); font-size: 10.5px; border-radius: 4px; padding: 1px 6px; margin-bottom: 5px; }
  .stage-badge { display: inline-block; background: var(--soft); color: var(--mut); font-size: 10.5px; border-radius: 4px; padding: 1px 6px; margin-left: 4px; }
  .card-preview { font-size: 11.5px; color: var(--mut); line-height: 1.5; margin-top: 4px; white-space: pre-wrap; word-break: break-word; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; }
  .card-actions { display: flex; gap: 4px; margin-top: 8px; }
  .move-btn { background: var(--soft); border: 1px solid var(--line); color: var(--mut); border-radius: 5px; padding: 2px 8px; font-size: 12px; cursor: pointer; line-height: 1.4; }
  .move-btn:hover { border-color: var(--accent); color: var(--accent); }

  /* Add idea input */
  .add-idea { display: flex; gap: 6px; align-items: center; margin-top: 4px; }
  .add-inp { flex: 1; min-width: 0; font-size: 12px; padding: 6px 8px; }

  /* Empty state */
  .empty-state { text-align: center; padding: 60px 20px; color: var(--mut); }
  .empty-icon { opacity: .35; margin-bottom: 14px; display: flex; justify-content: center; }
  .empty-title { font-size: 16px; font-weight: 600; color: var(--txt); margin-bottom: 6px; }

  /* Buttons */
  .btn-primary { background: var(--accent); color: #fff; border: none; border-radius: 7px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
  .btn-primary:disabled { opacity: .45; cursor: default; }
  .btn-ghost { background: transparent; border: 1px solid var(--line); color: var(--txt); border-radius: 7px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .btn-ghost:disabled { opacity: .45; cursor: default; }
  .btn-danger { background: transparent; border: 1px solid var(--red, #f87171); color: var(--red, #f87171); border-radius: 7px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .btn-danger:disabled { opacity: .45; cursor: default; }
  .icon-btn { background: transparent; border: none; color: var(--mut); font-size: 16px; cursor: pointer; padding: 4px 8px; border-radius: 5px; line-height: 1; }
  .icon-btn:hover { color: var(--txt); }

  /* Errors */
  .err { color: var(--red, #f87171); font-size: 12.5px; margin-top: 6px; }
  .board-err { margin-bottom: 12px; }

  /* Modal/overlay */
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 16px; }
  .modal { background: var(--card, var(--panel)); border: 1px solid var(--line); border-radius: 14px; width: 100%; max-width: 680px; max-height: 90vh; overflow-y: auto; display: flex; flex-direction: column; }
  .modal-head { display: flex; align-items: center; gap: 10px; padding: 16px 18px 10px; border-bottom: 1px solid var(--line); }
  .modal-title-inp { flex: 1; background: transparent; border: none; font-size: 16px; font-weight: 700; color: var(--txt); outline: none; }
  .modal-meta { display: flex; align-items: center; gap: 6px; padding: 10px 18px 6px; flex-wrap: wrap; }
  .modal-script { width: 100%; box-sizing: border-box; background: var(--soft); border: 1px solid var(--line); border-radius: 8px; color: var(--txt); font-size: 13px; line-height: 1.6; padding: 10px 12px; margin: 8px 18px; width: calc(100% - 36px); resize: vertical; outline: none; font-family: inherit; }
  .modal-script:focus { border-color: var(--accent); }
  .modal-foot { display: flex; align-items: center; gap: 8px; padding: 12px 18px 16px; border-top: 1px solid var(--line); }
</style>
