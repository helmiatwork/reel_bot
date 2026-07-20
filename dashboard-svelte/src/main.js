import './app.css'
import './lib/i18n.js'
import { waitLocale } from 'svelte-i18n'
import { mount } from 'svelte'
import App from './App.svelte'

let app
waitLocale().then(() => {
  app = mount(App, { target: document.getElementById('app') })
})
export default app
