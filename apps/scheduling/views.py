from rest_framework import viewsets

from core.permissions import visible_customers
from crm_api.models import Customer
from .models import Appointment
from .serializers import AppointmentSerializer
from apps.activities.models import UniversalActivity

class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.select_related('customer', 'order', 'assigned_staff').all()
    serializer_class = AppointmentSerializer

    def get_queryset(self):
        """Only appointments for clients this caller may see.

        This had no scoping at all, and RolePermission grants every non-Owner
        staff member all SAFE_METHODS -- a blanket grant that only works because
        crm_api's viewsets narrow their own querysets. This router never did, and
        AppointmentSerializer nests the FULL CustomerSerializer, which in turn
        nests that customer's orders and their money. So a tailor who is
        correctly 404'd from a stranger's customer record read the same person's
        name, mobile number, email and home address here instead -- and the
        frontend loads this endpoint for every role on every login, so it
        arrived in their browser unasked.

        core/permissions.py's own docstring names this exact outcome as the thing
        it exists to prevent: a tailor reading the whole order book is how a
        customer list walks out of the building.
        """
        customers = visible_customers(Customer.objects.all(), self.request.user)
        return super().get_queryset().filter(customer__in=customers)

    def perform_create(self, serializer):
        appointment = serializer.save()
        UniversalActivity.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            user_name_snapshot=self.request.user.get_full_name() or self.request.user.username if self.request.user.is_authenticated else "System",
            module="scheduling",
            entity_type="Appointment",
            entity_id=str(appointment.id),
            action="SCHEDULED",
            title=f"Appointment Booked: {appointment.get_appointment_type_display()}",
            description=f"{appointment.get_appointment_type_display()} scheduled for client {appointment.customer.first_name} {appointment.customer.last_name} on {appointment.scheduled_time.strftime('%b %d, %Y %I:%M %p')}",
            new_value={"status": appointment.status, "scheduled_time": str(appointment.scheduled_time)}
        )
