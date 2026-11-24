import { defineConfig } from 'vite'

// Riggvyn för landningssidan: ett eget bygge med src/rigg/sajt.ts som ingång, utan HTML.
// Körs av site/bygg.sh: npx vite build --config vite.sajt.config.ts (UT = utmapp, standard ../site/dist/rigg).
export default defineConfig({
  base: './',
  publicDir: false,
  build: {
    outDir: process.env.UT ?? '../site/dist/rigg',
    emptyOutDir: true,
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 800,
    rolldownOptions: {
      input: 'src/rigg/sajt.ts',
      output: { entryFileNames: 'rigg.js', chunkFileNames: '[name]-[hash].js', assetFileNames: '[name]-[hash][extname]' },
    },
  },
})
