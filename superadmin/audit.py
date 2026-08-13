"""Writing and reading the console's audit trail.

One function the console calls -- `record()` -- and one the console reads with.
Everything about this module exists to make the first promise true: an audit
write must never be the reason an administrator's action fails, and must never
disappear without a trace either.

The two halves of that promise pull against each other, so both are handled
explicitly below: `record()` catches everything (the action is what matters,
not its receipt) but logs at ERROR with the traceback, so a broken audit trail
shows up in the service log rather than as a suspiciously quiet history page.
"""

import logging

from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context

# The IP rules are subtle and were learned from a 500 on a public endpoint --
# see the docstring on _client_ip. Importing rather than restating them means a
# fix there is a fix here too.
from tenants.views import _client_ip

from .models import AuditLog

logger = logging.getLogger(__name__)

#: Read from the model so the two cannot drift when a column is widened.
_MAX = {name: AuditLog._meta.get_field(name).max_length
        for name in ('actor', 'action', 'target', 'boutique', 'user_agent')}

DEFAULT_LIMIT = 100
#: A ceiling on the reader, not a preference. The console paginates; this is
#: what stops a `?limit=` in a URL from selecting a million rows.
MAX_LIMIT = 500


def _fit(value, field):
    """Clip a string to its column, defensively.

    A value longer than the column raises DataError, which `record()` would
    then swallow -- so the whole entry would be lost over a long User-Agent
    header or an unexpectedly long target. A clipped string is a worse record
    than a full one and a far better record than none.
    """
    return ('' if value is None else str(value))[:_MAX[field]]


def record(request, action, target='', boutique='', before=None, after=None, reason=''):
    """Write one audit entry. Returns the AuditLog, or None if it could not be written.

    `action` should be one of AuditLog.ACTIONS. `target` is whatever was acted
    on -- a schema name, a username, a flag key -- and `boutique` is the schema
    the action concerned, where it concerned one. `before`/`after` are anything
    JSON-serialisable; pass the fields that changed, not the whole object, and
    never a password hash or a token (see superadmin/datasets.py for the same
    rule on the read side).

    For `console.login_failed` there is no authenticated user, so `actor` comes
    out as the empty string; pass the attempted username as `target`.

    Never raises. An audit write that fails must not take the suspension or the
    password reset that triggered it down with it -- but the failure is logged
    with its traceback, because an audit trail that stops recording and says
    nothing is worse than no audit trail at all: it still looks authoritative.
    """
    try:
        # AuditLog is a SHARED_APPS model: the table exists in public and
        # nowhere else. Console requests are already pinned to public by
        # tenants/middleware.py, but that is not the only caller. The console
        # reaches *into* a boutique's schema to do its work (schema_context in
        # metrics.py, datasets.py, and any view that resets a user's password),
        # and a record() called from inside one of those blocks would aim the
        # INSERT at a schema with no superadmin_auditlog in it. That fails with
        # ProgrammingError, which the except below would swallow -- so exactly
        # the sensitive actions worth auditing would be the ones silently not
        # audited. Pinning here unconditionally costs a deferred `SET
        # search_path` and removes the whole class of mistake, rather than
        # asking every future caller to remember where the connection is.
        #
        # The savepoint is for the caller's sake, not ours: if record() is
        # called inside a transaction.atomic() block, a failed INSERT marks the
        # whole transaction for rollback, and catching the exception does not
        # heal it -- the caller's own commit would then fail. The savepoint
        # confines the damage to this statement. (Nothing sets ATOMIC_REQUESTS,
        # so in the common case this is the autocommit BEGIN/COMMIT anyway.)
        with schema_context(get_public_schema_name()), transaction.atomic():
            return AuditLog.objects.create(
                # Nested getattr because both halves can be absent: a plain
                # HttpRequest that never met AuthenticationMiddleware has no
                # `user` at all, and AnonymousUser has a blank `username`.
                # Neither is worth losing the entry over -- an action recorded
                # with no actor still says it happened.
                actor=_fit(getattr(getattr(request, 'user', None), 'username', ''), 'actor'),
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
    """The most recent entries, newest first, as a list.

    A list rather than a queryset on purpose: a lazy queryset returned from
    inside schema_context would be evaluated by the caller after the connection
    had gone back to whatever schema it was on, which is the same failure
    record() guards against above. `limit` is what makes materialising it safe.

    Filtering and slicing are both done in the database -- the ordering is
    Meta.ordering and the three filters each have a covering index (see
    AuditLog.Meta.indexes), so this stays an index scan of at most `limit` rows
    however large the table gets.
    """
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
