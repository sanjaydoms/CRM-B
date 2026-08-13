"""Where a 500 goes, now that it goes anywhere at all.

Until this module existed an unhandled exception reached nobody. DEBUG is False
in production so the traceback was not rendered, ADMINS is empty so Django's
default mail_admins handler had no recipient, and there was no LOGGING config,
so the only trace of a crash was gunicorn's stderr on Render -- rotated away in
days and read by no one. The first anyone heard of a broken endpoint was a
boutique owner saying "it isn't working".

Capture hangs off django.core.signals.got_request_exception, NOT off DRF's
EXCEPTION_HANDLER, and that is the whole point of this module's shape.

Hooking DRF only saw DRF. crm_api/tracking_views.order_tracking (the public
customer tracking page) and tenants/views.demo_request are plain Django views,
and TenantHeaderMiddleware runs before any view at all -- none of those go
through DRF dispatch, so a 500 in any of them was recorded nowhere and the
console went on reporting 'healthy' while every tracking link a boutique had
sent out returned an error page.

got_request_exception fires from django.core.handlers.exception.
response_for_exception, which every request path funnels through:
convert_exception_to_response wraps each middleware and the view chain, so a
plain view, a DRF view and a middleware all land there. Django's known-4xx
branches (Http404, PermissionDenied, BadRequest, SuspiciousOperation) return
before the signal, so only genuine 500s reach us.

Exactly once for a DRF exception, too. DRF's handle_exception calls the
EXCEPTION_HANDLER and, when it returns None, calls raise_uncaught_exception,
which re-raises -- so the exception leaves dispatch and gets converted by
Django, firing the signal. If platform_exception_handler ALSO recorded, every
DRF 500 would be counted twice while every plain-view 500 was counted once, and
`count` -- the only signal for which bug matters -- would be a comparison
between two different units. So it records nothing; see the bottom of the file.

Three rules shape everything below:

  * Record only what Django could *not* answer. Expected client errors -- the
    4xx DRF renders itself -- are the API working, not the API breaking.
  * One row per bug, not one row per crash. See _fingerprint.
  * Never raise. A failure in here would replace the original 500 with a
    different one and lose the thing worth keeping.
"""

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

#: BASE_DIR is not enough to decide a frame is ours: the virtualenv lives at
#: BASE_DIR/.venv, so every Django and DRF frame is "inside the project" by that
#: test. These markers are what actually separates our code from vendored code.
_VENDOR_MARKERS = ('/site-packages/', '/dist-packages/', '/.venv/')

#: Enough of the exception's own words to recognise it, bounded because a
#: database error can carry an entire failing statement.
_MESSAGE_LIMIT = 2000

#: How many distinct boutiques ErrorEvent.boutiques will name before it stops
#: growing. Past twenty the answer to "who does this affect" is "the platform",
#: and the exact roll call has stopped being the useful fact -- while an
#: unbounded list on a row that is updated on every single occurrence is a
#: JSON blob that grows with the tenant count forever.
_BOUTIQUE_LIST_LIMIT = 20


def _normalise_path(path):
    """Collapse the identities out of a request path.

    /api/orders/41/ and /api/orders/93/ are the same endpoint failing the same
    way. Fingerprinting the raw path files one row per order, and a single
    broken endpoint hit across a day's order book then buries every other
    problem in the feed -- which is the exact failure ErrorEvent's grouping
    exists to prevent.

    ponytail: only integers and UUIDs are collapsed, which covers every path
    parameter this project actually has (DRF routers use numeric pks; the only
    other converters in the URLconf are a tracking token and a schema name, and
    a per-boutique breakdown of a console crash is worth keeping). Add a rule
    here if a slug-shaped identifier ever appears in a path.
    """
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
    """The traceback with the vendor frames dropped, innermost last.

    A raw traceback here is twenty frames of wsgi, middleware and DRF dispatch
    wrapped around the two lines that are actually wrong, identical on every
    entry in the feed. Keeping only our own frames means the line that broke is
    the last line on screen rather than the one that scrolled off it.
    """
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
    """The identity of a *bug*: exception class, endpoint, and where it broke.

    The frame contributes file and function but deliberately not the line
    number. A line number makes the fingerprint move whenever anything above the
    bug is edited, so the same unfixed bug reappears as a brand new error after
    every unrelated deploy and its count resets to one -- and count is the whole
    signal for which problem matters. File and function stay put across edits.

    sha1 because it is short and stable, not for any security property; nothing
    here is a secret and nothing verifies it.
    """
    site = f'{frames[-1][0]}:{frames[-1][2]}' if frames else ''
    raw = f'{type(exc).__name__}|{normalised_path}|{site}'
    return hashlib.sha1(raw.encode()).hexdigest()


def _record(exc, request):
    """Upsert one ErrorEvent for this crash. Called inside a try in the handler."""
    # Imported here rather than at module scope so `core` stays importable
    # without the app registry being ready; core is imported by permission and
    # role code that runs very early.
    from superadmin.models import ErrorEvent

    path = getattr(request, 'path', '') or ''
    normalised = _normalise_path(path)
    frames = _project_frames(exc)
    fingerprint = _fingerprint(exc, normalised, frames)

    user = getattr(request, 'user', None)
    username = getattr(user, 'username', '') if getattr(user, 'is_authenticated', False) else ''

    # Read the schema before entering the public context below, or every error
    # is filed against 'public' and the feed cannot say which boutique broke.
    boutique = connection.schema_name
    if boutique == get_public_schema_name():
        boutique = ''

    traceback_text = '\n'.join(
        f'{name}:{lineno} in {func}\n    {line}' for name, lineno, func, line in frames)

    # Everything reaching here is a 500 in front of a real user, so 'high' is
    # the floor rather than the middle of the scale. A django.db.Error is worse
    # than that: it is either a constraint the code does not know about -- so
    # writes are being lost -- or the database itself, which in a single-database
    # multi-tenant deployment is every boutique at once. 'medium' and 'low'
    # exist for an operator to downgrade something to during triage, which is
    # also why severity is set on create only and left alone afterwards.
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

    # ErrorEvent is a SHARED_APPS model and lives only in public, but the
    # request that crashed is almost always a boutique's, so the connection is
    # pointed at that boutique's schema right now. Writing from here without
    # switching fails with "relation superadmin_errorevent does not exist" --
    # or, worse, would find a same-named table in the tenant schema and scatter
    # the platform's error feed across fifty boutiques. schema_context restores
    # the previous tenant in its own __exit__ (django_tenants/utils.py), so the
    # request's schema is intact for anything that runs after this.
    with schema_context(get_public_schema_name()), transaction.atomic():
        # The atomic() is what makes the boutiques append below race-free, and
        # it is doing real work rather than decorating. update_or_create takes
        # SELECT ... FOR UPDATE on the row inside its own atomic block; nested
        # atomic is a savepoint, so that row lock is held until THIS block
        # commits rather than being dropped the moment update_or_create
        # returns. A concurrent worker recording the same fingerprint therefore
        # blocks until it can read the list we just wrote, instead of both of
        # them reading the same old list and one append being lost.
        event, _ = ErrorEvent.objects.update_or_create(
            fingerprint=fingerprint,
            # count as an F() expression rather than obj.count + 1: gunicorn
            # runs two workers with four threads each, and a read-modify-write
            # loses occurrences exactly when an error is firing fast enough to
            # be worth counting.
            defaults=dict(
                shared,
                count=F('count') + 1,
                # A bug that comes back is not resolved. 'ignored' is a standing
                # decision about a known-noisy error and must survive a
                # recurrence, or it can never be made to stick; 'acknowledged'
                # means someone is already on it. Only 'resolved' is a claim the
                # recurrence disproves.
                status=Case(When(status='resolved', then=Value('new')),
                            default=F('status')),
            ),
            # resolved_by/resolved_at are left as they were on a reopen: "closed
            # by Anita on the 1st, back on the 12th" is the useful reading.
            create_defaults=dict(shared, count=1, status='new', severity=severity,
                                 boutiques=[boutique] if boutique else []),
        )

        # `boutique` is overwritten by every occurrence, so on its own it says
        # "most recently seen in" while the model index and the console's search
        # column present it as THE affected boutique. One bug hitting forty
        # boutiques reported the fortieth and made the other thirty-nine
        # unattributable -- which is exactly the question a platform error feed
        # exists to answer. `boutiques` accumulates instead, so the column can
        # stop pretending.
        seen = list(event.boutiques or [])
        if boutique and boutique not in seen and len(seen) < _BOUTIQUE_LIST_LIMIT:
            seen.append(boutique)
            event.boutiques = seen
            # update_fields so this cannot write back the unresolved F()
            # expression sitting on event.count from the upsert above.
            event.save(update_fields=['boutiques'])


def _on_request_exception(sender, request=None, **kwargs):
    """got_request_exception receiver. Every 500 in the project arrives here.

    The signal carries no exception -- it is sent from inside the `except`
    block in response_for_exception, so sys.exc_info() is the one being
    handled. That is also why this must not be called from anywhere else.
    """
    exc = sys.exc_info()[1]
    if exc is None:
        return
    try:
        _record(exc, request)
    except Exception:
        # A crash inside the crash handler replaces the original 500 with a
        # different, more confusing one and loses the thing worth keeping.
        # Nothing this module does is worth that. This also covers the
        # fresh-database case: before superadmin's migration has run the table
        # does not exist, and the site must still answer.
        logger.exception('could not record unhandled exception %r', exc)


def capture_middleware(get_response):
    """Not middleware. The boot hook that connects the receiver above.

    DO NOT REMOVE THE MIDDLEWARE ENTRY. It looks unused because it declines to
    join the chain, and deleting it silently switches off every ErrorEvent in
    the platform.

    The receiver has to be connected before the first request and `core` is not
    an installed app, so it has no AppConfig.ready() to do it from. MIDDLEWARE
    is the one list Django imports at handler construction -- guaranteed once
    per worker, before any request -- which is all that is needed here.

    MiddlewareNotUsed is Django's own way of saying "imported, not wanted in the
    chain": load_middleware discards the adapted handler and continues, so this
    adds no frame, no per-request work, and no async/sync adaptation. It also
    settles the positioning question -- got_request_exception fires for the
    whole request stack including TenantHeaderMiddleware, so there is no
    ordering this could be wrong at, which a process_exception middleware could
    not have claimed (process_exception only ever sees view exceptions, never
    another middleware's).
    """
    got_request_exception.connect(
        _on_request_exception,
        # Idempotent: the test client builds a fresh handler per settings
        # override, and a second connect would file every crash twice.
        dispatch_uid='core.exceptions.capture',
    )
    raise MiddlewareNotUsed('registration only; capture is via got_request_exception')


def platform_exception_handler(exc, context):
    """DRF's exception handler, unchanged. Deliberately records nothing.

    Still wired in as REST_FRAMEWORK['EXCEPTION_HANDLER'] and still worth
    naming, because the tempting edit is to put _record() back here.

    Do not. When this returns None DRF calls raise_uncaught_exception, the
    exception leaves dispatch, and Django's convert_exception_to_response fires
    got_request_exception -- so _on_request_exception has already got it.
    Recording here as well would count every DRF 500 twice and every plain-view
    or middleware 500 once.
    """
    return drf_exception_handler(exc, context)
