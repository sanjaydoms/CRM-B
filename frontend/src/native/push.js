/**
 * Push notifications: permission, registration, and what a tap opens.
 *
 * The server already decides WHO gets told what (crm_api/push.py). This side
 * has three jobs and no opinions: ask for permission at a moment that makes
 * sense, hand the FCM token to the backend so it can be reached, and turn a tap
 * into a screen.
 *
 * Permission is requested after sign-in rather than at first launch, and that
 * is deliberate. Android 13+ shows a system dialog that can only be answered
 * once; asked on a cold first launch, before the person has seen what the app
 * is for, it is refused -- and a refusal is close to permanent, because the
 * only way back is the OS settings screen. Asked after they have signed in to
 * their own boutique, the request has a reason behind it.
 *
 * NOTHING here runs unless the build was made with a Firebase configuration.
 * That is not caution, it is the difference between an app that works and one
 * that dies: PushNotifications.register() calls FirebaseMessaging.getInstance(),
 * which throws IllegalStateException when no google-services.json was present at
 * build time -- and Capacitor's bridge rethrows a plugin exception as a
 * RuntimeException on its own thread (Bridge.java:856), where nothing can catch
 * it. The process is killed. A try/catch in JavaScript cannot save this, because
 * the throw never reaches JavaScript.
 *
 * Observed exactly that way: sign in, the app closes; sign in again, it closes
 * faster, because a restored session calls this immediately.
 *
 * So the gate is a build-time fact rather than a runtime hope. build-android.mjs
 * sets VITE_PUSH_ENABLED only when android/app/google-services.json exists, and
 * the day that file is added the next build turns push on with no code change.
 */

import { api } from '../services/api';
import { handleDeepLink, isNative, platformName } from './index';

let registeredToken = null;

/**
 * Start push for the signed-in user. Called after login and on app start when
 * a session is restored.
 */
export const pushIsConfigured = () => import.meta.env?.VITE_PUSH_ENABLED === 'true';

export const enablePush = async () => {
  if (!isNative()) return { enabled: false, reason: 'not a device' };
  if (!pushIsConfigured()) {
    // See the note above: calling register() here would kill the process.
    console.info('push: no Firebase configuration in this build; skipping');
    return { enabled: false, reason: 'firebase not configured' };
  }

  try {
    return await start();
  } catch (error) {
    // Anything the bridge DOES hand back as a rejection -- a plugin missing, a
    // permission call refused by the OS -- must not take the sign-in with it.
    console.error('push could not be enabled', error);
    return { enabled: false, reason: 'push failed to start' };
  }
};

const start = async () => {
  const { PushNotifications } = await import('@capacitor/push-notifications');

  let status = await PushNotifications.checkPermissions();
  if (status.receive === 'prompt' || status.receive === 'prompt-with-rationale') {
    status = await PushNotifications.requestPermissions();
  }
  if (status.receive !== 'granted') {
    // Refused, or refused permanently. The bell inside the app still works, so
    // nothing is broken -- the person just has to open the app to see it.
    return { enabled: false, reason: 'permission not granted' };
  }

  PushNotifications.removeAllListeners();

  PushNotifications.addListener('registration', async ({ value }) => {
    if (value === registeredToken) return;
    try {
      await api.registerDevice(value, platformName());
      registeredToken = value;
    } catch (error) {
      // A device that fails to register is a device that gets no push. It is
      // not a reason to fail the sign-in that triggered it.
      console.error('device registration failed', error);
    }
  });

  PushNotifications.addListener('registrationError', (error) => {
    console.error('FCM registration error', error);
  });

  // Delivered while the app is open. Android does not draw a notification for
  // these, so the in-app bell is what has to update -- the badge is refreshed
  // by whoever registered onPushReceived.
  PushNotifications.addListener('pushNotificationReceived', (notification) => {
    received.forEach((handler) => handler(notification));
  });

  // The tap. `data` is what crm_api/push.py put there.
  PushNotifications.addListener('pushNotificationActionPerformed', ({ notification }) => {
    const data = notification?.data || {};
    if (data.order_id) {
      handleDeepLink(`/app/orders/${data.order_id}`);
    } else {
      handleDeepLink('/app/notifications');
    }
  });

  await PushNotifications.register();
  return { enabled: true };
};

const received = new Set();

/** Told when a push arrives while the app is in the foreground. */
export const onPushReceived = (handler) => {
  received.add(handler);
  return () => received.delete(handler);
};

/**
 * Stop this device receiving notifications for the account signing out.
 *
 * Called before the token is cleared, because the request needs it. A device
 * left registered keeps buzzing with the next shift's work for someone who is
 * no longer signed in.
 */
export const disablePush = async () => {
  if (!isNative() || !registeredToken) return;
  try {
    await api.unregisterDevice(registeredToken);
  } catch (error) {
    console.error('device unregistration failed', error);
  }
  registeredToken = null;
};
