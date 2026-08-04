import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
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
