/**
 * The build that goes inside the Android app.
 *
 * Two differences from the web build, both deliberate:
 *
 *   * ONE entry. The web build also emits superadmin.html -- the platform
 *     console, which is opened by a handful of people on a desktop and shares
 *     no screen with the boutique workspace. Bundling it into the APK would put
 *     the whole console in every boutique's download for nobody's benefit.
 *
 *   * The entry is emitted as index.html, because that is the only file
 *     Capacitor's Android WebView will open.
 *
 * The API URL is baked in at build time (Vite substitutes import.meta.env), so
 * an APK is permanently pointed at whichever backend was configured when it was
 * built. That is exactly why the guard below refuses to build without one:
 * shipping a release that quietly talks to http://localhost:8000 is a bug you
 * only find after upload.
 */

import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiUrl = process.env.VITE_API_URL
if (!apiUrl) {
  throw new Error(
    'VITE_API_URL is not set. An Android build bakes the API address in, so a '
    + 'build without one produces an app that can only talk to a developer\'s '
    + 'laptop. Set it to the environment this build is for, e.g.\n'
    + '  VITE_API_URL=https://crm-b-sitt.onrender.com/api npm run build:android')
}
if (/localhost|127\.0\.0\.1/.test(apiUrl) && process.env.ALLOW_LOCAL_API !== 'true') {
  throw new Error(
    `VITE_API_URL points at ${apiUrl}. An Android device is not your laptop: `
    + 'localhost inside the app is the phone itself. Use a LAN address or a '
    + 'deployed environment, or set ALLOW_LOCAL_API=true if you really mean it.')
}

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-android',
    emptyOutDir: true,
    rollupOptions: {
      input: { index: fileURLToPath(new URL('./app.html', import.meta.url)) },
      output: {
        // Same reasoning as the web build: React and the icon set change only
        // when they are upgraded, and keeping them in their own chunks keeps
        // the WebView's cache useful across app updates.
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('lucide-react')) return 'icons'
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react'
        },
      },
    },
  },
})
