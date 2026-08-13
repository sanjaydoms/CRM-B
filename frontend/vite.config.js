import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // Vite builds the React workspace only. The marketing site is plain
      // static HTML assembled by build-site.mjs after this runs -- it has no
      // bundle, no framework and no client-side routing on purpose, because a
      // crawler that does not execute JavaScript has to be able to read it.
      // Two entries, two bundles, on purpose. The platform console shares no
      // component with the boutique workspace and is opened by a handful of
      // people; folding it into app.html would put it in the download every
      // boutique makes. They share React and lucide-react, which the chunking
      // below already splits out, so the second entry costs its own code and
      // nothing else.
      input: {
        app: fileURLToPath(new URL('./app.html', import.meta.url)),
        superadmin: fileURLToPath(new URL('./superadmin.html', import.meta.url)),
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
