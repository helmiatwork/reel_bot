import { register, init, locale, waitLocale } from 'svelte-i18n'

// Register lazy-loaded locale files
register('id', () => import('../locales/id.json'))
register('en', () => import('../locales/en.json'))

// Determine the initial locale: check localStorage, fallback to 'id'
const savedLocale = typeof window !== 'undefined' ? localStorage.getItem('reelbot_lang') : null
const initialLocale = savedLocale || 'id'

// Initialize svelte-i18n with fallback to Indonesian
init({
  fallbackLocale: 'id',
  initialLocale: initialLocale
})

// Helper to set language and persist to localStorage
export function setLang(lang) {
  locale.set(lang)
  if (typeof window !== 'undefined') {
    localStorage.setItem('reelbot_lang', lang)
  }
}

export { locale, waitLocale }
