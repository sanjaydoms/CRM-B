from crm_api.models import Customer, Measurement

class CustomerRepository:
    @staticmethod
    def get_all():
        return Customer.objects.prefetch_related(
            'orders', 'orders__stages', 'orders__activities', 'orders__tailor', 'orders__master',
            'measurement_history', 'design_preferences', 'fabric_selections'
        ).all().order_by('-created_at')

    @staticmethod
    def get_by_id(customer_id):
        return Customer.objects.filter(id=customer_id).first()

    @staticmethod
    def search(query):
        return Customer.objects.filter(
            first_name__icontains=query
        ) | Customer.objects.filter(
            last_name__icontains=query
        ) | Customer.objects.filter(
            mobile_number__icontains=query
        )
