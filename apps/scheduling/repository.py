from core.permissions import visible_customers
from crm_api.models import Customer
from .models import Appointment


class AppointmentRepository:

    @staticmethod
    def get_queryset_for_user(user):
        visible = visible_customers(Customer.objects.all(), user)
        return (
            Appointment.objects.select_related('customer', 'order', 'assigned_staff')
            .filter(customer__in=visible)
        )

    @staticmethod
    def get_by_id(appointment_id, user):
        return AppointmentRepository.get_queryset_for_user(user).filter(pk=appointment_id).first()

    @staticmethod
    def create(serializer):
        return serializer.save()

    @staticmethod
    def update(serializer):
        return serializer.save()

    @staticmethod
    def delete(appointment):
        appointment.delete()
