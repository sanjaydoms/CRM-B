import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // Two entry points, not one. index.html is the marketing site: plain
      // static HTML that a crawler can read without running anything. The React
      // workspace lives at app.html and is served from /app.
      //
      // This split is the whole point -- when the marketing copy lived inside
      // App.jsx as `view` state, boutique.scaleezy.com returned 919 bytes with
      // an empty <div id="root">, /features 404'd, and every answer engine that
      // does not execute JavaScript saw nothing at all.
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        app: fileURLToPath(new URL('./app.html', import.meta.url)),
      },
      output: {
        // Everything used to land in one ~594KB file, so shipping a one-line
        // change to the app invalidated React and the icon set along with it,
        // and every returning user re-downloaded the lot. These dependencies
        // change only when we upgrade them, so giving them their own chunks
        // lets the browser keep them cached across deploys.
        // Rolldown (Vite 8) only accepts the function form here, not an object.
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('lucide-react')) return 'icons'
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react'
        },
      },
    },
  },
})
