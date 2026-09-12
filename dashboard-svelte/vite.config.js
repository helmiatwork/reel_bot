import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

const apiTarget = process.env.VITE_API_PROXY || 'http://localhost:3000'

// Build output goes straight into analytics-dashboard/, which Rails
// serves in production.
export default defineConfig({
  plugins: [svelte()],
  base: '/',
  build: {
    outDir: '../analytics-dashboard',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200
  },
  server: {
    port: 5180,
    proxy: {
      // dev convenience: hit the live Rails API on :3000 while running `npm run dev`
      '/dash': apiTarget,
      '/pipeline': apiTarget,
      '/clips': apiTarget,
      '/snoop': apiTarget,
      '/keywords': apiTarget,
      '/youtube': apiTarget,
      '/analyze': apiTarget,
      '/analytics': apiTarget,
      '/creators': apiTarget,
      '/songs': apiTarget,
      '/health': apiTarget,
      '/sources': apiTarget,
      '/decompose': apiTarget,
      '/frames': apiTarget,
      '/schedule': apiTarget,
      '/cookies': apiTarget,
      '/generate': apiTarget,
      '/discover': apiTarget
    }
  }
})
