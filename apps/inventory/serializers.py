from rest_framework import serializers

from .models import (
    CatalogItem, CatalogSection, Category, DEFAULT_UNIT_BY_CATEGORY, InventoryItem,
    LocationStock, PurchaseOrder, PurchaseOrderLine, StockLocation, StockMovement,
    Supplier, Unit,
)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'


class InventoryItemSerializer(serializers.ModelSerializer):
    available_stock = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = InventoryItem
        fields = '__all__'
        # Stock moves only through InventoryService; letting the API PATCH these
        # would put the ledger and the balance out of step.
        read_only_fields = ['current_stock', 'reserved_stock', 'created_at', 'updated_at']

    def validate(self, attrs):
        category = attrs.get('category') or getattr(self.instance, 'category', None)
        if category and not attrs.get('unit') and not self.instance:
            attrs['unit'] = DEFAULT_UNIT_BY_CATEGORY.get(category, Unit.UNIT)
        return attrs


class InventoryItemSummarySerializer(serializers.ModelSerializer):
    """Flat row for list views -- no supplier join, no descriptors."""

    available_stock = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'item_code', 'name', 'category', 'color', 'unit', 'unit_display',
            'current_stock', 'reserved_stock', 'available_stock', 'reorder_level',
            'needs_reorder', 'rack_location', 'status', 'purchase_price',
        ]


class StockMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    order_reference = serializers.CharField(source='order.order_id', read_only=True)
    performed_by_name = serializers.CharField(source='performed_by.name', read_only=True)

    class Meta:
        model = StockMovement
        fields = '__all__'
        # The ledger is append-only: it is written by InventoryService alone.
        read_only_fields = [f.name for f in StockMovement._meta.fields]


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    quantity_outstanding = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'item', 'item_name', 'item_code', 'quantity_ordered',
            'quantity_received', 'quantity_outstanding', 'unit_cost',
            'line_total', 'batch_number',
        ]
        read_only_fields = ['quantity_received']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, required=False)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = '__all__'
        read_only_fields = ['status', 'received_date', 'order_date']

    def create(self, validated_data):
        lines = validated_data.pop('lines', [])
        purchase_order = PurchaseOrder.objects.create(**validated_data)
        for line in lines:
            PurchaseOrderLine.objects.create(purchase_order=purchase_order, **line)
        return purchase_order

    def update(self, instance, validated_data):
        # Lines are managed through the receive action, not by wholesale replacement.
        validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CatalogItemSerializer(serializers.ModelSerializer):
    """A row of the published catalogue, with enough context to stock it."""

    section_name = serializers.CharField(source='section.name', read_only=True)
    section_full_name = serializers.CharField(source='section.full_name', read_only=True)
    subsection = serializers.CharField(source='section.subsection', read_only=True)
    doc = serializers.CharField(source='section.doc', read_only=True)
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    is_stockable = serializers.BooleanField(read_only=True)
    #: Whether this boutique already stocks it, so the UI can offer "Add to
    #: inventory" once rather than creating a second row for the same material.
    stocked_item_id = serializers.SerializerMethodField()

    class Meta:
        model = CatalogItem
        fields = [
            'id', 'name', 'item_type', 'item_type_display', 'default_unit',
            'legacy_category', 'is_active', 'is_stockable',
            'doc', 'section_name', 'subsection', 'section_full_name', 'stocked_item_id',
        ]

    def get_stocked_item_id(self, obj):
        existing = getattr(obj, 'stocked_as', None)
        if existing is None:
            return None
        row = existing.all()[:1]
        return str(row[0].id) if row else None


class CatalogSectionSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    doc_display = serializers.CharField(source='get_doc_display', read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CatalogSection
        fields = ['id', 'doc', 'doc_display', 'sequence', 'name', 'subsection',
                  'full_name', 'item_count']


class StockLocationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    tailor_name = serializers.CharField(source='tailor.name', read_only=True, default=None)

    class Meta:
        model = StockLocation
        fields = ['id', 'name', 'kind', 'kind_display', 'is_default', 'is_active',
                  'sequence', 'tailor', 'tailor_name']


class LocationStockSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)
    location_kind = serializers.CharField(source='location.kind', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    unit_display = serializers.CharField(source='item.get_unit_display', read_only=True)

    class Meta:
        model = LocationStock
        fields = ['id', 'item', 'item_name', 'item_code', 'location', 'location_name',
                  'location_kind', 'quantity', 'unit_display', 'updated_at']
