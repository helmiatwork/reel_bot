import { writable } from 'svelte/store'

// current page id (matches nav data-p)
export const page = writable('dashboard')

// drawer content: null = closed, else { type, data }
// type ∈ 'source' | 'agent' | 'formula' | 'piece'
export const drawer = writable(null)

export function openDrawer(type, data) {
  drawer.set({ type, data })
}
export function closeDrawer() {
  drawer.set(null)
}
