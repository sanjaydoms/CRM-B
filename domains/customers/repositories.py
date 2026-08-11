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
            # distinct throughout. visible_customers scopes a tailor with
            # Q(orders__stages__assigned_to=...), and that join multiplies each
            # order row by its fifteen stages. Count already had it; Sum and Avg
            # did not, so a tailor's view of a client's spend came back fifteen
            # times too large. .distinct() on the queryset does not save an
            # annotated aggregate, which is why the row list looked right while
            # the money did not.
            orders_count=Count('orders', distinct=True),
            orders_total_spend=Sum('orders__total_amount', distinct=True),
            orders_avg_price=Avg('orders__total_amount', distinct=True),
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
