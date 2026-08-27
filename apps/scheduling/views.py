from rest_framework import viewsets

from .models import Appointment
from .serializers import AppointmentSerializer
from .services import AppointmentService


class AppointmentViewSet(viewsets.ModelViewSet):

    queryset = Appointment.objects.none()  # Default queryset hint for DRF router schema generator
    serializer_class = AppointmentSerializer

    def get_queryset(self):
        return AppointmentService.get_appointments_for_user(self.request.user)

    def perform_create(self, serializer):
        AppointmentService.create_appointment(serializer, user=self.request.user)

    def perform_update(self, serializer):
        AppointmentService.update_appointment(serializer)

    def perform_destroy(self, instance):
        AppointmentService.delete_appointment(instance)
