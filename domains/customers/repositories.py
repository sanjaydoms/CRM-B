from crm_api.models import Customer

# CustomerSerializer nests the full OrderSerializer, which in turn nests stages,
# activities, stage histories and the customer's measurements. Every relation the
# serializer touches has to be prefetched here or it becomes one round trip per
# row -- against a pooled remote Postgres that is seconds of latency per request.
CUSTOMER_PREFETCH = (
    'measurement_history',
    'design_preferences',
    'fabric_selections',
    'orders',
    'orders__tailor',
    'orders__master',
    'orders__customer__measurements',
    'orders__stages',
    'orders__stages__performed_by',
    'orders__stages__assigned_to',
    'orders__activities',
    'orders__activities__user',
    'orders__stage_histories',
)


class CustomerRepository:
    @staticmethod
    def summary_queryset():
        """Rows for CustomerSummarySerializer -- no order rows are read.

        Everything the serializer derives from orders (spend, count, average
        price, last order date) is computed in SQL here instead.
        """
        from django.db.models import Avg, Count, Max, Sum
        return Customer.objects.select_related('measurements').annotate(
            # distinct stays on Count and is GONE from Sum and Avg, and the
            # difference matters more than it looks.
            #
            # Count(DISTINCT id) counts distinct ROWS, which is what was wanted.
            # Sum(DISTINCT total_amount) sums distinct VALUES -- so a client with
            # two ₹40,000 orders had a lifetime spend of ₹40,000. Repeat orders
            # at a repeated price are the ordinary pattern in a boutique, not an
            # edge case, and it under-reported for EVERY role including the
            # Owner, who has no join fan-out at all. The existing test used
            # [1000, 2500, 500] -- three distinct values -- which is exactly why
            # it never caught this.
            #
            # distinct was added here to counter the row multiplication from
            # visible_customers' Q(orders__stages__assigned_to=...) join. That
            # join is now a subquery (see core.permissions.visible_customers),
            # so there is no fan-out left to counter and the honest aggregate is
            # the correct one. Do not put distinct back on these two: it treats
            # equal amounts as duplicates, which is the bug.
            orders_count=Count('orders', distinct=True),
            orders_total_spend=Sum('orders__total_amount'),
            orders_avg_price=Avg('orders__total_amount'),
            orders_last_date=Max('orders__order_date'),
        ).order_by('-created_at')

    @staticmethod
    def base_queryset():
        return Customer.objects.select_related('measurements').prefetch_related(*CUSTOMER_PREFETCH)

    @staticmethod
    def get_all():
        return CustomerRepository.base_queryset().order_by('-created_at')

    @staticmethod
    def get_by_id(customer_id):
        return CustomerRepository.base_queryset().filter(id=customer_id).first()

    @staticmethod
    def search(query):
        from django.db.models import Q
        return CustomerRepository.get_all().filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(mobile_number__icontains=query)
        )
