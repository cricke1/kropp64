import { defineConfig } from 'vite'

// Servern (FastAPI) serverar dist/ på /. Under utveckling proxas API och WebSocket dit.
const target = process.env.KONSILIET_API ?? 'http://127.0.0.1:8790'
// Publik demo (drift/publik-demo.sh): KONSILIET_PUBLIK_DEMO=1 låser webben i demoläge.
const publikDemo = process.env.KONSILIET_PUBLIK_DEMO === '1'

export default defineConfig({
  base: './',
  define: { __PUBLIK_DEMO__: JSON.stringify(publikDemo) },
  oxc: { jsx: { runtime: 'automatic', importSource: 'preact' } },
  build: { outDir: 'dist', assetsInlineLimit: 0, chunkSizeWarningLimit: 400 },
  server: {
    proxy: {
      '/api': target,
      '/ws': { target: target.replace('http', 'ws'), ws: true },
    },
  },
})
