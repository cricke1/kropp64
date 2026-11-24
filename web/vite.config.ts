import { defineConfig } from 'vite'

// Servern (FastAPI) serverar dist/ på /. Under utveckling proxas API och WebSocket dit.
const target = process.env.KONSILIET_API ?? 'http://127.0.0.1:8790'

export default defineConfig({
  base: './',
  oxc: { jsx: { runtime: 'automatic', importSource: 'preact' } },
  build: { outDir: 'dist', assetsInlineLimit: 0, chunkSizeWarningLimit: 400 },
  server: {
    proxy: {
      '/api': target,
      '/ws': { target: target.replace('http', 'ws'), ws: true },
    },
  },
})
