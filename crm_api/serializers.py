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
    class Meta:
        model = BoutiqueSettings
        fields = '__all__'

class TailorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tailor
        fields = '__all__'
        read_only_fields = ['user']

    def to_representation(self, instance):
        """Colleagues' login addresses are the owner's business, not the floor's.

        TailorViewSet has no queryset scoping and this serializer is
        fields='__all__', so any signed-in staff member could read the whole
        roster including every colleague's email -- which is also their
        username, against a bootstrap password that is written in this
        repository. core/permissions.py's own docstring names "the staff list"
        among the things it exists to stop leaking; only the write path was ever
        closed. Everything else on the row is what the floor legitimately needs
        to pick who does a stage.
        """
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request is not None:
            from core.roles import OWNER, resolve_user_role
            if resolve_user_role(request.user) != OWNER:
                data.pop('email', None)
                data.pop('user', None)
        return data

class BoutiqueFabricSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoutiqueFabric
        fields = '__all__'

class BoutiqueDesignSerializer(serializers.ModelSerializer):
    """The catalogue's shape, over the design library that now stores it.

    The rows moved to DesignAsset so the whole library shares one set of filters,
    one attribution and one approval path. This keeps the wire format the
    catalogue endpoints have always returned, so the boutique's Manage Designs
    screen and the wizard gallery carry on unchanged.
    """

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
        """Fold the two loose style fields back into `attributes`."""
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
    # The invoice has to be printable from the Invoices tab, where none of the
    # order wizard's state exists. Without these the modal fell back to
    # whatever customer the wizard last held, and billed the wrong person.
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
    # The per-dress spec and measurement snapshot. Wizard steps 1-2 collect a
    # full spec per garment and save it, and the read side worked -- but nothing
    # ever called it, so what the customer asked for was written once and shown
    # on no screen afterwards, least of all to the tailor who has to cut it.
    # Nesting it here rather than wiring a fetch is the choke point: every
    # screen that shows an order already reads this serializer.
    garment_jobs = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'customer_name', 'customer_garment_type', 'customer_measurements',
            'customer_mobile', 'customer_email', 'customer_address', 'customer_type', 'customer_occasion',
            'customer_neckline_style', 'customer_sleeve_style', 'customer_back_style',
            'tailor', 'tailor_name', 'master', 'master_name',
            'payment_status', 'order_status', 'base_price', 'fabric_price',
            'embroidery_price', 'customization_price', 'tailoring_charges',
            'packaging_handling', 'taxes', 'total_amount', 'order_date', 'estimated_delivery',
            'delivery_method', 'courier_service', 'tracking_number', 'delivery_address',
            'advance_paid', 'amount_paid', 'tailor_comments', 'completed_garment_image',
            'special_instructions',
            'master_verification', 'stage_histories', 'current_stage_key', 'production_status',
            'stages', 'activities', 'garment_images', 'garment_images_published',
            'garment_jobs',
        ]

    def get_customer_name(self, obj):
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}"
        return 'Unknown Customer'

    def get_garment_jobs(self, obj):
        # Imported inside the method: apps.catalog.serializers imports from this
        # module, so a module-level import would be circular.
        from apps.catalog.serializers import GarmentJobSerializer
        return GarmentJobSerializer(obj.garment_jobs.all(), many=True).data


def build_style_dna(obj, avg_price=None, last_order_date=None):
    """Derive the Style DNA panel for a customer.

    Callers pass avg_price and last_order_date so this works both from a
    prefetched order relation (detail view) and from queryset annotations
    (list view, which never loads order rows).
    """
    # 1. Calculate Budget Category
    if not avg_price:
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
    # Built-in hash() is salted per process, so this picked a different palette
    # for the same client after every server restart. A digest keeps it stable.
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

    # 3. Style Preference
    styles_options = [
        "Traditional 90% | Fusion 10%",
        "Contemporary 80% | Traditional 20%",
        "Indo-Western 70% | Traditional 30%",
        "Minimalist 60% | Royal Heritage 40%"
    ]
    style = styles_options[(h >> 8) % len(styles_options)]

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
    last_visit_date = last_order_date.date() if last_order_date else obj.created_at.date()
    
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
        """This customer's orders, scoped the way the order endpoint scopes them.

        It was a plain nested OrderSerializer, so opening a customer a tailor
        legitimately works for handed back that customer's ENTIRE order history
        -- including orders belonging to a different tailor, which
        /api/orders/<id>/ refuses them with a 404 one request earlier. The money,
        all fifteen stage rows and the activity log came with it. Scoping the
        queryset decides which customers you may open; it does nothing about
        what the representation then nests inside them.
        """
        from core.permissions import visible_orders

        queryset = obj.orders.all()
        request = self.context.get('request')
        if request is not None:
            queryset = visible_orders(queryset, request.user)
        return OrderSerializer(queryset, many=True, context=self.context).data

    def validate_mobile_number(self, value):
        """Refuse a number the boutique could never actually reach.

        There was no validator on the model, none here and none on the form, so
        a nine-digit slip was accepted silently -- and every WhatsApp update
        after that rendered as a working "Open WhatsApp" button pointing at
        nobody, which the owner could then mark as sent. whatsapp_number() is
        already the single definition of what is reachable (see
        crm_api/models.py); asking it here means the wizard, the API and any
        future caller all get the same answer.
        """
        if value and not whatsapp_number(value):
            raise serializers.ValidationError(
                'Enter a mobile number the boutique can actually reach '
                '-- 10 digits, or a full international number.')
        return value

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
        
        # Segment logic
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

class OrderSummarySerializer(serializers.ModelSerializer):
    """Order for the dashboard panels.

    Keeps `stages`, which the Order Progress tracker renders, but drops the
    activity log, stage histories and the customer's measurements -- none of
    which any dashboard panel reads.
    """

    tailor_name = serializers.CharField(source='tailor.name', read_only=True)
    master_name = serializers.CharField(source='master.name', read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer_garment_type = serializers.CharField(source='customer.garment_type', read_only=True)
    stages = OrderStageSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'customer_name', 'customer_garment_type',
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


class CustomerSummarySerializer(serializers.ModelSerializer):
    """Customer row for the directory list and dashboard panels.

    Carries everything a directory card renders -- profile fields, measurements
    and Style DNA -- but not the order rows themselves. CustomerSerializer nests
    each order with its stages, activities and stage histories, which made the
    list payload ~119KB for 25 clients. Spend, order count, average price and
    last order date all come from queryset annotations, so no order row is read.

    Consumers that need the actual orders fetch the detail endpoint.
    """

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
    """What the owner needs to send a queued message and tick it off.

    whatsapp_url is the whole feature: it opens the customer's chat with the
    body already typed, so sending is a tap rather than a copy-paste.
    """

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
