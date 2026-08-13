"""One box that finds anything on the platform.

An administrator on a support call has a name, a phone number or an order id and
no idea which boutique it belongs to -- that is the whole reason this exists.
Answering it means the same shape as the rest of this console: three tables in
the public schema queried once, and three per boutique queried inside each
schema, because Postgres will not join across them.

Everything the answer costs is bounded on purpose:

  * A term under MIN_TERM characters returns nothing at all. 'a' matches most of
    every table in every schema, so it is a full sweep of the platform that
    produces a page of noise; refusing it is cheaper than serving it.
  * Each type has a cap, filled across all boutiques rather than per boutique,
    and the loop stops switching schemas once all three per-boutique types are
    full.
  * The concatenated answer is capped again, so a caller asking for a large
    limit_per_type cannot turn one keystroke into a thousand-row payload.

ponytail: every match is an unindexed ILIKE, so each is a sequential scan of the
table it runs against -- fine for a boutique's staff and order book, and the
same ceiling superadmin/datasets.py already accepts for its per-table search.
The upgrade is pg_trgm GIN indexes on the handful of columns actually searched
here, not a search service.

ponytail: the per-type cap is filled in tenant order, so with fifty boutiques
and a cap of ten, a matching customer in the fortieth boutique can be crowded
out by earlier ones. Cutting the sweep short is the point -- and the real fix is
the cross-schema index this console keeps asking for (see superadmin/users.py),
not a larger cap.
"""

from django.contrib.auth.models import User
from django.db.models import Q
from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context

from .schemas import MissingSchema, tenant_scope
from .users import clamped_int

import logging

logger = logging.getLogger(__name__)

from crm_api.models import Customer, Order
from tenants.models import BoutiqueTenant

from .models import AuditLog, ErrorEvent

MIN_TERM = 2
DEFAULT_PER_TYPE = 10
MAX_PER_TYPE = 25
MAX_RESULTS = 100

#: Result order, and therefore what MAX_RESULTS cuts first. Boutiques and people
#: lead because they are what a caller is usually holding; the audit trail is
#: last because it is the one type an administrator arrives at deliberately,
#: through its own screen, rather than by typing a name into a search box.
TYPES = ('boutique', 'user', 'customer', 'order', 'error', 'audit')

#: Types that live inside a boutique's schema, in the order they are gathered.
TENANT_TYPES = ('user', 'customer', 'order')


def _hit(kind, ident, label, sublabel, schema='', boutique_name=''):
    """One result row.

    `id` is the handle the console acts on, not always a primary key: a user's
    is their username (what superadmin/users.py mutations take) and an order's
    is its order_id (what everyone quotes). Stringified so a Customer's UUID
    survives JSON.

    `key` is unique across the whole mixed list. Neither type nor id alone is:
    user 3 in one boutique and order 3 in another collide, and so do two
    customers with the same primary key in two schemas -- which is not exotic
    here, it is what a schema-per-tenant database does by design.
    """
    return {
        'type': kind,
        'id': str(ident),
        'label': label,
        'sublabel': sublabel,
        'boutique': schema,
        'boutique_name': boutique_name,
        'key': f'{kind}:{schema}:{ident}',
    }


def _boutique_hits(term, limit):
    public = get_public_schema_name()
    return [
        _hit('boutique', t.schema_name, t.name or t.schema_name,
             f'{t.owner_email} - {"active" if t.is_active else "suspended"}',
             t.schema_name, t.name)
        for t in BoutiqueTenant.objects.exclude(schema_name=public).filter(
            Q(name__icontains=term) | Q(schema_name__icontains=term)
            | Q(owner_email__icontains=term)).order_by('name')[:limit]
    ]


def _error_hits(term, limit, names):
    return [
        _hit('error', e.id, e.exception_type,
             f'{e.path} - seen {e.count}x - {e.get_status_display()}',
             e.boutique, names.get(e.boutique, ''))
        for e in ErrorEvent.objects.filter(
            Q(exception_type__icontains=term) | Q(message__icontains=term)
            | Q(path__icontains=term) | Q(username__icontains=term))[:limit]
    ]


def _audit_hits(term, limit, names):
    return [
        _hit('audit', a.id, f'{a.actor} - {a.get_action_display()}',
             f'{a.target or "-"} - {a.created_at:%Y-%m-%d %H:%M}',
             a.boutique, names.get(a.boutique, ''))
        for a in AuditLog.objects.filter(
            Q(actor__icontains=term) | Q(target__icontains=term)
            # `action` is matched as stored ('boutique.suspend'), which is also
            # how someone searching "suspend" spells it.
            | Q(action__icontains=term) | Q(reason__icontains=term))[:limit]
    ]


def _user_hits(tenant, term, limit):
    return [
        _hit('user', u.username, u.get_full_name() or u.username,
             f'{u.email or "no email"} - '
             f'{"active" if u.is_active else "deactivated"}',
             tenant.schema_name, tenant.name)
        for u in User.objects.filter(
            Q(username__icontains=term) | Q(email__icontains=term)
            | Q(first_name__icontains=term) | Q(last_name__icontains=term)
        ).order_by('username')[:limit]
    ]


def _customer_hits(tenant, term, limit):
    return [
        _hit('customer', c.id, f'{c.first_name} {c.last_name}'.strip(),
             c.mobile_number or c.email_address or '',
             tenant.schema_name, tenant.name)
        for c in Customer.objects.filter(
            Q(first_name__icontains=term) | Q(last_name__icontains=term)
            | Q(mobile_number__icontains=term)
            | Q(email_address__icontains=term)
        ).order_by('first_name', 'id')[:limit]
    ]


def _order_hits(tenant, term, limit):
    """Orders, matched on the customer as well as on the order itself.

    A support call names a person far more often than an order id, and the join
    is inside one schema so it costs nothing extra. The customer row matches too
    and both are returned -- which is the useful answer, not a duplicate: one
    opens the person, the other opens the garment they are asking about.
    """
    return [
        _hit('order', o.order_id, o.order_id,
             f'{o.customer.first_name} {o.customer.last_name} - '
             f'{o.order_status}',
             tenant.schema_name, tenant.name)
        for o in Order.objects.select_related('customer').filter(
            Q(order_id__icontains=term) | Q(tracking_number__icontains=term)
            | Q(customer__first_name__icontains=term)
            | Q(customer__last_name__icontains=term)
            | Q(customer__mobile_number__icontains=term)
        ).order_by('-order_date', 'order_id')[:limit]
    ]


def search(term, tenants, limit_per_type=DEFAULT_PER_TYPE):
    """Everything matching `term`, across the platform.

    `tenants` is the caller's tenant list (superadmin.views._boutiques()), so
    this module never decides which boutiques exist.

    Returns a flat list of hits grouped by type in TYPES order -- flat rather
    than a dict of lists because the console renders one ranked list, and
    grouping is a `groupby` on the client if it ever wants sections.
    """
    term = (term or '').strip()
    if len(term) < MIN_TERM:
        return []
    # ?limit_per_type=abc is a malformed URL, not a server error -- see
    # clamped_int. Shared with users.py rather than re-cast here.
    cap = clamped_int(limit_per_type, DEFAULT_PER_TYPE, 1, MAX_PER_TYPE)

    public = get_public_schema_name()
    boutiques = [t for t in tenants if t.schema_name != public]
    # Built from the list already in memory: ErrorEvent and AuditLog store a
    # schema name rather than a foreign key (they outlive what they describe),
    # and this is what lets their rows carry a readable boutique name without a
    # lookup each.
    names = {t.schema_name: t.name for t in boutiques}

    found = {name: [] for name in TYPES}

    # The console's own three tables. Not wrapped in a try: if the public schema
    # cannot be read, the console is not running at all, and swallowing that
    # would hide the failure behind an empty search box.
    with schema_context(public):
        found['boutique'] = _boutique_hits(term, cap)
        found['error'] = _error_hits(term, cap, names)
        found['audit'] = _audit_hits(term, cap, names)

    finders = {'user': _user_hits, 'customer': _customer_hits,
               'order': _order_hits}
    for tenant in boutiques:
        if all(len(found[name]) >= cap for name in TENANT_TYPES):
            # Every per-boutique bucket is full, so the remaining schemas can
            # only produce rows that would be discarded. This break is what
            # keeps a common term from costing one schema switch per boutique.
            break
        try:
            # tenant_scope, not tenant_context, and its own savepoint. Both
            # matter here and neither is defensive padding.
            #
            # A boutique with a registry row but no schema does not raise: it
            # resolves through search_path to `public`, where auth_user exists
            # because auth is a SHARED_APP -- so searching a ghost boutique for
            # "admin" returned the platform console's own superuser, labelled as
            # that boutique's staff. Confirmed against this database. The except
            # below could never have caught it, because nothing went wrong.
            #
            # And a query that genuinely fails inside an enclosing atomic()
            # aborts the transaction, so swallowing it here left every following
            # statement failing with "current transaction is aborted" -- one bad
            # boutique breaking search for the other forty-nine, which is what
            # this except exists to prevent.
            with transaction.atomic():
                with tenant_scope(tenant):
                    gathered = {
                        name: finders[name](tenant, term, cap - len(found[name]))
                        for name in TENANT_TYPES if cap > len(found[name])
                    }
        except MissingSchema as exc:
            logger.warning('%s', exc)
            continue
        except Exception as exc:
            logger.warning('Search skipped boutique %s: %s', tenant.schema_name, exc)
            continue
        # Merged only once the whole boutique has been read, which is not
        # bookkeeping -- it closes the half of the fallthrough that
        # tenant_scope alone does not.
        #
        # tenant_scope proves the SCHEMA exists. It cannot prove the schema has
        # TABLES, and a half-run migration leaves one that does not: auth is a
        # SHARED_APP, so `auth_user` still resolves through search_path to
        # public, and _user_hits returns the platform console's own accounts
        # while the next query (crm_api_customer, which is tenant-only) is the
        # one that finally errors. Extending `found` inside the with kept those
        # rows -- the platform superuser, labelled as that boutique's staff,
        # from a boutique the search had just decided it could not read.
        for name, hits in gathered.items():
            found[name].extend(hits)

    results = []
    for name in TYPES:
        results.extend(found[name])
    return results[:MAX_RESULTS]
