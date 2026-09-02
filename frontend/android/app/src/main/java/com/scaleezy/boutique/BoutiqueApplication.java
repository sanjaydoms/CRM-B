package com.scaleezy.boutique;

import android.app.Application;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.os.Build;

/**
 * Creates the notification channel the server sends to.
 *
 * On Android 8 and above a notification whose channel does not exist is
 * dropped -- not shown late, not shown in a default channel, dropped, with
 * nothing in the log to say so. The channel therefore has to exist before the
 * first push can arrive, which means at application start rather than when some
 * screen gets around to it.
 *
 * Its id must match FCM_CHANNEL_ID in boutique_crm/settings.py, which is what
 * crm_api/push_fcm.py puts in the payload.
 */
public class BoutiqueApplication extends Application {

    @Override
    public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }

        NotificationChannel channel = new NotificationChannel(
                getString(R.string.default_notification_channel_id),
                getString(R.string.default_notification_channel_name),
                // HIGH, not DEFAULT: these are work assignments and order
                // events on a shop floor. A tailor who is handed a garment
                // needs to be told now, not on their next unlock.
                NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription(getString(R.string.default_notification_channel_description));

        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.createNotificationChannel(channel);
        }
    }
}
