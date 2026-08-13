"""Reading a boutique's numbers from outside the boutique.

Every business table lives inside that boutique's own Postgres schema, so there
is no join, no aggregate and no queryset that spans them: the only way to count a
tenant's orders is to enter its schema and count them there. That is what makes
this module exist rather than a couple of annotations on the tenant queryset.

One definition, two readers -- the API in views.py and the Django admin
changelist (tenants/admin.py). They showed different numbers when this logic was
written twice.

Money is reported twice on purpose. `revenue` is BOOKED -- the sum of
total_amount, what the boutique has written down as owed to it. `collected` is
CASH -- the sum of amount_paid, which crm_api.views._reconcile_payment makes the
authoritative figure (it clamps paid into [0, total_amount] and forces
advance_paid <= paid). One number cannot mean both, and a console that shows only
the first reports a boutique that has invoiced a fortune and banked nothing as
its best customer.
"""

import logging
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from django_tenants.utils import get_public_schema_name

# tenant_scope rather than schema_context/tenant_context, for the reason written
# up at length in schemas.py: django_tenants sets `search_path = schema, public`
# without checking the schema exists, Postgres silently skips a missing entry,
# and every query then answers from `public`. For this module that is not a
# crash, it is a WRONG NUMBER that looks right -- a boutique whose schema was
# never created would report the platform console's own superuser as its staff
# count, and `healthy: True` beside it. The try/except below cannot see that,
# because nothing raises. tenant_scope raises MissingSchema instead.
from .schemas import MissingSchema, tenant_scope

logger = logging.getLogger(__name__)

#: Order statuses that mean the garment is off the boutique's floor. Everything
#: else counts as open work.
#:
#: Imported rather than restated, and imported from the boutique's own service
#: layer rather than declared here, because this used to read
#: ('Delivered', 'Cancelled') and was wrong twice over. 'Cancelled' is not a
#: value Order.order_status can hold at all -- the vocabulary is the eight
#: statuses in OrderViewSet.CLIENT_STATUSES, and the only 'Cancelled' literals in
#: the tree are on Appointment and the inventory models -- so half of this tuple
#: matched nothing. Worse, 'Shipped' was missing, so every shipped garment was
#: counted as open work by the console forever while the boutique's own screens
#: (refresh_staff_availability, which frees the tailor) had already settled it.
#: Two definitions of "done" is what produced that; there is now one.
#:
#: The name is private in the module that owns it. Importing it anyway is
#: deliberate: a public copy here is a second definition, which is the defect.
from domains.orders.services import _SETTLED_ORDER_STATUSES as CLOSED_ORDER_STATUSES

EMPTY = {
    'staff': None, 'customers': None, 'orders': None,
    'open_orders': None, 'revenue': None, 'collected': None, 'last_order': None,
}

#: Payment labels _reconcile_payment can write. Seeded so a boutique with no
#: unpaid orders still renders a "Pending: 0" cell rather than dropping the
#: column. They are if/elif branches over there rather than a constant, so this
#: is a copy -- if it drifts, the buckets simply stop being pre-seeded, they do
#: not go wrong: _buckets() reports whatever the rows actually say.
PAYMENT_STATUSES = ('Pending', 'Partially Paid', 'Paid')

#: Why the overdue count cannot be read at face value. Travels with the number
#: rather than living in the frontend, so whoever renders it cannot render it
#: bare.
OVERDUE_CAVEAT = (
    'estimated_delivery defaults to order_date + 15 days when an order is '
    'created without one, so this counts dates the system invented alongside '
    'dates the boutique actually promised. Treat it as an upper bound.'
)


def _buckets(queryset, field, seed=()):
    """GROUP BY `field`, as a dict, with `seed` keys guaranteed present.

    Seeded keys make the payload's shape independent of the data, so a console
    panel does not gain and lose columns as a boutique's orders move. Values the
    seed does not mention are still reported: order_status was writable to any
    string before OrderViewSet grew its allowlist, so rows holding something
    outside the vocabulary exist and must not be silently dropped from a total.

    Plain Count('id') rather than distinct=True: unlike the boutique dashboard's
    version this queryset carries no join to `stages`, which is what multiplied
    every bucket there by fifteen.
    """
    counts = {value: 0 for value in seed}
    for row in queryset.values(field).annotate(n=Count('id')):
        counts[row[field]] = row['n']
    return counts


def tenant_metrics(tenant):
    """Usage figures for one boutique, read from inside its own schema.

    A handful of aggregates in a single schema switch, memoised on the instance
    because the admin changelist asks for each column separately and would
    otherwise repeat the whole thing once per column per row.

    A tenant whose schema is missing or half-migrated reports EMPTY rather than
    raising. That case is exactly what an administrator opens this page to find,
    and one broken boutique must not take the list of all the others down with
    it -- the API reports it as `healthy: false` so it is visible rather than
    silently zero.
    """
    cached = getattr(tenant, '_metrics', None)
    if cached is not None:
        return cached

    metrics = dict(EMPTY, healthy=True)
    if tenant.schema_name == get_public_schema_name():
        # Not a boutique: this is the registry schema the console itself runs in.
        metrics['healthy'] = False
    else:
        # Imported before the try, not inside it. These are console-side code
        # faults if they fail -- a rename, an unrelated import error -- and
        # reporting a code fault as "this boutique is unreadable" points the
        # administrator at the boutique they were already worried about.
        from django.contrib.auth.models import User

        from crm_api.models import Customer, Order

        try:
            # Savepoint, for the half-migrated case tenant_scope cannot see: the
            # schema is there so the guard passes, and then a missing table
            # raises. Swallowing that leaves the connection ABORTED inside any
            # enclosing atomic(), so every later statement dies with "current
            # transaction is aborted" -- one broken boutique taking down the
            # whole page this except was written to protect, which is the exact
            # failure superadmin/schemas.py for_each_tenant wraps for.
            with transaction.atomic(), tenant_scope(tenant):
                totals = Order.objects.aggregate(
                    orders=Count('id'), revenue=Sum('total_amount'),
                    collected=Sum('amount_paid'), last_order=Max('order_date'),
                )
                metrics = {
                    'staff': User.objects.filter(is_active=True).count(),
                    'customers': Customer.objects.count(),
                    'orders': totals['orders'],
                    'open_orders': Order.objects.exclude(
                        order_status__in=CLOSED_ORDER_STATUSES).count(),
                    'revenue': totals['revenue'],
                    'collected': totals['collected'],
                    'last_order': totals['last_order'],
                    'healthy': True,
                }
        except MissingSchema as exc:
            # Logged rather than only counted. `healthy: false` tells the
            # administrator the boutique could not be read; only this line tells
            # them the schema is absent, which is a registry repair rather than
            # a migration.
            logger.warning('%s', exc)
            metrics = dict(EMPTY, healthy=False)
        except Exception:
            metrics = dict(EMPTY, healthy=False)

    tenant._metrics = metrics
    return metrics


def operational_metrics(tenant):
    """What a boutique's order book is doing right now, for the Orders Monitor.

    Separate from tenant_metrics rather than folded into it because the two are
    read on different screens at different rates: tenant_metrics runs once per
    boutique on every overview and every admin changelist row, and this runs when
    someone opens one boutique's monitor. Six grouped queries per boutique on the
    landing page would be six times the schema switching for numbers nobody is
    looking at.

    Every figure is a database aggregate. Nothing here fetches rows: a boutique's
    order table is the largest thing in its schema and counting it in Python is
    how a console page becomes a memory incident.

    Same failure contract as tenant_metrics -- an unreadable schema answers
    `healthy: false` rather than raising, so one broken boutique does not take
    the monitor down. That contract covers ONE BOUTIQUE'S DATA and nothing else:
    a fault in the console's own code raises, deliberately, because the
    administrator needs to be told the console is broken rather than told the
    platform is.
    """
    empty = {
        'orders': None, 'by_order_status': {}, 'by_payment_status': {},
        'created': {'today': None, 'week': None, 'month': None},
        'overdue': {'count': None, 'caveat': OVERDUE_CAVEAT},
        'queued_messages': None,
        'by_production_status': {}, 'by_stage': {},
    }
    if tenant.schema_name == get_public_schema_name():
        return dict(empty, healthy=False)

    # Read the console's own code BEFORE the try, so a fault in it is a fault.
    # These two lines used to sit inside the per-tenant except, which meant a
    # rename of CLIENT_STATUSES, or any unrelated import error anywhere in
    # crm_api.views' large import graph, was reported to the administrator as
    # every boutique on the platform having an unreadable schema. That sends
    # someone to look at the database during what is a deploy problem. The
    # except below is for one boutique's data; nothing here is one boutique's
    # data.
    from crm_api.models import CustomerMessage, Order
    from crm_api.views import OrderViewSet

    # Sorted for a stable payload; the pipeline order is presentation and
    # belongs to whoever draws the columns. Read once here rather than inside
    # the schema for the same reason as the imports.
    order_status_seed = sorted(OrderViewSet.CLIENT_STATUSES)

    try:
        # Savepoint for the same reason as tenant_metrics above.
        with transaction.atomic(), tenant_scope(tenant):
            orders = Order.objects.all()

            # Boundaries in the active timezone, not UTC-by-accident: "created
            # today" is a question about the boutique's day. TIME_ZONE is UTC
            # today, so these coincide -- computing them properly is what keeps
            # that a coincidence rather than an assumption. Aware datetime
            # boundaries rather than __date lookups so the order_date index is
            # still usable; a function on the column would not be.
            today = timezone.localdate()
            current = timezone.get_current_timezone()

            def day_start(day):
                return datetime.combine(day, time.min, tzinfo=current)

            # ISO week: Monday. The boutiques run Monday-to-Saturday weeks.
            week = today - timedelta(days=today.weekday())

            # One pass for the four counts. The alternative is four sequential
            # scans of the same table across a schema switch, which is four
            # round trips to a database that is a network hop away.
            counted = orders.aggregate(
                orders=Count('id'),
                today=Count('id', filter=Q(order_date__gte=day_start(today))),
                week=Count('id', filter=Q(order_date__gte=day_start(week))),
                month=Count('id', filter=Q(order_date__gte=day_start(today.replace(day=1)))),
                # NULL estimated_delivery is excluded by the comparison itself,
                # which is the behaviour wanted: an order with no promised date
                # cannot be late against one.
                #
                # ponytail: estimated_delivery has no index, so this is a
                # sequential scan. Fine at a boutique's order volume and on a
                # page opened deliberately; add an index on
                # (estimated_delivery, order_status) if the monitor ever moves
                # onto a dashboard that polls.
                overdue=Count('id', filter=Q(estimated_delivery__lt=today)
                              & ~Q(order_status__in=CLOSED_ORDER_STATUSES)),
            )

            return {
                'orders': counted['orders'],
                # The vocabulary comes from the endpoint that enforces it rather
                # than from a ninth copy of the eight strings.
                'by_order_status': _buckets(orders, 'order_status', order_status_seed),
                'by_payment_status': _buckets(
                    orders, 'payment_status', PAYMENT_STATUSES),
                'created': {'today': counted['today'], 'week': counted['week'],
                            'month': counted['month']},
                'overdue': {'count': counted['overdue'], 'caveat': OVERDUE_CAVEAT},
                # Queued means written but not yet sent. There is no send worker
                # -- the owner presses send on their own phone via
                # CustomerMessage.whatsapp_url -- so a large number here is a
                # backlog of messages nobody has sent, not a stuck queue.
                'queued_messages': CustomerMessage.objects.filter(status='QUEUED').count(),
                'by_production_status': _buckets(orders, 'production_status'),
                # Open vocabulary: stage keys come from the workflow definition,
                # so these are not seeded. Bounded by the number of stages
                # (~15), not by the number of orders.
                'by_stage': _buckets(orders, 'current_stage_key'),
                'healthy': True,
            }
    except MissingSchema as exc:
        # See tenant_metrics: the count is not enough on its own, the reason is
        # what tells an administrator this is a registry repair.
        logger.warning('%s', exc)
        return dict(empty, healthy=False)
    except Exception:
        return dict(empty, healthy=False)


def platform_totals(tenants):
    """Roll the per-tenant figures up into the numbers across the whole product.

    Sums the same dictionaries the rows are built from rather than re-querying,
    so a total can never disagree with the rows underneath it. Unreadable tenants
    contribute nothing to the sums and are counted separately, because a total
    that quietly omits a boutique is worse than one that says it did.

    ponytail: O(tenants) schema switches, same ceiling as the changelist. Roll
    these into a public-schema table on a schedule if the tenant count reaches
    the hundreds.
    """
    totals = {'boutiques': 0, 'active': 0, 'suspended': 0, 'unreadable': 0,
              'staff': 0, 'customers': 0, 'orders': 0, 'open_orders': 0,
              'revenue': 0, 'collected': 0}
    for tenant in tenants:
        totals['boutiques'] += 1
        totals['active' if tenant.is_active else 'suspended'] += 1
        metrics = tenant_metrics(tenant)
        if not metrics['healthy']:
            totals['unreadable'] += 1
            continue
        for key in ('staff', 'customers', 'orders', 'open_orders', 'revenue',
                    'collected'):
            totals[key] += metrics[key] or 0
    return totals
