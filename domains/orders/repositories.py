from crm_api.models import Order

class OrderRepository:
    @staticmethod
    def get_all():
        return Order.objects.select_related(
            'customer', 'tailor', 'master', 'customer__measurements'
        ).prefetch_related(
            'stages', 'stages__performed_by', 'activities', 'activities__user'
        ).all().order_by('-order_date')

    @staticmethod
    def get_by_id(order_id):
        return Order.objects.filter(id=order_id).first()

    @staticmethod
    def get_active_orders():
        return Order.objects.exclude(order_status__in=['Shipped', 'Delivered']).order_by('-order_date')
