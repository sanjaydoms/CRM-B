from rest_framework import serializers

from .models import DesignAsset, DesignBoard, DesignBoardItem


class DesignAssetSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source='get_source_display', read_only=True)

    class Meta:
        model = DesignAsset
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class DesignBoardItemSerializer(serializers.ModelSerializer):
    production_notes_by_name = serializers.CharField(
        source='production_notes_by.name', read_only=True, default='')

    class Meta:
        model = DesignBoardItem
        fields = '__all__'
        read_only_fields = ['board', 'is_selected', 'production_notes', 'production_notes_by']


class DesignBoardSerializer(serializers.ModelSerializer):
    items = DesignBoardItemSerializer(many=True, read_only=True)
    selected = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    order_id_display = serializers.CharField(source='order.order_id', read_only=True, default='')

    class Meta:
        model = DesignBoard
        fields = '__all__'
        read_only_fields = ['status', 'created_by', 'approved_by', 'approved_at', 'order']

    def get_selected(self, obj):
        item = obj.selected_item
        return DesignBoardItemSerializer(item).data if item else None

    def get_customer_name(self, obj):
        customer = obj.customer
        return f"{customer.first_name} {customer.last_name}".strip()


class TailorBriefSerializer(serializers.ModelSerializer):
    """What a Tailor is shown: the approved design and how to make it."""

    customer_name = serializers.SerializerMethodField()
    order_id_display = serializers.CharField(source='order.order_id', read_only=True, default='')
    design = serializers.SerializerMethodField()

    class Meta:
        model = DesignBoard
        fields = ['id', 'status', 'customer_name', 'order_id_display', 'approved_at', 'design']

    def get_customer_name(self, obj):
        customer = obj.customer
        return f"{customer.first_name} {customer.last_name}".strip()

    def get_design(self, obj):
        item = obj.selected_item
        if item is None:
            return None
        return {
            'title': item.title,
            'image_url': item.image_url,
            'source': item.source,
            'source_url': item.source_url,
            'attributes': item.attributes,
            'colour_palette': item.colour_palette,
            'customer_notes': item.customer_notes,
            'tailor_instructions': item.tailor_instructions,
            'production_notes': item.production_notes,
        }


class DiscoverRequestSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    garment_type = serializers.CharField(required=False, allow_blank=True)
    occasion = serializers.CharField(required=False, allow_blank=True)
    budget = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    delivery_timeline = serializers.CharField(required=False, allow_blank=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)
    sources = serializers.ListField(child=serializers.CharField(), required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
