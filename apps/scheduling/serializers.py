from rest_framework import serializers
from .models import Appointment
from crm_api.serializers import CustomerSerializer, TailorSerializer

class AppointmentSerializer(serializers.ModelSerializer):
    customer_detail = CustomerSerializer(source='customer', read_only=True)
    assigned_staff_detail = TailorSerializer(source='assigned_staff', read_only=True)

    class Meta:
        model = Appointment
        fields = '__all__'
