import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { hideSplash, isNative, restoreSession, start } from './native'
import { watchNetwork } from './native/network'

// The session is restored BEFORE the first render, not after it. App decides on
// its first pass whether anyone is signed in, and on Android that answer lives
// in an encrypted store that can only be read asynchronously -- so rendering
// first would show the login screen to someone who never signed out, for as
// long as the read took.
//
// On the web this resolves immediately: session.js seeds itself from
// localStorage at import, exactly as it always did.
const boot = async () => {
  await restoreSession()
  watchNetwork(isNative())

  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )

  // After the render, because none of it affects what is drawn first and the
  // back-button listener has nothing to act on until there is a screen.
  start()

  // And only now does the splash come down, onto a screen that has painted.
  hideSplash()
}

boot()
