/**
 * The session, kept in Android's encrypted store instead of the WebView's.
 *
 * A Capacitor WebView's localStorage lives in the app's private data directory,
 * which no other app can read on a device that has not been rooted. That is
 * already better than it sounds -- but it is readable by anything that gets
 * filesystem access, it is included in device backups unless they are turned
 * off, and it is the first place anyone looks. The access token is short-lived
 * now; the refresh token is not, and it is the one worth protecting.
 *
 * capacitor-secure-storage-plugin stores values through the Android Keystore,
 * so the bytes on disk are encrypted with a key the OS holds and the app cannot
 * export.
 *
 * Reads are asynchronous, which is why session.js keeps the values in memory
 * and hydrates once at boot rather than reading per request.
 */

import { SecureStoragePlugin } from 'capacitor-secure-storage-plugin';

const KEY = 'boutique.session';

export const secureSessionBackend = {
  async read() {
    try {
      const { value } = await SecureStoragePlugin.get({ key: KEY });
      return JSON.parse(value);
    } catch {
      // The plugin throws rather than returning null when the key is absent,
      // which is the ordinary state on a fresh install.
      return null;
    }
  },

  async write(session) {
    try {
      if (!session || !session.token) {
        await SecureStoragePlugin.remove({ key: KEY });
        return;
      }
      await SecureStoragePlugin.set({ key: KEY, value: JSON.stringify(session) });
    } catch (error) {
      // Losing the ability to persist is not a reason to lose the session in
      // memory: the user stays signed in until the app is closed.
      console.error('secure storage write failed', error);
    }
  },
};
