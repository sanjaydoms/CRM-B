from apps.activities.models import UniversalActivity
from .repository import AppointmentRepository


class AppointmentService:

    @staticmethod
    def get_appointments_for_user(user):
        return AppointmentRepository.get_queryset_for_user(user)

    @staticmethod
    def get_appointment_by_id(appointment_id, user):
        return AppointmentRepository.get_by_id(appointment_id, user)

    @staticmethod
    def create_appointment(serializer, user):
        appointment = AppointmentRepository.create(serializer)

        is_auth = user and user.is_authenticated
        user_snapshot = (
            (user.get_full_name() or user.username) if is_auth else "System"
        )
        acting_user = user if is_auth else None

        UniversalActivity.objects.create(
            user=acting_user,
            user_name_snapshot=user_snapshot,
            module="scheduling",
            entity_type="Appointment",
            entity_id=str(appointment.id),
            action="SCHEDULED",
            title=f"Appointment Booked: {appointment.get_appointment_type_display()}",
            description=(
                f"{appointment.get_appointment_type_display()} scheduled for client "
                f"{appointment.customer.first_name} {appointment.customer.last_name} "
                f"on {appointment.scheduled_time.strftime('%b %d, %Y %I:%M %p')}"
            ),
            new_value={
                "status": appointment.status,
                "scheduled_time": str(appointment.scheduled_time),
            },
        )

        return appointment

    @staticmethod
    def update_appointment(serializer):
        return AppointmentRepository.update(serializer)

    @staticmethod
    def delete_appointment(appointment):
        AppointmentRepository.delete(appointment)
