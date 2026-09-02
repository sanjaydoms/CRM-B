/**
 * Runs the Android web build and gives Capacitor the filename it insists on.
 *
 * Vite names an HTML output after its source file, so `app.html` in and
 * `app.html` out -- and Capacitor's Android WebView opens `index.html` and
 * nothing else. Renaming afterwards is smaller than keeping a duplicate
 * index.html in the repository for the two files to drift apart.
 */

import { execFileSync } from 'node:child_process'
import { renameSync, existsSync } from 'node:fs'

execFileSync('npx', ['vite', 'build', '--config', 'vite.config.android.js'],
             { stdio: 'inherit' })

const built = new URL('./dist-android/app.html', import.meta.url)
const wanted = new URL('./dist-android/index.html', import.meta.url)
if (!existsSync(built)) {
  throw new Error('dist-android/app.html was not produced; nothing to rename.')
}
renameSync(built, wanted)
console.log('dist-android/index.html ready for `npx cap sync android`')
