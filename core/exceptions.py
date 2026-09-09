"""
Every way this product meets an error, recorded in one place.

Before this module grew past crashes it captured exactly one thing: an exception
that nothing caught, which reached Django's core handler and became a 500. That
is the rarest way this product fails. The common ways were all invisible:

  * 49 `except Exception` sites carry on after logging, so a boutique's order
    emails could fail for a week behind a clean Error Center;
  * 149 deliberate 4xx returns and 31 raised DRF exceptions never touch
    `got_request_exception`, because DRF handles them itself;
  * the middleware's own refusals -- suspension, a switched-off module,
    maintenance, a missing schema -- are `JsonResponse` returns, not exceptions,
    so the console could switch a module off and never see it bite;
  * a React crash in the boutique workspace happens in a browser the server
    never hears from.

All five now land in `superadmin.models.ErrorEvent`, separated by `kind` so the
crash feed stays a crash feed. The capture points are:

  crash     `got_request_exception`            (unchanged)
  handled   `ErrorEventLogHandler` on the root logger -- every `logger.exception`
            in the project, with no edit to the 49 call sites
  client    `platform_exception_handler`, already wired as DRF's EXCEPTION_HANDLER
  refusal   `record_refusal`, called by tenants.middleware
  frontend  `record_frontend`, called by the client-error ingest view

Two rules hold everywhere in here:

1. **Recording never raises into the caller.** A console that loses its error
   feed is bad; an error feed that turns a swallowed failure into a 500 is
   worse. Every entry point is wrapped, exactly like `superadmin.audit.record`.
2. **Recording never recurses.** Writing a row can itself fail and log, and that
   log would be captured, and so on. `_capturing` is the latch that stops it.
"""

import hashlib
import logging
import re
import sys
import threading
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

#: A handled exception produced no HTTP response -- the code swallowed it and
#: carried on -- so there is no status code to record. 0 says that, where 500
#: would be a lie and null would need a nullable column.
NO_RESPONSE = 0

#: Loggers whose exception records are already captured by another route.
#: `django.request` logs precisely the unhandled 500s that `got_request_exception`
#: has just recorded as crashes; capturing them here too would file every crash
#: twice, once with its traceback and once without.
_LOGGERS_ALREADY_CAPTURED = ('django.request', 'django.server', __name__)

#: Set while a row is being written, so that a failure inside the write -- which
#: logs, which would be captured, which would write a row -- stops here.
_capturing = threading.local()


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


def _fingerprint(exc_name, normalised_path, site, kind):
    """
    The identity of a bug, which is what makes this feed one row per problem
    rather than one row per occurrence.

    `kind` joins the formula for everything except a crash. Two reasons, and the
    exception matters as much as the rule:

    * Without it a `ValueError` that crashed `/api/orders/` and the same
      `ValueError` caught and logged on that path would share a row, and its
      `kind` would flip on every occurrence -- so the crash feed would gain and
      lose the bug depending on which fired last.
    * With it applied to crashes too, every ErrorEvent already in the database
      would be orphaned on deploy: the same bug would fingerprint differently,
      open a second row, and lose its count, its notes and its resolution. So
      crash keeps the original formula, byte for byte -- `kind` is prefixed only
      when it is not 'crash'.
    """
    raw = f'{exc_name}|{normalised_path}|{site}'
    if kind != 'crash':
        raw = f'{kind}|{raw}'
    return hashlib.sha1(raw.encode()).hexdigest()


def _frames_and_site(exc):
    """The in-project frames as text, and the last of them as a bug's address."""
    frames = _project_frames(exc)
    text = '\n'.join(
        f'{name}:{lineno} in {func}\n    {line}' for name, lineno, func, line in frames)
    site = f'{frames[-1][0]}:{frames[-1][2]}' if frames else ''
    return text, site


def _current_boutique():
    schema = connection.schema_name
    return '' if schema == get_public_schema_name() else schema


def _username(request):
    user = getattr(request, 'user', None)
    return getattr(user, 'username', '') if getattr(user, 'is_authenticated', False) else ''


def _write(*, kind, exception_type, message, traceback_text='', site='', path='',
           method='', status_code, boutique='', username='', severity, source=''):
    """
    The single writer. Every capture point funnels here; nothing else touches
    ErrorEvent. Callers must already hold the `_capturing` latch.
    """
    from superadmin.models import ErrorEvent

    normalised = _normalise_path(path or '')
    fingerprint = _fingerprint(exception_type, normalised, site, kind)

    shared = {
        'exception_type': (exception_type or 'Unknown')[:200],
        'message': (message or '')[:_MESSAGE_LIMIT],
        'traceback': traceback_text or '',
        'path': (path or '')[:300],
        'method': (method or '')[:10],
        'status_code': status_code,
        'boutique': boutique,
        'username': username,
        'source': (source or '')[:200],
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
            # `kind` and `severity` are set once, at creation, and never
            # updated: a row's kind is half its fingerprint, and re-deciding
            # severity on every occurrence would overwrite a triage decision.
            create_defaults=dict(shared, kind=kind, count=1, status='new',
                                 severity=severity,
                                 boutiques=[boutique] if boutique else []),
        )

        seen = list(event.boutiques or [])
        if boutique and boutique not in seen and len(seen) < _BOUTIQUE_LIST_LIMIT:
            seen.append(boutique)
            event.boutiques = seen
            event.save(update_fields=['boutiques'])
    return event


def _guarded(fn):
    """Never raise into the caller, and never recurse into ourselves."""
    def wrapper(*args, **kwargs):
        if getattr(_capturing, 'active', False):
            return None
        _capturing.active = True
        try:
            return fn(*args, **kwargs)
        except Exception:
            # logger.exception here would itself be captured by our own log
            # handler, except that the latch is still held -- which is the
            # entire point of holding it across this except block.
            logger.exception('could not record an error event')
            return None
        finally:
            _capturing.active = False
    wrapper.__name__ = getattr(fn, '__name__', 'wrapper')
    return wrapper


# --------------------------------------------------------------------------
# crash -- an exception nothing caught
# --------------------------------------------------------------------------

def _record(exc, request):
    """
    Unchanged in behaviour and in fingerprint from the version that only ever
    recorded crashes. Kept as a module-level name because the existing tests
    call it directly.
    """
    traceback_text, site = _frames_and_site(exc)
    boutique = _current_boutique()
    return _write(
        kind='crash',
        exception_type=type(exc).__name__,
        message=str(exc),
        traceback_text=traceback_text,
        site=site,
        path=getattr(request, 'path', '') or '',
        method=getattr(request, 'method', '') or '',
        status_code=500,
        boutique=boutique,
        username=_username(request),
        severity='critical' if isinstance(exc, DatabaseError) else 'high',
    )


def _on_request_exception(sender, request=None, **kwargs):
    exc = sys.exc_info()[1]
    if exc is None:
        return
    if getattr(_capturing, 'active', False):
        return
    _capturing.active = True
    try:
        _record(exc, request)
    except Exception:
        logger.exception('could not record unhandled exception %r', exc)
    finally:
        _capturing.active = False


def capture_middleware(get_response):
    got_request_exception.connect(
        _on_request_exception,
        dispatch_uid='core.exceptions.capture',
    )
    raise MiddlewareNotUsed('registration only; capture is via got_request_exception')


# --------------------------------------------------------------------------
# handled -- caught, logged, carried on
# --------------------------------------------------------------------------

class ErrorEventLogHandler(logging.Handler):
    """
    Turns every `logger.exception(...)` in the project into a visible row.

    A handler rather than 49 edits at the call sites, because the call sites are
    the part that keeps growing: this captures the ones written after today
    without anybody remembering to. The cost is that it sees only the failures
    somebody thought worth logging -- an `except Exception: pass` (there are a
    few, e.g. closing an SMTP connection) stays invisible, and no handler can
    fix that.

    Attached in settings.LOGGING at ERROR level, so a warning with exc_info is
    not filed as a product error.
    """

    def emit(self, record):
        if not record.exc_info:
            return
        if record.name.startswith(_LOGGERS_ALREADY_CAPTURED):
            return
        exc = record.exc_info[1]
        if exc is None:
            return
        record_exception(exc, source=record.name,
                         message=f'{record.getMessage()} -- {exc}')


@_guarded
def record_exception(exc, *, request=None, source='', message='', kind='handled',
                     severity=None, status_code=NO_RESPONSE):
    traceback_text, site = _frames_and_site(exc)

    if severity is None:
        # A swallowed database error still means a write may have been lost, so
        # it keeps the severity it would have carried as a crash. Everything
        # else is 'medium': the code chose to continue, so it is not an outage,
        # but somebody decided it was worth a log line and they were right.
        severity = 'critical' if isinstance(exc, DatabaseError) else 'medium'

    return _write(
        kind=kind,
        exception_type=type(exc).__name__,
        message=message or str(exc),
        traceback_text=traceback_text,
        site=site,
        path=getattr(request, 'path', '') or '',
        method=getattr(request, 'method', '') or '',
        status_code=status_code,
        boutique=_current_boutique(),
        username=_username(request),
        severity=severity,
        source=source,
    )


# --------------------------------------------------------------------------
# refusal -- a platform control said no
# --------------------------------------------------------------------------

@_guarded
def record_refusal(request, *, reason, message, status_code, boutique=''):
    """
    Called by tenants.middleware wherever it returns a JsonResponse instead of
    serving the request. There is no exception and no traceback: `reason` is the
    identity, so a suspended boutique and a switched-off module are separate
    rows rather than one row that keeps changing its mind.

    Volume: one UPDATE per refused request, onto a single deduped row however
    many requests arrive. At tens of boutiques that is nothing. The shape that
    would make it hot is a boutique left suspended while its app keeps polling;
    if that ever shows up in query stats, the answer is a counter table, not
    dropping the signal.
    """
    _mark_recorded(request)
    return _write(
        kind='refusal',
        exception_type=reason,
        message=message,
        site='',
        path=getattr(request, 'path', '') or '',
        method=getattr(request, 'method', '') or '',
        status_code=status_code,
        boutique=boutique or _current_boutique(),
        username=_username(request),
        # A refusal is the platform doing its job. It earns a row so the console
        # can watch its own controls bite, not an alarm.
        severity='low',
        source='tenants.middleware',
    )


# --------------------------------------------------------------------------
# client -- a 4xx the API returned on purpose
# --------------------------------------------------------------------------

@_guarded
def _record_client(exc, context, response):
    context = context if isinstance(context, dict) else {}
    request = context.get('request')
    view = context.get('view')

    _mark_recorded(request)
    return _write(
        kind='client',
        exception_type=type(exc).__name__,
        # The response's own words, not repr() of DRF's internals. Without this
        # an operator reads
        #   {'detail': ErrorDetail(string='Authentication credentials were not
        #    provided.', code='not_authenticated')}
        # where the useful part is the sentence inside it.
        message=_response_message(response) or str(exc),
        # The view, not a stack: two endpoints rejecting the same shape of input
        # are two different things to fix, and neither has a traceback worth
        # keeping. It is also what separates rows that share a path prefix.
        site=type(view).__name__ if view is not None else '',
        path=getattr(request, 'path', '') or '',
        method=getattr(request, 'method', '') or '',
        status_code=response.status_code,
        boutique=_current_boutique(),
        username=_username(request),
        severity='low',
        source=type(view).__name__ if view is not None else '',
    )


#: Set on a request once any capture point has filed it, so ClientErrorMiddleware
#: does not file the same 4xx a second time from the response side.
_RECORDED = '_error_event_recorded'


def _mark_recorded(request):
    """
    Mark both the DRF Request and the Django HttpRequest underneath it.

    DRF wraps the Django request, and `setattr` on the wrapper does not reach
    the wrapped object -- only attribute *reads* proxy through. So marking only
    what the exception handler was handed leaves ClientErrorMiddleware, which
    sees the Django request, believing nothing was recorded. Every raised 4xx
    was then filed twice: once by class name, once as its status.
    """
    for target in (request, getattr(request, '_request', None)):
        if target is None:
            continue
        try:
            setattr(target, _RECORDED, True)
        except Exception:
            pass


def platform_exception_handler(exc, context):
    """
    DRF's EXCEPTION_HANDLER, already wired in settings and until now a pure
    delegation.

    Records only when DRF produced a response. `None` means DRF did not
    recognise the exception and is about to re-raise it, which ends at
    `got_request_exception` and is filed as a crash -- recording here as well
    would file every 500 twice.
    """
    response = drf_exception_handler(exc, context)
    if response is not None and response.status_code >= 400:
        _record_client(exc, context, response)
    return response


#: Paths whose 4xx are somebody else's business. The ingest endpoint's own 400
#: ("nothing to report") is not a product error, and /admin/ 4xx are Django's
#: login flow rather than this API refusing anyone.
_UNRECORDED_PREFIXES = ('/api/client-errors/', '/admin/', '/static/', '/media/')


class ClientErrorMiddleware:
    """
    Records the 4xx that never raise.

    `platform_exception_handler` sees only *raised* exceptions -- the 31
    `raise ValidationError(...)` sites. The other 149 are plain
    `return Response({...}, status=400)`, which never reaches an exception
    handler because nothing was ever thrown. Without this, the Client tab would
    show a sixth of the client errors the product actually returns and look like
    the whole picture, which is worse than showing none.

    Ordered outside TenantHeaderMiddleware in settings.MIDDLEWARE so it also
    sees the refusals -- but those already filed themselves with a reason worth
    more than a status code, and they set the marker, so this leaves them alone.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (400 <= getattr(response, 'status_code', 0) < 500
                    and not getattr(request, _RECORDED, False)
                    and not request.path.startswith(_UNRECORDED_PREFIXES)):
                _record_returned(request, response)
        except Exception:
            logger.exception('could not record a returned client error')
        return response


def _view_name(request):
    match = getattr(request, 'resolver_match', None)
    func = getattr(match, 'func', None)
    cls = getattr(func, 'cls', None) or getattr(func, 'view_class', None)
    return getattr(cls, '__name__', '') or getattr(match, 'view_name', '') or ''


def _response_message(response):
    """
    The endpoint's own words, when it gave any. Never the whole body.

    DRF's shapes are {'detail': ErrorDetail(...)} for an APIException and
    {field: [ErrorDetail(...), ...]} for a serializer, and `str()` on either
    prints the repr rather than the sentence. Both are flattened here so the row
    reads like the message the caller actually received.
    """
    data = getattr(response, 'data', None)
    if isinstance(data, dict):
        for key in ('error', 'detail', 'message'):
            if data.get(key):
                return str(data[key])
        parts = []
        for field, value in data.items():
            first = value[0] if isinstance(value, (list, tuple)) and value else value
            parts.append(f'{field}: {first}')
        return '; '.join(parts)
    if isinstance(data, (list, tuple)) and data:
        return '; '.join(str(item) for item in data)
    return str(data) if data else ''


@_guarded
def _record_returned(request, response):
    view = _view_name(request)
    _mark_recorded(request)
    return _write(
        kind='client',
        # There is no exception class here, because nothing was raised. The
        # status is the only classification the response carries, and pretending
        # otherwise would put an invented exception name in front of an operator.
        exception_type=f'HTTP {response.status_code}',
        message=_response_message(response),
        site=view,
        path=request.path,
        method=getattr(request, 'method', '') or '',
        status_code=response.status_code,
        boutique=_current_boutique(),
        username=_username(request),
        severity='low',
        source=view,
    )


# --------------------------------------------------------------------------
# frontend -- a React crash, reported by the browser
# --------------------------------------------------------------------------

#: A browser stack is not this project's source, so none of the frame-trimming
#: above applies to it. It is stored as text and capped.
_FRONTEND_STACK_LIMIT = 4000


@_guarded
def record_frontend(request, *, name, message, stack='', route=''):
    stack = (stack or '')[:_FRONTEND_STACK_LIMIT]
    _mark_recorded(request)
    return _write(
        kind='frontend',
        exception_type=name or 'Error',
        message=message or '',
        traceback_text=stack,
        # The first stack line is the throw site. Without it every crash in one
        # component collapses into a single row, because a React error message
        # is usually the same sentence wherever it is raised.
        site=stack.strip().splitlines()[0].strip()[:120] if stack.strip() else '',
        path=route or '',
        status_code=NO_RESPONSE,
        boutique=_current_boutique(),
        username=_username(request),
        # The user of that boutique got a blank page. That is not 'low'.
        severity='high',
        source='browser',
    )
