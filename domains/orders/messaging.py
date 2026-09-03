
import logging

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

from crm_api.models import BoutiqueSettings, CustomerMessage

logger = logging.getLogger(__name__)

_cache = {}


def log_backend(message):
    logger.info(
        "customer message [%s] to %s for order %s: %s",
        message.template_key, message.to_number,
        message.order.order_id, message.body,
    )
    return ''


def get_backend():

    path = getattr(settings, 'CUSTOMER_MESSAGE_BACKEND', '') or ''
    if not path:
        return None
    if path not in _cache:
        try:
            _cache[path] = import_string(path)
        except ImportError:
            logger.exception("CUSTOMER_MESSAGE_BACKEND %r is not importable", path)
            _cache[path] = log_backend
    return _cache[path]


def _deliver(message):
    try:
        message.provider_message_id = get_backend()(message) or ''
        message.status = 'SENT'
    except Exception as exc:  # noqa: BLE001 - any transport failure is just a failed message
        logger.exception("customer message %s failed", message.pk)
        message.status = 'FAILED'
        message.error = str(exc)

    message.save(update_fields=['provider_message_id', 'status', 'error'])


def send_customer_message(order, template_key, body, sent_by=None):
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
    if get_backend() is not None:
        transaction.on_commit(lambda: _deliver(message))
    return message
