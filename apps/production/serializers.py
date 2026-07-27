from rest_framework import serializers
from .models import ProductionTask, QCRecord
from crm_api.serializers import TailorSerializer

class ProductionTaskSerializer(serializers.ModelSerializer):
    assigned_to_detail = TailorSerializer(source='assigned_to', read_only=True)
    order_id_display = serializers.CharField(source='order.order_id', read_only=True)
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductionTask
        fields = '__all__'

    def get_customer_name(self, obj):
        if obj.order and obj.order.customer:
            return f"{obj.order.customer.first_name} {obj.order.customer.last_name}"
        return ""

class QCRecordSerializer(serializers.ModelSerializer):
    inspector_detail = TailorSerializer(source='inspector', read_only=True)

    class Meta:
        model = QCRecord
        fields = '__all__'
