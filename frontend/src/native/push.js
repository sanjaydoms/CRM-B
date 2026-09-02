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
 */

import { api } from '../services/api';
import { handleDeepLink, isNative, platformName } from './index';

let registeredToken = null;

/**
 * Start push for the signed-in user. Called after login and on app start when
 * a session is restored.
 */
export const enablePush = async () => {
  if (!isNative()) return { enabled: false, reason: 'not a device' };

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
