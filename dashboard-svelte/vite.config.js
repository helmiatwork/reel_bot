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
      '/analytics': 'http://localhost:8000',
      '/health': 'http://localhost:8000'
    }
  }
})
