
import logging
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from django_tenants.utils import get_public_schema_name

from .schemas import MissingSchema, tenant_scope

logger = logging.getLogger(__name__)

from domains.orders.services import _SETTLED_ORDER_STATUSES as CLOSED_ORDER_STATUSES

EMPTY = {
    'staff': None, 'customers': None, 'orders': None,
    'open_orders': None, 'revenue': None, 'collected': None, 'last_order': None,
}

PAYMENT_STATUSES = ('Pending', 'Partially Paid', 'Paid')

OVERDUE_CAVEAT = (
    'estimated_delivery defaults to order_date + 15 days when an order is '
    'created without one, so this counts dates the system invented alongside '
    'dates the boutique actually promised. Treat it as an upper bound.'
)


def _buckets(queryset, field, seed=()):
    counts = {value: 0 for value in seed}
    for row in queryset.values(field).annotate(n=Count('id')):
        counts[row[field]] = row['n']
    return counts


def tenant_metrics(tenant):
    cached = getattr(tenant, '_metrics', None)
    if cached is not None:
        return cached

    metrics = dict(EMPTY, healthy=True)
    if tenant.schema_name == get_public_schema_name():
        metrics['healthy'] = False
    else:
        from django.contrib.auth.models import User

        from crm_api.models import Customer, Order

        try:
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
            logger.warning('%s', exc)
            metrics = dict(EMPTY, healthy=False)
        except Exception:
            metrics = dict(EMPTY, healthy=False)

    tenant._metrics = metrics
    return metrics


def operational_metrics(tenant):
    empty = {
        'orders': None, 'by_order_status': {}, 'by_payment_status': {},
        'created': {'today': None, 'week': None, 'month': None},
        'overdue': {'count': None, 'caveat': OVERDUE_CAVEAT},
        'queued_messages': None,
        'by_production_status': {}, 'by_stage': {},
    }
    if tenant.schema_name == get_public_schema_name():
        return dict(empty, healthy=False)

    from crm_api.models import CustomerMessage, Order
    from crm_api.views import OrderViewSet

    order_status_seed = sorted(OrderViewSet.CLIENT_STATUSES)

    try:
        with transaction.atomic(), tenant_scope(tenant):
            orders = Order.objects.all()

            today = timezone.localdate()
            current = timezone.get_current_timezone()

            def day_start(day):
                return datetime.combine(day, time.min, tzinfo=current)

            week = today - timedelta(days=today.weekday())

            counted = orders.aggregate(
                orders=Count('id'),
                today=Count('id', filter=Q(order_date__gte=day_start(today))),
                week=Count('id', filter=Q(order_date__gte=day_start(week))),
                month=Count('id', filter=Q(order_date__gte=day_start(today.replace(day=1)))),
                overdue=Count('id', filter=Q(estimated_delivery__lt=today)
                              & ~Q(order_status__in=CLOSED_ORDER_STATUSES)),
            )

            return {
                'orders': counted['orders'],
                'by_order_status': _buckets(orders, 'order_status', order_status_seed),
                'by_payment_status': _buckets(
                    orders, 'payment_status', PAYMENT_STATUSES),
                'created': {'today': counted['today'], 'week': counted['week'],
                            'month': counted['month']},
                'overdue': {'count': counted['overdue'], 'caveat': OVERDUE_CAVEAT},
                'queued_messages': CustomerMessage.objects.filter(status='QUEUED').count(),
                'by_production_status': _buckets(orders, 'production_status'),
                'by_stage': _buckets(orders, 'current_stage_key'),
                'healthy': True,
            }
    except MissingSchema as exc:
        logger.warning('%s', exc)
        return dict(empty, healthy=False)
    except Exception:
        return dict(empty, healthy=False)


def platform_totals(tenants):
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
