import { writable } from 'svelte/store'

// Valid page ids — must stay in sync with App.svelte's {#if} chain and NAV n.p values.
const VALID_PAGES = new Set([
  'openclaw', 'dashboard', 'sources', 'analysis', 'clips', 'clipper',
  'performance', 'pipeline', 'posts', 'agents', 'formulas', 'cost', 'discover'
])

function hashPage() {
  if (typeof window === 'undefined') return 'dashboard'
  const h = window.location.hash.replace(/^#/, '')
  return VALID_PAGES.has(h) ? h : 'dashboard'
}

// Hash-synced page store: survives refresh, works with browser back/forward.
function createPageStore() {
  const { subscribe, set } = writable(hashPage())

  // Keep hash in sync whenever the store value changes.
  subscribe((v) => {
    if (typeof window !== 'undefined') {
      // location.hash = adds a history entry, giving back/forward for free.
      window.location.hash = v
    }
  })

  // Bridge browser back/forward → store.
  if (typeof window !== 'undefined') {
    window.addEventListener('hashchange', () => {
      set(hashPage())
    })
  }

  return { subscribe, set }
}

export const page = createPageStore()

// drawer content: null = closed, else { type, data }
// type ∈ 'source' | 'agent' | 'formula' | 'piece'
export const drawer = writable(null)

export function openDrawer(type, data) {
  drawer.set({ type, data })
}
export function closeDrawer() {
  drawer.set(null)
}
