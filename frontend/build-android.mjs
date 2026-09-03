/**
 * Runs the Android web build and gives Capacitor the filename it insists on.
 *
 * Vite names an HTML output after its source file, so `app.html` in and
 * `app.html` out -- and Capacitor's Android WebView opens `index.html` and
 * nothing else. Renaming afterwards is smaller than keeping a duplicate
 * index.html in the repository for the two files to drift apart.
 *
 * It also decides one thing the web layer cannot see for itself: whether this
 * build has a Firebase configuration. See below.
 */

import { execFileSync } from 'node:child_process'
import { renameSync, existsSync } from 'node:fs'

/**
 * Push is switched on by the presence of android/app/google-services.json, and
 * by nothing else.
 *
 * This is a guard against a crash, not a feature flag. PushNotifications
 * .register() calls FirebaseMessaging.getInstance(), which throws
 * IllegalStateException when the google-services plugin was never applied --
 * and Capacitor rethrows a plugin exception as a RuntimeException on its own
 * thread, where no JavaScript can catch it. The process is killed: the user
 * signs in and the app closes.
 *
 * Gradle already applies the google-services plugin only when this file exists
 * (see android/app/build.gradle). Reading the same file here means the web
 * layer and the native layer can never disagree about whether Firebase is
 * available -- and the day it is added, the next build turns push on with no
 * code change.
 */
const firebaseConfig = new URL('./android/app/google-services.json', import.meta.url)
const pushEnabled = existsSync(firebaseConfig)

console.log(pushEnabled
  ? 'push: google-services.json found, registration enabled'
  : 'push: no google-services.json, registration disabled for this build')

execFileSync('npx', ['vite', 'build', '--config', 'vite.config.android.js'],
             { stdio: 'inherit', env: { ...process.env, VITE_PUSH_ENABLED: String(pushEnabled) } })

const built = new URL('./dist-android/app.html', import.meta.url)
const wanted = new URL('./dist-android/index.html', import.meta.url)
if (!existsSync(built)) {
  throw new Error('dist-android/app.html was not produced; nothing to rename.')
}
renameSync(built, wanted)
console.log('dist-android/index.html ready for `npx cap sync android`')
