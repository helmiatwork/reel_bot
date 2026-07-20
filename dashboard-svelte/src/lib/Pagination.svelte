<script>
  import { _ } from 'svelte-i18n'
  // ponytail: minimal pagination bar — no framework, just two buttons + a label
  let { offset = 0, limit = 25, total = 0, onprev, onnext } = $props()

  let from = $derived(total === 0 ? 0 : offset + 1)
  let to = $derived(Math.min(offset + limit, total))
  let atStart = $derived(offset === 0)
  let atEnd = $derived(offset + limit >= total)
</script>

{#if total > limit}
  <div class="pg">
    <button disabled={atStart} onclick={onprev}>{$_('pagination.prev')}</button>
    <span class="mut">{from}–{to} {$_('pagination.of')} {total}</span>
    <button disabled={atEnd} onclick={onnext}>{$_('pagination.next')}</button>
  </div>
{:else if total > 0}
  <div class="pg"><span class="mut">{from}–{to} {$_('pagination.of')} {total}</span></div>
{/if}

<style>
  .pg {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 0;
    font-size: 0.85rem;
  }
  button {
    padding: 0.3rem 0.8rem;
    border-radius: 6px;
    border: 1px solid var(--border, #2d3748);
    background: var(--bg-card, #1a202c);
    color: var(--text, #e2e8f0);
    cursor: pointer;
    font-size: 0.85rem;
  }
  button:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
  button:not(:disabled):hover {
    background: var(--bg-hover, #2d3748);
  }
</style>
