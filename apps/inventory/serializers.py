from rest_framework import serializers

from .models import (
    BillOfMaterials, BomLine, CatalogItem, CatalogSection, Category,
    CustomerMaterial, CustomerMaterialMovement, DEFAULT_UNIT_BY_CATEGORY,
    InventoryItem, LocationStock, OrderMaterialLine, OrderMaterialPlan,
    PurchaseOrder, PurchaseOrderLine, StockLocation, StockMovement, Supplier,
    Unit, UnitConversion,
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


class UnitConversionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitConversion
        fields = ['id', 'item', 'from_unit', 'to_unit', 'factor']


class BomLineSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)

    class Meta:
        model = BomLine
        fields = [
            'id', 'bom', 'role', 'role_display', 'inventory_item', 'catalog_item',
            'description', 'material_name', 'quantity', 'quantity_formula', 'unit',
            'unit_display', 'waste_percent', 'is_optional', 'is_customer_supplied',
            'sequence', 'notes',
        ]

    def validate(self, attrs):
        """A line must name a material, and its formula must be a valid one.

        Checked here as well as by the database constraint so the operator gets
        a readable message instead of an integrity error, and so a broken formula
        is caught when it is written rather than when an order tries to use it.
        """
        from .formula import FormulaError, validate_syntax

        merged = {**({} if self.instance is None else {
            'inventory_item': self.instance.inventory_item,
            'catalog_item': self.instance.catalog_item,
            'is_customer_supplied': self.instance.is_customer_supplied,
        }), **attrs}

        if not (merged.get('inventory_item') or merged.get('catalog_item')
                or merged.get('is_customer_supplied')):
            raise serializers.ValidationError(
                'A line must name an inventory item, a catalogue item, or be '
                'marked as customer-supplied.')

        # A garment category or a payment gateway is catalogued but cannot be
        # consumed by a garment, so it has no business on a recipe.
        catalog_item = merged.get('catalog_item')
        if catalog_item is not None and not catalog_item.is_stockable:
            raise serializers.ValidationError({'catalog_item': (
                f"'{catalog_item.name}' is a "
                f"{catalog_item.get_item_type_display().lower()} and cannot be "
                f"used as a material.")})

        formula = attrs.get('quantity_formula')
        if formula:
            try:
                # Structural check, not an evaluation. The measurements a
                # formula reads do not exist until an order does, so it cannot
                # be run here; validate_syntax walks every node instead, which
                # means an unbound name is fine and a forbidden construct is
                # caught wherever it sits in the expression.
                validate_syntax(formula)
            except FormulaError as exc:
                raise serializers.ValidationError({'quantity_formula': str(exc)})
        return attrs


class BillOfMaterialsSerializer(serializers.ModelSerializer):
    lines = BomLineSerializer(many=True, read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True, default=None)
    line_count = serializers.IntegerField(source='lines.count', read_only=True)

    class Meta:
        model = BillOfMaterials
        fields = ['id', 'name', 'template', 'template_name', 'design', 'version',
                  'is_active', 'notes', 'lines', 'line_count', 'created_at', 'updated_at']
        read_only_fields = ['version']

    def validate(self, attrs):
        """Refuse a duplicate version before the database has to.

        DRF's UniqueTogetherValidator short-circuits as soon as any component of
        the key is None (rest_framework/validators.py), and template or design
        being null is the ordinary case here -- so without this the partial
        constraints in Meta would surface as an IntegrityError 500 rather than a
        400 naming the clash.
        """
        merged = {**({} if self.instance is None else {
            'name': self.instance.name,
            'template': self.instance.template,
            'design': self.instance.design,
        }), **attrs}

        version = getattr(self.instance, 'version', 1)
        clash = BillOfMaterials.objects.filter(
            template=merged.get('template'), design=merged.get('design'),
            version=version)
        if merged.get('template') is None and merged.get('design') is None:
            clash = clash.filter(name=merged.get('name'))
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(
                {'version': f'A version {version} of this recipe already exists.'})
        return attrs


class OrderMaterialLineSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)
    outstanding_reservation = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True, default=None)
    available_stock = serializers.DecimalField(
        source='item.available_stock', max_digits=12, decimal_places=3,
        read_only=True, default=None)

    class Meta:
        model = OrderMaterialLine
        fields = [
            'id', 'plan', 'bom_line', 'item', 'item_code', 'role', 'role_display',
            'material_name', 'unit', 'unit_display', 'required_quantity',
            'reserved_quantity', 'consumed_quantity', 'wasted_quantity',
            'returned_quantity', 'outstanding_reservation', 'available_stock',
            'is_customer_supplied',
            'gathered_at', 'gathered_by_name', 'photos', 'sequence',
        ]
        read_only_fields = fields


class OrderMaterialPlanSerializer(serializers.ModelSerializer):
    lines = OrderMaterialLineSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_code = serializers.CharField(source='order.order_id', read_only=True)
    bom_name = serializers.CharField(source='bom.name', read_only=True)

    class Meta:
        model = OrderMaterialPlan
        fields = ['id', 'order', 'order_code', 'bom', 'bom_name', 'bom_version',
                  'status', 'status_display', 'variables', 'packaging_deducted_at',
                  'lines', 'created_at', 'updated_at']
        read_only_fields = fields


class CustomerMaterialMovementSerializer(serializers.ModelSerializer):
    movement_type_display = serializers.CharField(
        source='get_movement_type_display', read_only=True)

    class Meta:
        model = CustomerMaterialMovement
        fields = ['id', 'material', 'movement_type', 'movement_type_display', 'quantity',
                  'previous_remaining', 'new_remaining', 'user_name_snapshot',
                  'remarks', 'created_at']
        read_only_fields = fields


class CustomerMaterialSerializer(serializers.ModelSerializer):
    remaining_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True)
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)
    order_code = serializers.CharField(source='order.order_id', read_only=True)

    class Meta:
        model = CustomerMaterial
        fields = ['id', 'order', 'order_code', 'kind', 'kind_display', 'name',
                  'description', 'unit', 'unit_display', 'received_quantity',
                  'used_quantity', 'returned_quantity', 'damaged_quantity',
                  'remaining_quantity', 'received_at', 'notes']
        # Balances move only through recorded movements, exactly as boutique
        # stock does. Editing them directly would leave the ledger disagreeing
        # with the figure it is supposed to explain.
        read_only_fields = ['received_quantity', 'used_quantity', 'returned_quantity',
                            'damaged_quantity', 'remaining_quantity', 'received_at']
