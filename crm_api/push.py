"""Push notifications, and the one place that decides who gets one.

The product already writes every event a staff member cares about into
Notification -- order received, stage assigned, garment ready, payment landed,
stock run down. Until now those rows were only ever read by the bell, and the
bell was fetched once at login. On a desktop that is a mild annoyance. On a
phone in an apron pocket it means the app is silent: a tailor is given work and
finds out when they next open it.

So this does not invent a second notion of "notifiable event". It listens to the
one that exists. Every Notification row, however it was created and by whichever
of the twenty-odd call sites, is offered to the devices of whoever it is
addressed to. Nothing else has to remember to push.

Delivery follows the convention domains/orders/messaging.py already set for
customer messaging: a swappable callable named by a setting, defaulting to one
that logs. That is what lets registration, targeting, deep links and the whole
Android side be built and tested before a Firebase project exists -- and what
keeps the test suite from making network calls.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.module_loading import import_string

from crm_api.models import DeviceToken, Notification, Tailor

logger = logging.getLogger(__name__)

_cache = {}


def log_backend(messages):
    """Report what would have been sent. The shipped default.

    Takes the whole batch rather than one message, because a real transport
    sends a batch in one call and this has to have the same shape.
    """
    for message in messages:
        logger.info("push [%s] to %s: %s", message['data'].get('type'),
                    message['token'][:12] + '...', message['title'])
    return []


def get_backend():
    path = getattr(settings, 'PUSH_BACKEND', '') or 'crm_api.push.log_backend'
    if path not in _cache:
        try:
            _cache[path] = import_string(path)
        except ImportError:
            # A misconfigured transport must not take order creation down with
            # it. The same rule, and the same reason, as CUSTOMER_MESSAGE_BACKEND.
            logger.exception("PUSH_BACKEND %r is not importable", path)
            _cache[path] = log_backend
    return _cache[path]


def recipients_for(notification):
    """The user accounts a notification is addressed to.

    The inverse of NotificationViewSet._audience, and it has to stay that way:
    if these two disagree, a push arrives for something the bell will not show.

      * 'Owner' is the account whose email matches the boutique's owner_email --
        the same positive identification core.roles makes, rather than "whoever
        has no staff profile".
      * Any other role names Tailor profiles carrying it, narrowed to one person
        when the notification names an email and left as the whole role when it
        does not (a queue arrival is addressed to every QC Master on purpose).
      * 'Customer' reaches nobody. Customers have no accounts in this product;
        they are reached by the tracking link and by WhatsApp.
    """
    role = notification.recipient_role
    if role == 'Customer':
        return []

    if role == 'Owner':
        from django.contrib.auth.models import User
        from django.db import connection
        # Two getattrs: `connection.tenant` itself is absent outside a request
        # -- a management command, the public schema -- and the same guard is
        # why core/roles.py wraps its own read of this in a try. Without a
        # boutique there is no owner to notify, which is the right answer
        # rather than an AttributeError inside a post-commit hook.
        tenant = getattr(connection, 'tenant', None)
        owner_email = (getattr(tenant, 'owner_email', '') or '').strip()
        if not owner_email:
            return []
        return list(User.objects.filter(email__iexact=owner_email, is_active=True))

    profiles = Tailor.objects.filter(role=role, user__isnull=False)
    email = (notification.recipient_email or '').strip()
    if email:
        profiles = profiles.filter(email__iexact=email)
    return [p.user for p in profiles.select_related('user') if p.user and p.user.is_active]


def message_for(notification, token):
    """One device's payload.

    `data` rather than a fixed screen name: the Android client owns its own
    routing, and what it needs from here is WHAT this is about. An order id is
    enough for it to open that order; without one it opens the notification
    list, which is still better than opening the dashboard.
    """
    data = {'type': 'order' if notification.order_id else 'notification',
            'notification_id': str(notification.pk)}
    if notification.order_id:
        # The reference the tailor reads, not the primary key -- it is what the
        # deep link and the tracking page both use.
        data['order_id'] = notification.order.order_id
    return {
        'token': token,
        'title': notification.title,
        'body': notification.message,
        'data': data,
    }


def push_notification(notification):
    """Deliver one Notification to every device its audience has registered."""
    users = recipients_for(notification)
    if not users:
        return 0

    tokens = list(DeviceToken.objects.filter(
        user__in=users, is_active=True).values_list('token', flat=True))
    if not tokens:
        return 0

    messages = [message_for(notification, token) for token in tokens]
    try:
        dead = get_backend()(messages) or []
    except Exception:
        # A push that fails is a push that fails. It must not roll back the
        # order transition that raised it, and by this point that transition has
        # already been committed anyway.
        logger.exception("push delivery failed for notification %s", notification.pk)
        return 0

    if dead:
        # FCM answers UNREGISTERED for an app that has been uninstalled. Keeping
        # those rows means every later send wastes a slot on a device that no
        # longer exists.
        DeviceToken.objects.filter(token__in=dead).update(is_active=False)
        logger.info("deactivated %s device tokens FCM rejected", len(dead))

    return len(messages) - len(dead)


@receiver(post_save, sender=Notification, dispatch_uid='crm_api.push')
def _push_on_notification(sender, instance, created, **kwargs):
    """Push when the row is created, and only then.

    on_commit, so a notification written inside a transition that later rolls
    back is never announced to a phone -- an order that did not move must not
    buzz in someone's pocket. Marking one read must not push again, hence
    `created`.
    """
    if not created:
        return
    transaction.on_commit(lambda: _push_quietly(instance))


def _push_quietly(notification):
    """Never let a push turn a committed transition into an error.

    An exception raised inside an on_commit callback propagates out of the
    atomic block that scheduled it -- and by then the order has already been
    written. So a boutique would see a 500 for a stage transition that in fact
    succeeded, and the retry would be applied to an order that had already
    moved.

    push_notification guards the transport itself; this guards everything around
    it -- resolving the audience, reading device rows, a schema that has gone
    away since the row was written.
    """
    try:
        push_notification(notification)
    except Exception:
        logger.exception("push for notification %s failed after commit",
                         getattr(notification, 'pk', None))
