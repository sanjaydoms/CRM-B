from crm_api.models import Order

# Mirrors every relation OrderSerializer reads. 'stage_histories' was missing and
# cost one extra query per order.
ORDER_SELECT_RELATED = ('customer', 'tailor', 'master', 'customer__measurements')
ORDER_PREFETCH = (
    'stages',
    'stages__performed_by',
    'activities',
    'activities__user',
    'stage_histories',
)


class OrderRepository:
    @staticmethod
    def summary_queryset():
        """Rows for OrderSummarySerializer -- stages only, no activity log."""
        return Order.objects.select_related('customer', 'tailor', 'master').prefetch_related(
            'stages', 'stages__performed_by',
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
        return OrderRepository.get_all().exclude(order_status__in=['Shipped', 'Delivered'])
