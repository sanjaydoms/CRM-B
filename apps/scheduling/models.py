import uuid
from django.db import models
from crm_api.models import Customer, Order, Tailor

class Appointment(models.Model):
    TYPE_CHOICES = [
        ('CONSULTATION', 'Design Consultation'),
        ('MEASUREMENT', 'Measurement Fitting'),
        ('TRIAL', 'Garment Trial'),
        ('DELIVERY', 'Final Delivery'),
    ]

    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('CONFIRMED', 'Confirmed'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('RESCHEDULED', 'Rescheduled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='appointments')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments')
    appointment_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default='TRIAL', db_index=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='SCHEDULED', db_index=True)
    scheduled_time = models.DateTimeField(db_index=True)
    assigned_staff = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_appointments')
    notes = models.TextField(blank=True, null=True)
    reminder_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_time']

    def __str__(self):
        return f"{self.get_appointment_type_display()} for {self.customer.first_name} at {self.scheduled_time}"
