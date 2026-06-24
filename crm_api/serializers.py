from rest_framework import serializers
from .models import Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign

class TailorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tailor
        fields = '__all__'

class BoutiqueFabricSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoutiqueFabric
        fields = '__all__'

class BoutiqueDesignSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoutiqueDesign
        fields = '__all__'

class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = ['bust', 'waist', 'hips', 'shoulder', 'arm_length', 'neck', 'length', 'additional_measurements']

class DesignPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DesignPreference
        fields = ['notes', 'reference_images']

class FabricSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FabricSelection
        fields = ['is_boutique_fabric', 'fabric_name', 'fabric_price', 'uploaded_fabric_images']

class OrderSerializer(serializers.ModelSerializer):
    tailor_name = serializers.CharField(source='tailor.name', read_only=True)
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'customer_name', 'tailor', 'tailor_name',
            'payment_status', 'order_status', 'base_price', 'fabric_price',
            'embroidery_price', 'customization_price', 'tailoring_charges',
            'packaging_handling', 'taxes', 'total_amount', 'order_date', 'estimated_delivery'
        ]

    def get_customer_name(self, obj):
        return f"{obj.customer.first_name} {obj.customer.last_name}"

class CustomerSerializer(serializers.ModelSerializer):
    measurements = MeasurementSerializer(required=False)
    design_preferences = DesignPreferenceSerializer(many=True, read_only=True)
    fabric_selections = FabricSelectionSerializer(many=True, read_only=True)
    orders = OrderSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'first_name', 'last_name', 'mobile_number', 'email_address',
            'address', 'city_region', 'source', 'customer_type', 'garment_type',
            'neckline_style', 'sleeve_style', 'back_style', 'length_preference',
            'silhouette', 'embellishments', 'pattern_style', 'occasion',
            'custom_requirements', 'date_of_birth', 'occupation',
            'preferred_communication', 'notes', 'profile_photo',
            'measurements', 'design_preferences', 'fabric_selections', 'orders',
            'created_at', 'updated_at'
        ]

    def create(self, validated_data):
        measurements_data = validated_data.pop('measurements', None)
        customer = Customer.objects.create(**validated_data)
        if measurements_data:
            Measurement.objects.create(customer=customer, **measurements_data)
        else:
            Measurement.objects.create(customer=customer)
        return customer

    def update(self, instance, validated_data):
        measurements_data = validated_data.pop('measurements', None)
        
        # Update customer fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update measurements
        if measurements_data:
            measurements_instance, _ = Measurement.objects.get_or_create(customer=instance)
            for attr, value in measurements_data.items():
                setattr(measurements_instance, attr, value)
            measurements_instance.save()
            
        return instance
