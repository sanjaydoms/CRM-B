"""Delivery through Firebase Cloud Messaging, for when a project exists.

Not wired in by default. Point PUSH_BACKEND at `crm_api.push_fcm.send` and give
the service the credentials below, and every Notification the product already
writes starts arriving on the staff member's phone. Until then crm_api.push
logs, which is a working product with a silent phone rather than a broken one.

    PUSH_BACKEND=crm_api.push_fcm.send
    FCM_PROJECT_ID=<firebase project id>
    GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

The service-account JSON is a production secret in the same class as
SUPABASE_SERVICE_KEY: it authorises sending to every device registered against
the project. It belongs in the deployment's secret store, never in this
repository and never in the Android bundle.

Why HTTP v1 and not the legacy server key: Google turned the legacy endpoint off
in 2024. There is no simpler option left, which is why this needs an OAuth
library at all.

`google-auth` is imported inside the function, so a deployment that does not use
push does not need the dependency installed.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ENDPOINT = 'https://fcm.googleapis.com/v1/projects/{project}/messages:send'
SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'
TIMEOUT = (5, 30)

_credentials = None


def _access_token():
    """A cached, auto-refreshing OAuth token for the service account."""
    global _credentials
    if _credentials is None:
        from google.auth import default  # imported lazily; see the docstring
        _credentials, _ = default(scopes=[SCOPE])
    if not _credentials.valid:
        from google.auth.transport.requests import Request
        _credentials.refresh(Request())
    return _credentials.token


def send(messages):
    """Send a batch and return the tokens FCM says are dead.

    One HTTP call per message: the v1 API has no true batch endpoint (the old
    batch route was retired with the legacy API), and a boutique's staff is
    tens of devices, not thousands. If that stops being true, this is where a
    thread pool goes.
    """
    project = getattr(settings, 'FCM_PROJECT_ID', '')
    if not project:
        logger.error("FCM_PROJECT_ID is not set; nothing was sent")
        return []

    url = ENDPOINT.format(project=project)
    headers = {'Authorization': f'Bearer {_access_token()}',
               'Content-Type': 'application/json; UTF-8'}
    dead = []

    for message in messages:
        payload = {'message': {
            'token': message['token'],
            'notification': {'title': message['title'], 'body': message['body']},
            # Every value must be a string in the v1 API -- a number here is a
            # 400 for the whole message.
            'data': {k: str(v) for k, v in message['data'].items()},
            'android': {
                'priority': 'high',
                'notification': {
                    # Tapping opens the app rather than a browser; the Android
                    # side reads `data` to decide which screen. The channel must
                    # match the one the app creates, or Android files the
                    # notification under a channel that does not exist and drops
                    # it without showing anything.
                    'click_action': 'FCM_PLUGIN_ACTIVITY',
                    'channel_id': getattr(settings, 'FCM_CHANNEL_ID', 'boutique_orders'),
                },
            },
        }}

        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        if response.status_code == 200:
            continue

        # 404 UNREGISTERED and a 400 naming UNREGISTERED both mean this device
        # will never receive anything again.
        body = response.text[:300]
        unregistered = response.status_code == 404 or (
            response.status_code == 400 and 'UNREGISTERED' in body.upper())
        if unregistered:
            dead.append(message['token'])
        else:
            logger.error("FCM refused a message: %s %s", response.status_code, body)

    return dead
