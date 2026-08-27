from crm_api.models import Customer

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
        from django.db.models import Avg, Count, Max, Sum
        return Customer.objects.select_related('measurements').annotate(
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
