import { writable } from 'svelte/store'

// Valid page ids — must stay in sync with App.svelte's {#if} chain and NAV n.p values.
const VALID_PAGES = new Set([
  'openclaw', 'dashboard', 'sources', 'analysis', 'clips', 'clipper', 'snoop',
  'performance', 'pipeline', 'posts', 'agents', 'formulas', 'cost', 'discover', 'creators', 'songs',
  'decompose', 'generate', 'cookies', 'publish-accounts', 'jadwal', 'seo', 'prep', 'studio'
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

// App-wide job polling (analyze runs)
export const jobs = writable([])

// Toast notifications: array of { id, kind, title, sub }
export const toasts = writable([])

let toastId = 0
export function pushToast(kind, title, sub = '') {
  const id = ++toastId
  toasts.update(ts => [...ts, { id, kind, title, sub }])
  // Auto-dismiss after 5s
  setTimeout(() => {
    toasts.update(ts => ts.filter(t => t.id !== id))
  }, 5000)
  return id
}

export function dismissToast(id) {
  toasts.update(ts => ts.filter(t => t.id !== id))
}

// ponytail: Web Audio context reused, wrapped in try/catch for safety
let audioCtx = null
function getAudioContext() {
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)()
    }
    return audioCtx
  } catch (e) {
    return null
  }
}

// Play a beep: freq(hz), duration(ms)
function beep(freq, duration) {
  const ctx = getAudioContext()
  if (!ctx) return
  try {
    const now = ctx.currentTime
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.15, now)
    gain.gain.exponentialRampToValueAtTime(0.01, now + duration / 1000)
    osc.start(now)
    osc.stop(now + duration / 1000)
  } catch (e) {
    // silently ignore audio errors
  }
}

export function beepSuccess() {
  // 2-note: E5 then G5, 100ms each
  beep(659.25, 100)
  setTimeout(() => beep(783.99, 100), 110)
}

export function beepError() {
  // Single low tone: A3, 150ms
  beep(220, 150)
}
