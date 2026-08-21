from crm_api.models import Order

# The one definition of "off the boutique's floor", imported rather than
# restated. This module held its own literal ('Shipped', 'Delivered') and
# superadmin/metrics.py carried a comment claiming there was now a single
# definition -- there were two that happened to agree. Agreeing today is the
# whole danger: a status added to the settled set in services.py would silently
# leave get_active_orders() below still counting it as active, and the comment
# would still say it could not.
#
# No cycle: services.py reaches crm_api.models, core.roles and
# domains.orders.{notifications,messaging,tracking}, none of which import this
# module. crm_api/views.py already imports both.
from domains.orders.services import _SETTLED_ORDER_STATUSES

# Mirrors every relation OrderSerializer reads. 'stage_histories' was missing and
# cost one extra query per order.
ORDER_SELECT_RELATED = ('customer', 'tailor', 'master', 'customer__measurements')
ORDER_PREFETCH = (
    'stages',
    'stages__performed_by',
    'stages__assigned_to',
    'activities',
    'activities__user',
    'stage_histories',
    # OrderSerializer nests the per-dress spec now; without these an order list
    # is one extra query per garment, and the wizard writes several per order.
    'garment_jobs',
    'garment_jobs__template',
    'garment_jobs__materials',
)


class OrderRepository:
    @staticmethod
    def summary_queryset():
        """Rows for OrderSummarySerializer -- stages only, no activity log."""
        return Order.objects.select_related('customer', 'tailor', 'master').prefetch_related(
            'stages', 'stages__performed_by', 'stages__assigned_to',
            # OrderSummarySerializer names the garments now, and it reads them
            # off the jobs. Without these that is two queries per order on a
            # dashboard that lists every open one.
            'garment_jobs', 'garment_jobs__template',
        ).order_by('-order_date')

    @staticmethod
    def base_queryset():
        return Order.objects.select_related(*ORDER_SELECT_RELATED).prefetch_related(*ORDER_PREFETCH)

    @staticmethod
    def get_all():
        return OrderRepository.base_queryset().order_by('-order_date')

    @staticmethod
    def get_by_id(order_id):
        return OrderRepository.base_queryset().filter(id=order_id).first()

    @staticmethod
    def get_active_orders():
        return OrderRepository.get_all().exclude(order_status__in=_SETTLED_ORDER_STATUSES)
