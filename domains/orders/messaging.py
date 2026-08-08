"""Outbound customer messaging, and the seam a real transport plugs into.

Every automated customer notification is recorded as a CustomerMessage before
anything tries to deliver it, so the order's communication history is complete
whether or not a transport is configured. The default backend only logs, which
means the history, the boutique toggle and the tracking links are all working
and testable before a WhatsApp Business account exists.

Swapping in delivery is one setting: point ``CUSTOMER_MESSAGE_BACKEND`` at
another callable. It follows the same convention as
``DESIGN_STUDIO_INTELLIGENCE``.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

from crm_api.models import BoutiqueSettings, CustomerMessage

logger = logging.getLogger(__name__)

_DEFAULT_BACKEND = 'domains.orders.messaging.log_backend'
_cache = {}


def log_backend(message):
    """Record the message and report it delivered nowhere.

    Returns the provider's id for the message; there is no provider here, so it
    returns an empty string.
    """
    logger.info(
        "customer message [%s] to %s for order %s: %s",
        message.template_key, message.to_number,
        message.order.order_id, message.body,
    )
    return ''


def get_backend():
    path = getattr(settings, 'CUSTOMER_MESSAGE_BACKEND', _DEFAULT_BACKEND) or _DEFAULT_BACKEND
    if path not in _cache:
        try:
            _cache[path] = import_string(path)
        except ImportError:
            # A misconfigured transport must not take order creation down with
            # it -- the order matters more than the notification.
            logger.exception("CUSTOMER_MESSAGE_BACKEND %r is not importable", path)
            _cache[path] = log_backend
    return _cache[path]


def _deliver(message):
    """Hand one message to the transport and record what happened.

    Runs after the caller's transaction has committed, so its own failure --
    including a database failure inside the transport -- can only ever mark this
    message FAILED. Nothing it does can reach back into the order.
    """
    try:
        message.provider_message_id = get_backend()(message) or ''
        message.status = 'SENT'
    except Exception as exc:  # noqa: BLE001 - any transport failure is just a failed message
        logger.exception("customer message %s failed", message.pk)
        message.status = 'FAILED'
        message.error = str(exc)

    message.save(update_fields=['provider_message_id', 'status', 'error'])


def send_customer_message(order, template_key, body, sent_by=None):
    """Record a message to the order's customer, and deliver it after commit.

    Returns the CustomerMessage (still QUEUED), or None if the boutique has
    customer messaging switched off.

    The row is written inside the caller's transaction so it lands with the
    order it describes; delivery is deferred to on_commit for two reasons that
    both cost real money:

    - Every caller is inside @transaction.atomic. A transport that touches the
      database -- which any real one does, writing a receipt or a rate-limit
      counter -- aborts that transaction when it fails, and the follow-up save()
      recording the failure then raises inside the caller and rolls back the
      order itself. Verified: it costs the boutique the order to record that a
      WhatsApp message did not send.
    - Delivery must not happen for an order that is subsequently rolled back.
      A customer told their order is confirmed, for an order that does not
      exist, is worse than no message.

    Outside a transaction, on_commit runs the callback immediately, so a manual
    send from a plain view still behaves synchronously.
    """
    config, _ = BoutiqueSettings.objects.get_or_create(id=1)
    if not config.customer_messaging_enabled:
        return None

    message = CustomerMessage.objects.create(
        order=order,
        template_key=template_key,
        to_number=order.customer.mobile_number,
        body=body,
        sent_by=sent_by,
    )
    transaction.on_commit(lambda: _deliver(message))
    return message
