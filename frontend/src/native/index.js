/**
 * Everything the app does because it is running on a phone.
 *
 * One module, imported once by main.jsx, and inert in a browser: `start()`
 * returns immediately unless Capacitor says this is a native platform. That
 * keeps the web build's behaviour exactly as it was and keeps the native
 * concerns out of a 9,000-line component that has enough to think about.
 *
 * The plugins are imported lazily, inside start(), so the web bundle does not
 * carry them at all.
 */

import { Capacitor } from '@capacitor/core';

import { hydrateSession, setSessionBackend } from '../services/session';
import { runBack } from './back';

export const isNative = () => Capacitor.isNativePlatform();

/** What the OS is called, for the device registration payload. */
export const platformName = () => Capacitor.getPlatform();

/**
 * Prepare the session store before anything renders.
 *
 * Separate from start() and awaited by main.jsx, because the app decides on its
 * very first render whether anyone is signed in. Reading the token after that
 * decision shows the login screen to someone who is already signed in.
 */
export const restoreSession = async () => {
  if (!isNative()) {
    // The web backend seeds itself synchronously from localStorage at import.
    return;
  }

  try {
    const { secureSessionBackend } = await import('./storage');
    setSessionBackend(secureSessionBackend);
  } catch (error) {
    // Fail CLOSED. If the encrypted store cannot be reached -- the plugin
    // missing from a build, a device whose Keystore is unavailable -- the
    // fallback must not be the WebView's own storage, because that would
    // silently start writing a refresh token to exactly the place this app
    // promises never to keep one. Memory only: the session works until the app
    // is closed, and the user signs in again after that.
    console.error('secure storage unavailable; session will not be persisted', error);
    setSessionBackend({ read: () => null, write: () => {} });
    return;
  }

  await hydrateSession();
};

/** Wire the native behaviours. Safe to call on the web, where it does nothing. */
/**
 * Take the splash down, now that something real is on screen.
 *
 * The splash is configured with launchAutoHide: false, so it stays until this
 * is called. That is the point: on a default install it disappears on a timer,
 * and a timer cannot know when the bundle has finished booting -- so a slow
 * cold start shows the splash, then a white WebView, then the app. Hiding it
 * from here means the fade always lands on a painted screen.
 *
 * Two frames of grace first, because "React has rendered" and "the pixels are
 * up" are not the same moment.
 */
export const hideSplash = async () => {
  if (!isNative()) return;
  try {
    const { SplashScreen } = await import('@capacitor/splash-screen');
    await new Promise((resolve) => requestAnimationFrame(
      () => requestAnimationFrame(resolve)));
    // No fadeOutDuration here: Capacitor ignores it for the LAUNCH splash and
    // says so in the log. The fade is launchFadeOutDuration in
    // capacitor.config.json, which is the one that applies.
    await SplashScreen.hide();
  } catch (error) {
    // A splash that will not hide would be a permanent screen with no way past
    // it, so this failure is worth a line in the log and nothing more.
    console.error('splash screen would not hide', error);
  }
};

export const start = async () => {
  if (!isNative()) return;

  const [{ App }, { StatusBar, Style }, { Keyboard }] = await Promise.all([
    import('@capacitor/app'),
    import('@capacitor/status-bar'),
    import('@capacitor/keyboard'),
  ]);

  // --- the hardware back button ---------------------------------------
  App.addListener('backButton', ({ canGoBack }) => {
    if (runBack()) return;
    if (canGoBack) {
      window.history.back();
      return;
    }
    // Nothing left to close and nowhere to go back to: this is the app's front
    // door, and leaving is what the user asked for.
    App.exitApp();
  });

  // --- deep links -------------------------------------------------------
  App.addListener('appUrlOpen', ({ url }) => {
    handleDeepLink(url);
  });

  // The link that STARTED the app, which the listener above never sees: on a
  // cold start Android delivers the intent before any JavaScript exists to
  // hear it. Without this, tapping a notification for an order while the app
  // is closed opens the app on its dashboard and appears to have ignored the
  // tap -- which is most of the time, because a notification is what closes the
  // gap between "not using the app" and "using it".
  try {
    const launch = await App.getLaunchUrl();
    if (launch?.url) handleDeepLink(launch.url);
  } catch {
    // Not every platform answers this; a missing launch URL is the ordinary
    // case and not a failure.
  }

  // --- chrome -----------------------------------------------------------
  try {
    // The workspace is dark. A light status bar over it is unreadable.
    await StatusBar.setStyle({ style: Style.Dark });
  } catch { /* not fatal, and absent on some devices */ }

  try {
    // Scrolling stays enabled so a focused field can be brought above the
    // keyboard. The resize behaviour itself is set in AndroidManifest.xml
    // (windowSoftInputMode="adjustResize") -- Keyboard.setResizeMode answers
    // UNIMPLEMENTED on Android, which is silent unless you read the log.
    await Keyboard.setScroll({ isDisabled: false });
  } catch { /* absent on some devices; not worth failing the boot over */ }
};

/**
 * Route an opened link to the screen it names.
 *
 * The URLs are the product's own: an order link, a tracking link, a password
 * reset. Anything unrecognised is ignored rather than guessed at -- an app that
 * navigates somewhere arbitrary because a link was malformed is worse than one
 * that opens on its dashboard.
 */
const deepLinkHandlers = new Set();

export const onDeepLink = (handler) => {
  deepLinkHandlers.add(handler);
  return () => deepLinkHandlers.delete(handler);
};

export const handleDeepLink = (rawUrl) => {
  let parsed;
  try {
    // The base makes a bare path work as well as a full link, which is what
    // lets a notification say `/app/orders/T2B-...` without naming a host --
    // and a host named there would silently stop matching the day the domain
    // changes. The base itself is never used for anything but parsing.
    parsed = new URL(rawUrl, 'https://app.invalid');
  } catch {
    return;
  }
  deepLinkHandlers.forEach((handler) => {
    try {
      handler(parsed);
    } catch (error) {
      console.error('deep link handler failed', error);
    }
  });
};
