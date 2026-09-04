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
        customers = visible_customers(Customer.objects.all(), self.request.user)
        queryset = super().get_queryset().filter(customer__in=customers)

        # The dashboard panel is headed "Upcoming Appointments" and was handed
        # every appointment the boutique had ever booked, oldest first -- so a
        # fitting from three months ago sat at the top of it, a cancelled one
        # sat below that, and the trial happening this afternoon was somewhere
        # further down. Asking for what the panel actually promises is one
        # parameter; without it the panel could only ever grow more wrong.
        if self.request.query_params.get('upcoming') == 'true':
            from django.utils import timezone
            queryset = queryset.filter(
                scheduled_time__gte=timezone.now()
            ).exclude(status='CANCELLED')
        return queryset

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
