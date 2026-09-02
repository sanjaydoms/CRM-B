
import logging

from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context

from tenants.views import _client_ip

from .models import AuditLog

logger = logging.getLogger(__name__)

_MAX = {name: AuditLog._meta.get_field(name).max_length
        for name in ('actor', 'action', 'target', 'boutique', 'user_agent')}

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _fit(value, field):
    return ('' if value is None else str(value))[:_MAX[field]]


def record(request, action, target='', boutique='', before=None, after=None,
           reason='', actor=None):
    try:
        with schema_context(get_public_schema_name()), transaction.atomic():
            return AuditLog.objects.create(
                actor=_fit(
                    actor if actor is not None
                    else getattr(getattr(request, 'user', None), 'username', ''),
                    'actor'),
                action=_fit(action, 'action'),
                target=_fit(target, 'target'),
                boutique=_fit(boutique, 'boutique'),
                before=before,
                after=after,
                reason=reason or '',
                ip=_client_ip(request),
                user_agent=_fit(request.META.get('HTTP_USER_AGENT', ''), 'user_agent'),
            )
    except Exception:
        logger.exception('audit write failed: action=%r target=%r boutique=%r',
                         action, target, boutique)
        return None


def recent(boutique=None, actor=None, action=None, limit=DEFAULT_LIMIT):
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    with schema_context(get_public_schema_name()):
        entries = AuditLog.objects.all()
        if boutique:
            entries = entries.filter(boutique=boutique)
        if actor:
            entries = entries.filter(actor=actor)
        if action:
            entries = entries.filter(action=action)
        return list(entries[:limit])
