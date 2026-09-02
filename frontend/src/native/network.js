/**
 * Whether the phone can reach anything, published to React.
 *
 * The product's rule, from the directive it was built to: never claim an
 * operation succeeded that the backend has not confirmed. So this exists to
 * TELL the user they are offline and to stop them starting work that cannot
 * finish -- not to queue writes and replay them later, which would mean
 * inventing an offline conflict model the backend has no notion of.
 */

const listeners = new Set();
let online = true;

export const isOnline = () => online;

export const onNetworkChange = (handler) => {
  listeners.add(handler);
  handler(online);
  return () => listeners.delete(handler);
};

const publish = (next) => {
  if (next === online) return;
  online = next;
  listeners.forEach((handler) => handler(online));
};

export const watchNetwork = async (native) => {
  // The browser's own events, on BOTH platforms. The Android WebView fires
  // them too, and they arrive without waiting for a plugin to load -- which
  // matters because watchNetwork is not awaited: a device that is offline at
  // launch would otherwise report itself online until the plugin resolved.
  publish(navigator.onLine);
  window.addEventListener('online', () => publish(true));
  window.addEventListener('offline', () => publish(false));

  if (!native) return;

  // On a device the plugin is the better authority: it distinguishes a radio
  // that is off from a network that is merely useless, and it reports the
  // change even where the WebView's own event does not fire.
  const { Network } = await import('@capacitor/network');
  const status = await Network.getStatus();
  publish(status.connected);
  Network.addListener('networkStatusChange', (s) => publish(s.connected));
};
