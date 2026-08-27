
import hashlib
import logging
import re
import sys
import traceback

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.core.signals import got_request_exception
from django.db import Error as DatabaseError
from django.db import connection, transaction
from django.db.models import Case, F, Value, When
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

_UUID = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

_VENDOR_MARKERS = ('/site-packages/', '/dist-packages/', '/.venv/')

_MESSAGE_LIMIT = 2000

_BOUTIQUE_LIST_LIMIT = 20


def _normalise_path(path):
    segments = []
    for segment in path.split('/'):
        if segment.isdigit():
            segments.append('<id>')
        elif _UUID.match(segment):
            segments.append('<uuid>')
        else:
            segments.append(segment)
    return '/'.join(segments)


def _project_frames(exc):
    root = str(settings.BASE_DIR)
    kept = []
    for frame in traceback.extract_tb(exc.__traceback__):
        filename = frame.filename
        if not filename.startswith(root):
            continue
        if any(marker in filename for marker in _VENDOR_MARKERS):
            continue
        kept.append((filename[len(root):].lstrip('/'), frame.lineno, frame.name,
                     (frame.line or '').strip()))
    return kept


def _fingerprint(exc, normalised_path, frames):
    site = f'{frames[-1][0]}:{frames[-1][2]}' if frames else ''
    raw = f'{type(exc).__name__}|{normalised_path}|{site}'
    return hashlib.sha1(raw.encode()).hexdigest()


def _record(exc, request):
    from superadmin.models import ErrorEvent

    path = getattr(request, 'path', '') or ''
    normalised = _normalise_path(path)
    frames = _project_frames(exc)
    fingerprint = _fingerprint(exc, normalised, frames)

    user = getattr(request, 'user', None)
    username = getattr(user, 'username', '') if getattr(user, 'is_authenticated', False) else ''

    boutique = connection.schema_name
    if boutique == get_public_schema_name():
        boutique = ''

    traceback_text = '\n'.join(
        f'{name}:{lineno} in {func}\n    {line}' for name, lineno, func, line in frames)

    severity = 'critical' if isinstance(exc, DatabaseError) else 'high'

    shared = {
        'exception_type': type(exc).__name__,
        'message': str(exc)[:_MESSAGE_LIMIT],
        'traceback': traceback_text,
        'path': path[:300],
        'method': getattr(request, 'method', '')[:10],
        'status_code': 500,
        'boutique': boutique,
        'username': username,
    }

    with schema_context(get_public_schema_name()), transaction.atomic():
        event, _ = ErrorEvent.objects.update_or_create(
            fingerprint=fingerprint,
            defaults=dict(
                shared,
                count=F('count') + 1,
                status=Case(When(status='resolved', then=Value('new')),
                            default=F('status')),
            ),
            create_defaults=dict(shared, count=1, status='new', severity=severity,
                                 boutiques=[boutique] if boutique else []),
        )

        seen = list(event.boutiques or [])
        if boutique and boutique not in seen and len(seen) < _BOUTIQUE_LIST_LIMIT:
            seen.append(boutique)
            event.boutiques = seen
            event.save(update_fields=['boutiques'])


def _on_request_exception(sender, request=None, **kwargs):
    exc = sys.exc_info()[1]
    if exc is None:
        return
    try:
        _record(exc, request)
    except Exception:
        logger.exception('could not record unhandled exception %r', exc)


def capture_middleware(get_response):
    got_request_exception.connect(
        _on_request_exception,
        dispatch_uid='core.exceptions.capture',
    )
    raise MiddlewareNotUsed('registration only; capture is via got_request_exception')


def platform_exception_handler(exc, context):
    return drf_exception_handler(exc, context)
