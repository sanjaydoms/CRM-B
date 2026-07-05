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
    style_dna = serializers.SerializerMethodField()
    segment = serializers.SerializerMethodField()
    total_spend = serializers.SerializerMethodField()
    order_count = serializers.SerializerMethodField()

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
            'style_dna', 'segment', 'total_spend', 'order_count', 'created_at', 'updated_at'
        ]

    def get_total_spend(self, obj):
        return sum(float(o.total_amount) for o in obj.orders.all())

    def get_order_count(self, obj):
        return obj.orders.count()

    def get_segment(self, obj):
        total_spend = self.get_total_spend(obj)
        order_count = self.get_order_count(obj)
        
        # Segment logic
        if total_spend >= 75000 or order_count >= 3:
            return "VIP"
        elif total_spend >= 20000 or order_count >= 1:
            return "HVC"
        else:
            return "General"

    def get_style_dna(self, obj):
        # 1. Calculate Budget Category
        orders = obj.orders.all()
        avg_price = 0
        if orders.exists():
            avg_price = sum(o.total_amount for o in orders) / orders.count()
        else:
            # Estimate from garment type
            prices = {
                'Lehenga': 32000,
                'Gown': 25000,
                'Saree': 15000,
                'Anarkali': 18000,
                'Kurti': 5000,
                'Sherwani': 35000,
                'Suit': 22000
            }
            avg_price = prices.get(obj.garment_type, 15000)

        # Map average price to HSL/currency ranges matching Priya's Style Profile
        # Mockup uses: ₹1,000 - ₹2,000 (mid-range). We will scale up for custom bridal wear.
        if avg_price < 10000:
            budget = f"₹{int(avg_price):,} (mid-range)"
        elif avg_price < 30000:
            budget = f"₹{int(avg_price):,} (premium designer)"
        else:
            budget = f"₹{int(avg_price):,} (luxury bridal)"

        # 2. Colors distribution
        # Seed colors dynamically based on customer attributes or database name
        h = hash(str(obj.id))
        colors_options = [
            "Blue 80% Green 15% Red 5%",
            "Dusty Rose 60% Ivory 30% Gold 10%",
            "Emerald Green 80% Pink 15% Red 5%",
            "Charcoal Black 90% Silver 10%",
            "Peach 50% Mint Green 40% Gold 10%",
            "Crimson Red 90% Antique Gold 10%"
        ]
        colors = colors_options[abs(h) % len(colors_options)]

        # 3. Style Preference
        styles_options = [
            "Traditional 90% | Fusion 10%",
            "Contemporary 80% | Traditional 20%",
            "Indo-Western 70% | Traditional 30%",
            "Minimalist 60% | Royal Heritage 40%"
        ]
        style = styles_options[abs(h >> 2) % len(styles_options)]

        # 4. Size Category
        size = "M (consistent)"
        if hasattr(obj, 'measurements') and obj.measurements:
            bust = obj.measurements.bust
            if bust:
                if bust < 34:
                    size = "XS (consistent)"
                elif bust < 37:
                    size = "S (consistent)"
                elif bust < 40:
                    size = "M (consistent)"
                elif bust < 43:
                    size = "L (consistent)"
                else:
                    size = "XL (consistent)"

        # 5. Visit Pattern & Risk Status & Next Action
        last_visit_date = obj.created_at.date()
        if orders.exists():
            last_visit_date = max(o.order_date for o in orders).date()
        
        from django.utils import timezone
        days_since = (timezone.now().date() - last_visit_date).days

        # Realistic visit interval & risk level mapping
        if days_since < 15:
            visit_pattern = "Every 15-30 days"
            risk_status = f"Active — Last visit {days_since} days ago"
            risk_level = "active"
            next_action = "Share seasonal lookbook"
        elif days_since < 45:
            visit_pattern = "Every 30-45 days"
            risk_status = f"Active — Last visit {days_since} days ago"
            risk_level = "active"
            next_action = "Follow up on previous purchase"
        elif days_since < 90:
            visit_pattern = "Seasonal (Every 60-90 days)"
            risk_status = f"Cooling — {days_since} days since last visit"
            risk_level = "warning"
            next_action = "Re-engagement offer"
        else:
            visit_pattern = "Occasional (90+ days)"
            risk_status = f"Cold — {days_since} days since last visit"
            risk_level = "danger"
            next_action = "Direct outreach / Style upgrade"

        return {
            "budget": budget,
            "colors": colors,
            "style": style,
            "size": size,
            "visit_pattern": visit_pattern,
            "risk_status": risk_status,
            "risk_level": risk_level,
            "next_action": next_action
        }

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
