import hashlib

from rest_framework import serializers

from apps.design_studio.models import DesignAsset
from .models import (
    Customer, CustomerMessage, GarmentImage, Measurement, DesignPreference,
    FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign,
    Notification, OrderStageHistory, BoutiqueSettings, MeasurementHistory,
    OrderStage, OrderActivity, whatsapp_number
)

class BoutiqueSettingsSerializer(serializers.ModelSerializer):
    timezone = serializers.SerializerMethodField()

    class Meta:
        model = BoutiqueSettings
        fields = '__all__'

    def get_timezone(self, obj):
        from django.db import connection

        from core.formatting import DEFAULT_TIMEZONE
        return (getattr(getattr(connection, 'tenant', None), 'timezone', '')
                or DEFAULT_TIMEZONE)

class TailorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tailor
        fields = '__all__'
        read_only_fields = ['user']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request is not None:
            from core.roles import OWNER, resolve_user_role
            if resolve_user_role(request.user) != OWNER:
                data.pop('email', None)
                data.pop('user', None)

        bootstrap = getattr(instance, '_bootstrap_password', None)
        if bootstrap:
            data['bootstrap_password'] = bootstrap
        return data

class BoutiqueFabricSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoutiqueFabric
        fields = '__all__'

class BoutiqueDesignSerializer(serializers.ModelSerializer):

    name = serializers.CharField(source='title')
    price = serializers.DecimalField(
        source='estimated_price', max_digits=10, decimal_places=2, required=False)
    is_boutique = serializers.SerializerMethodField()
    neckline_style = serializers.SerializerMethodField()
    sleeve_style = serializers.SerializerMethodField()

    class Meta:
        model = DesignAsset
        fields = [
            'id', 'name', 'garment_type', 'neckline_style', 'sleeve_style',
            'image_url', 'is_boutique', 'description', 'price',
        ]

    def get_is_boutique(self, asset):
        return asset.source == DesignAsset.SOURCE_CATALOGUE

    def get_neckline_style(self, asset):
        return (asset.attributes or {}).get('neckline_style', '')

    def get_sleeve_style(self, asset):
        return (asset.attributes or {}).get('sleeve_style', '')

    def _apply_style(self, asset, data):

        attributes = dict(asset.attributes or {})
        for key in ('neckline_style', 'sleeve_style'):
            if key in data:
                attributes[key] = data[key]
        asset.attributes = attributes

    def create(self, validated_data):
        raw = self.initial_data
        asset = DesignAsset(
            source=(DesignAsset.SOURCE_CATALOGUE
                    if raw.get('is_boutique', True) in (True, 'true', 'True')
                    else DesignAsset.SOURCE_SUGGESTION),
            **validated_data,
        )
        self._apply_style(asset, raw)
        asset.save()
        return asset

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        self._apply_style(instance, self.initial_data)
        if 'is_boutique' in self.initial_data:
            instance.source = (DesignAsset.SOURCE_CATALOGUE
                               if self.initial_data['is_boutique'] in (True, 'true', 'True')
                               else DesignAsset.SOURCE_SUGGESTION)
        instance.save()
        return instance

class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = ['bust', 'waist', 'hips', 'shoulder', 'arm_length', 'neck', 'length', 'additional_measurements']

class MeasurementHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementHistory
        fields = ['id', 'bust', 'waist', 'hips', 'shoulder', 'arm_length', 'neck', 'length', 'additional_measurements', 'changed_at']

class DesignPreferenceSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source='get_source_display', read_only=True)

    class Meta:
        model = DesignPreference
        fields = [
            'id', 'notes', 'reference_images', 'source', 'source_display',
            'reference_links', 'approved_image', 'is_approved', 'approved_at',
        ]
        read_only_fields = ['approved_at']

class FabricSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FabricSelection
        fields = ['is_boutique_fabric', 'fabric_name', 'fabric_price', 'uploaded_fabric_images']

class OrderStageHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStageHistory
        fields = '__all__'

class OrderStageSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source='performed_by.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.name', read_only=True)
    assigned_to_role = serializers.CharField(source='assigned_to.role', read_only=True)

    class Meta:
        model = OrderStage
        fields = '__all__'

class OrderActivitySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.first_name', read_only=True)

    class Meta:
        model = OrderActivity
        fields = '__all__'

class GarmentImageSerializer(serializers.ModelSerializer):
    view_label = serializers.CharField(source='get_view_display', read_only=True)

    class Meta:
        model = GarmentImage
        fields = ['id', 'order', 'view', 'view_label', 'image', 'uploaded_at']
        read_only_fields = ['id', 'order', 'view_label', 'uploaded_at']

class OrderSerializer(serializers.ModelSerializer):
    tailor_name = serializers.CharField(source='tailor.name', read_only=True)
    master_name = serializers.CharField(source='master.name', read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer_garment_type = serializers.CharField(source='customer.garment_type', read_only=True)
    customer_measurements = MeasurementSerializer(source='customer.measurements', read_only=True)
    customer_mobile = serializers.CharField(source='customer.mobile_number', read_only=True)
    customer_email = serializers.CharField(source='customer.email_address', read_only=True)
    customer_address = serializers.CharField(source='customer.address', read_only=True)
    customer_type = serializers.CharField(source='customer.customer_type', read_only=True)
    customer_occasion = serializers.CharField(source='customer.occasion', read_only=True)
    customer_neckline_style = serializers.CharField(source='customer.neckline_style', read_only=True)
    customer_sleeve_style = serializers.CharField(source='customer.sleeve_style', read_only=True)
    customer_back_style = serializers.CharField(source='customer.back_style', read_only=True)
    stage_histories = OrderStageHistorySerializer(many=True, read_only=True)
    stages = OrderStageSerializer(many=True, read_only=True)
    activities = OrderActivitySerializer(many=True, read_only=True)
    garment_images = GarmentImageSerializer(many=True, read_only=True)
    garment_jobs = serializers.SerializerMethodField()
    garments = serializers.SerializerMethodField()
    garment_label = serializers.SerializerMethodField()
    order_status_display = serializers.SerializerMethodField()
    delivery_method_display = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'customer_name', 'customer_garment_type', 'customer_measurements',
            'garments', 'garment_label',
            'customer_mobile', 'customer_email', 'customer_address', 'customer_type', 'customer_occasion',
            'customer_neckline_style', 'customer_sleeve_style', 'customer_back_style',
            'tailor', 'tailor_name', 'master', 'master_name',
            'payment_status', 'order_status', 'order_status_display', 'base_price', 'fabric_price',
            'embroidery_price', 'customization_price', 'tailoring_charges',
            'packaging_handling', 'discount', 'taxes', 'total_amount', 'order_date', 'estimated_delivery',
            'delivery_method', 'delivery_method_display', 'courier_service', 'tracking_number', 'delivery_address',
            'advance_paid', 'amount_paid', 'tailor_comments', 'completed_garment_image',
            'special_instructions',
            'master_verification', 'stage_histories', 'current_stage_key', 'production_status',
            'stages', 'activities', 'garment_images', 'garment_images_published',
            'garment_jobs',
        ]

    def _get_lang(self):
        request = self.context.get('request')
        if request:
            lang = request.headers.get('Accept-Language') or request.META.get('HTTP_ACCEPT_LANGUAGE', 'en')
            if lang:
                clean_lang = lang.split(',')[0].strip()[:2].lower()
                if clean_lang in ('hi', 'en'):
                    return clean_lang
        return 'en'

    def get_order_status_display(self, obj):
        lang = self._get_lang()
        status_val = obj.order_status or 'Received'
        translations = {
            'hi': {
                'Received': 'प्राप्त हुआ',
                'Confirmed': 'पुष्टि की गई',
                'Stylist Review': 'स्टाइलिस्ट समीक्षा',
                'Design & Creation': 'डिजाइन और निर्माण',
                'Quality Check': 'गुणवत्ता जांच',
                'Ready for Dispatch': 'डिस्पैच के लिए तैयार',
                'Shipped': 'भेज दिया',
                'Delivered': 'डिलीवर किया गया',
            },
            'en': {
                'Received': 'Received',
                'Confirmed': 'Confirmed',
                'Stylist Review': 'Stylist Review',
                'Design & Creation': 'Design & Creation',
                'Quality Check': 'Quality Check',
                'Ready for Dispatch': 'Ready for Dispatch',
                'Shipped': 'Shipped',
                'Delivered': 'Delivered',
            }
        }
        return translations.get(lang, translations['en']).get(status_val, status_val)

    def get_delivery_method_display(self, obj):
        lang = self._get_lang()
        method_val = obj.delivery_method or 'Direct Pickup'
        translations = {
            'hi': {
                'Direct Pickup': 'प्रत्यक्ष पिकअप',
                'Courier': 'कूरियर',
                'Store Pickup': 'स्टोर पिकअप',
                'प्रत्यक्ष पिकअप (Direct Pickup)': 'प्रत्यक्ष पिकअप',
            },
            'en': {
                'Direct Pickup': 'Direct Pickup',
                'Courier': 'Courier',
                'Store Pickup': 'Store Pickup',
                'प्रत्यक्ष पिकअप (Direct Pickup)': 'Direct Pickup',
            }
        }
        return translations.get(lang, translations['en']).get(method_val, method_val)

    def get_customer_name(self, obj):
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}"
        return 'Unknown Customer'

    def get_garment_jobs(self, obj):
        from apps.catalog.serializers import GarmentJobSerializer
        return GarmentJobSerializer(obj.garment_jobs.all(), many=True).data

    def get_garments(self, obj):
        from domains.orders.garments import garment_names
        return garment_names(obj)

    def get_garment_label(self, obj):
        from domains.orders.garments import garment_label
        return garment_label(obj)


def build_style_dna(obj, avg_price=None, last_order_date=None):
    if not avg_price:
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

    if avg_price < 10000:
        budget = f"₹{int(avg_price):,} (mid-range)"
    elif avg_price < 30000:
        budget = f"₹{int(avg_price):,} (premium designer)"
    else:
        budget = f"₹{int(avg_price):,} (luxury bridal)"

    h = int.from_bytes(hashlib.sha256(str(obj.id).encode()).digest()[:8], 'big')
    colors_options = [
        "Blue 80% Green 15% Red 5%",
        "Dusty Rose 60% Ivory 30% Gold 10%",
        "Emerald Green 80% Pink 15% Red 5%",
        "Charcoal Black 90% Silver 10%",
        "Peach 50% Mint Green 40% Gold 10%",
        "Crimson Red 90% Antique Gold 10%"
    ]
    colors = colors_options[h % len(colors_options)]

    styles_options = [
        "Traditional 90% | Fusion 10%",
        "Contemporary 80% | Traditional 20%",
        "Indo-Western 70% | Traditional 30%",
        "Minimalist 60% | Royal Heritage 40%"
    ]
    style = styles_options[(h >> 8) % len(styles_options)]

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

    last_visit_date = last_order_date.date() if last_order_date else obj.created_at.date()
    
    from django.utils import timezone
    days_since = (timezone.now().date() - last_visit_date).days

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


class CustomerSerializer(serializers.ModelSerializer):
    measurements = MeasurementSerializer(required=False)
    measurement_history = MeasurementHistorySerializer(many=True, read_only=True)
    design_preferences = DesignPreferenceSerializer(many=True, read_only=True)
    fabric_selections = FabricSelectionSerializer(many=True, read_only=True)
    orders = serializers.SerializerMethodField()
    style_dna = serializers.SerializerMethodField()
    segment = serializers.SerializerMethodField()
    total_spend = serializers.SerializerMethodField()
    order_count = serializers.SerializerMethodField()

    def get_orders(self, obj):
        from core.permissions import visible_orders

        queryset = obj.orders.all()
        request = self.context.get('request')
        if request is not None:
            queryset = visible_orders(queryset, request.user)
        return OrderSerializer(queryset, many=True, context=self.context).data

    def to_internal_value(self, data):
        raw = data.get('mobile_number') if hasattr(data, 'get') else None
        if raw:
            canonical = whatsapp_number(raw)
            if canonical and canonical != raw:
                data = data.copy()
                data['mobile_number'] = canonical
        return super().to_internal_value(data)

    def validate_mobile_number(self, value):
        if not value:
            return value
        canonical = whatsapp_number(value)
        if not canonical:
            raise serializers.ValidationError(
                'Enter a mobile number the boutique can actually reach '
                '-- 10 digits, or a full international number.')
        return canonical

    class Meta:
        model = Customer
        fields = [
            'id', 'first_name', 'last_name', 'mobile_number', 'email_address',
            'address', 'city_region', 'source', 'customer_type', 'garment_type',
            'neckline_style', 'sleeve_style', 'back_style', 'length_preference',
            'silhouette', 'embellishments', 'pattern_style', 'occasion',
            'custom_requirements', 'date_of_birth', 'occupation',
            'preferred_communication', 'notes', 'profile_photo',
            'measurements', 'measurement_history', 'design_preferences', 'fabric_selections', 'orders',
            'style_dna', 'segment', 'total_spend', 'order_count', 'created_at', 'updated_at'
        ]

    def get_total_spend(self, obj):
        return sum(float(o.total_amount) for o in obj.orders.all())

    def get_order_count(self, obj):
        return len(obj.orders.all())

    def get_segment(self, obj):
        total_spend = self.get_total_spend(obj)
        order_count = self.get_order_count(obj)
        
        if total_spend >= 75000 or order_count >= 3:
            return "VIP"
        elif total_spend >= 20000 or order_count >= 1:
            return "HVC"
        else:
            return "General"

    def get_style_dna(self, obj):
        orders = obj.orders.all()
        avg_price = sum(o.total_amount for o in orders) / len(orders) if orders else None
        last_order_date = max((o.order_date for o in orders), default=None)
        return build_style_dna(obj, avg_price, last_order_date)

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
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if measurements_data:
            measurements_instance, _ = Measurement.objects.get_or_create(customer=instance)
            for attr, value in measurements_data.items():
                setattr(measurements_instance, attr, value)
            measurements_instance.save()
            
        return instance

class OrderSummarySerializer(serializers.ModelSerializer):

    tailor_name = serializers.CharField(source='tailor.name', read_only=True)
    master_name = serializers.CharField(source='master.name', read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer_garment_type = serializers.CharField(source='customer.garment_type', read_only=True)
    garments = serializers.SerializerMethodField()
    garment_label = serializers.SerializerMethodField()
    stages = OrderStageSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'customer_name', 'customer_garment_type',
            'garments', 'garment_label',
            'tailor', 'tailor_name', 'master', 'master_name',
            'payment_status', 'order_status', 'total_amount', 'advance_paid', 'amount_paid',
            'order_date', 'estimated_delivery', 'delivery_method', 'courier_service',
            'tracking_number', 'delivery_address', 'tailor_comments',
            'completed_garment_image', 'current_stage_key', 'production_status', 'stages',
        ]

    def get_customer_name(self, obj):
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}"
        return 'Unknown Customer'

    def get_garments(self, obj):
        from domains.orders.garments import garment_names
        return garment_names(obj)

    def get_garment_label(self, obj):
        from domains.orders.garments import garment_label
        return garment_label(obj)


class CustomerSummarySerializer(serializers.ModelSerializer):

    measurements = MeasurementSerializer(read_only=True)
    style_dna = serializers.SerializerMethodField()
    total_spend = serializers.SerializerMethodField()
    order_count = serializers.SerializerMethodField()
    segment = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id', 'first_name', 'last_name', 'mobile_number', 'email_address',
            'address', 'city_region', 'source', 'customer_type', 'garment_type',
            'neckline_style', 'sleeve_style', 'back_style', 'length_preference',
            'silhouette', 'embellishments', 'pattern_style', 'occasion',
            'custom_requirements', 'date_of_birth', 'occupation',
            'preferred_communication', 'notes', 'profile_photo', 'measurements',
            'style_dna', 'total_spend', 'order_count', 'segment',
            'created_at', 'updated_at',
        ]

    def get_total_spend(self, obj):
        return float(getattr(obj, 'orders_total_spend', None) or 0)

    def get_order_count(self, obj):
        count = getattr(obj, 'orders_count', None)
        return count if count is not None else obj.orders.count()

    def get_segment(self, obj):
        total_spend = self.get_total_spend(obj)
        order_count = self.get_order_count(obj)
        if total_spend >= 75000 or order_count >= 3:
            return "VIP"
        if total_spend >= 20000 or order_count >= 1:
            return "HVC"
        return "General"

    def get_style_dna(self, obj):
        return build_style_dna(
            obj,
            avg_price=getattr(obj, 'orders_avg_price', None),
            last_order_date=getattr(obj, 'orders_last_date', None),
        )

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class CustomerMessageSerializer(serializers.ModelSerializer):

    whatsapp_url = serializers.ReadOnlyField()
    sent_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomerMessage
        fields = [
            'id', 'order', 'template_key', 'to_number', 'body', 'status',
            'whatsapp_url', 'sent_by_name', 'error', 'created_at',
        ]
        read_only_fields = fields

    def get_sent_by_name(self, obj):
        if not obj.sent_by:
            return None
        return obj.sent_by.get_full_name() or obj.sent_by.username
