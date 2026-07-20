<script>
  import { slide } from 'svelte/transition'
  import { _ } from 'svelte-i18n'
  import { toasts, dismissToast } from './stores.js'
</script>

<!-- Toast container: fixed top-right, stacked -->
<div class="toasts-container">
  {#each $toasts as toast (toast.id)}
    <div
      class="toast {toast.kind}"
      transition:slide={{ duration: 300 }}
    >
      <div class="toast-content">
        <span class="toast-icon">
          {#if toast.kind === 'success'}
            ✓
          {:else}
            ✗
          {/if}
        </span>
        <div class="toast-text">
          <div class="toast-title">{toast.title}</div>
          {#if toast.sub}
            <div class="toast-sub">{toast.sub}</div>
          {/if}
        </div>
      </div>
      <button
        class="toast-close"
        onclick={() => dismissToast(toast.id)}
        aria-label={$_('toast.dismiss')}
      >
        ×
      </button>
    </div>
  {/each}
</div>

<style>
  .toasts-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 2000;
    display: flex;
    flex-direction: column;
    gap: 10px;
    pointer-events: none;
  }

  .toast {
    pointer-events: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 16px;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
    max-width: 380px;
    min-width: 280px;
  }

  .toast.success {
    border-left: 4px solid var(--green);
  }

  .toast.error {
    border-left: 4px solid #ef4444;
  }

  .toast-content {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .toast-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    font-weight: 700;
    font-size: 14px;
  }

  .toast.success .toast-icon {
    color: var(--green);
  }

  .toast.error .toast-icon {
    color: #ef4444;
  }

  .toast-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .toast-title {
    font-weight: 500;
    font-size: 13px;
    color: var(--txt);
  }

  .toast-sub {
    font-size: 12px;
    color: var(--mut);
    word-break: break-word;
    line-height: 1.4;
  }

  .toast-close {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--mut);
    font-size: 20px;
    padding: 0;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: color 0.2s;
  }

  .toast-close:hover {
    color: var(--txt);
  }
</style>
