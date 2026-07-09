import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Build output goes straight into analytics-dashboard/, which pipeline-api
// copies into the image and serves at http://localhost:8000.
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
      // dev convenience: hit the live API on :8000 while running `npm run dev`
      '/dash': 'http://localhost:8000',
      '/pipeline': 'http://localhost:8000',
      '/clips': 'http://localhost:8000',
      '/snoop': 'http://localhost:8000',
      '/youtube': 'http://localhost:8000',
      '/analyze': 'http://localhost:8000',
      '/analytics': 'http://localhost:8000',
      '/creators': 'http://localhost:8000',
      '/songs': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/sources': 'http://localhost:8000',
      '/decompose': 'http://localhost:8000',
      '/frames': 'http://localhost:8000',
      '/schedule': 'http://localhost:8000',
      '/cookies': 'http://localhost:8000',
      '/generate': 'http://localhost:8000',
      '/discover': 'http://localhost:8000'
    }
  }
})
