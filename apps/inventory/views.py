from django.db import transaction
from django.db.models import Count, F, Sum, DecimalField, ExpressionWrapper
from django.utils import timezone
from rest_framework import status, viewsets
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    BillOfMaterials, BomLine, CatalogItem, CatalogSection, Category, CustomerMaterial,
    CustomerMaterialMovement, InventoryItem, LocationStock, OrderMaterialLine,
    OrderMaterialPlan, PurchaseOrder, StockLocation, StockMovement, Supplier, Unit,
    UnitConversion, DEFAULT_UNIT_BY_CATEGORY, STOCKABLE_ITEM_TYPES,
)
from .serializers import (
    BillOfMaterialsSerializer, BomLineSerializer, CatalogItemSerializer,
    CatalogSectionSerializer, CustomerMaterialMovementSerializer,
    CustomerMaterialSerializer, LocationStockSerializer, OrderMaterialPlanSerializer,
    StockLocationSerializer, UnitConversionSerializer,
    InventoryItemSerializer, InventoryItemSummarySerializer, PurchaseOrderSerializer,
    StockMovementSerializer, SupplierSerializer,
)
from core.permissions import OwnerOnly

from .services import InventoryService


def _as_bool(value):
    """Parse a flag from a request body.

    bool('false') is True, so a plain truth-test on a JSON string turns "false"
    into yes -- which for include_optional means quietly reserving optional
    materials the caller asked to leave out.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


class SupplierViewSet(viewsets.ModelViewSet):
    # Supplier names, phone numbers, email addresses and GST numbers are the
    # boutique's trading relationships, and they sat one URL away from an
    # InventoryReportViewSet that correctly refuses the same commercial data to
    # anyone but the Owner. RolePermission's blanket SAFE_METHODS grant meant
    # any signed-in tailor could read the lot.
    permission_classes = [OwnerOnly]
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer


class InventoryItemViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryItemSerializer

    def get_serializer_class(self):
        # The list is a stock table; the full record with supplier and descriptors
        # is only needed when one item is opened.
        if self.action == 'list':
            return InventoryItemSummarySerializer
        return InventoryItemSerializer

    def get_queryset(self):
        queryset = InventoryItem.objects.all()
        if self.action != 'list':
            queryset = queryset.select_related('supplier')

        params = self.request.query_params
        if category := params.get('category'):
            queryset = queryset.filter(category=category)
        if item_status := params.get('status'):
            queryset = queryset.filter(status=item_status)
        if search := params.get('search'):
            queryset = queryset.filter(name__icontains=search)
        if params.get('needs_reorder') == 'true':
            queryset = queryset.filter(
                current_stock__lte=F('reserved_stock') + F('reorder_level')
            )
        return queryset

    @action(detail=False, methods=['GET'], url_path='options')
    def options_metadata(self, request):
        """Categories, units and each category's default unit, for the item form."""
        return Response({
            'categories': [{'value': c.value, 'label': c.label} for c in Category],
            'units': [{'value': u.value, 'label': u.label} for u in Unit],
            'default_unit_by_category': {k: v for k, v in DEFAULT_UNIT_BY_CATEGORY.items()},
        })

    @action(detail=False, methods=['GET'], url_path='summary')
    def summary(self, request):
        """Stock valuation plus what needs attention."""
        items = self.get_queryset()
        value = items.aggregate(
            total=Sum(ExpressionWrapper(
                F('current_stock') * F('purchase_price'),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ))
        )['total'] or 0

        out_of_stock = items.filter(current_stock__lte=F('reserved_stock'))
        reorder = items.filter(
            current_stock__lte=F('reserved_stock') + F('reorder_level')
        ).exclude(pk__in=out_of_stock.values('pk'))
        # Nothing bought and nothing moved in 90 days.
        stale_before = timezone.now() - timezone.timedelta(days=90)
        dead = items.filter(current_stock__gt=0).exclude(
            movements__created_at__gte=stale_before
        ).distinct()

        return Response({
            'item_count': items.count(),
            'inventory_value': value,
            'out_of_stock_count': out_of_stock.count(),
            'needs_reorder_count': reorder.count(),
            'dead_stock_count': dead.count(),
            'out_of_stock': InventoryItemSummarySerializer(out_of_stock[:25], many=True).data,
            'needs_reorder': InventoryItemSummarySerializer(reorder[:25], many=True).data,
            'dead_stock': InventoryItemSummarySerializer(dead[:25], many=True).data,
        })

    @action(detail=True, methods=['GET'], url_path='movements')
    def movements(self, request, pk=None):
        item = self.get_object()
        ledger = item.movements.select_related('order', 'performed_by', 'item')[:100]
        return Response(StockMovementSerializer(ledger, many=True).data)

    # --- stock operations. Each returns the updated item. ---------------

    def _apply(self, request, operation, **extra):
        item = self.get_object()
        try:
            operation(
                item,
                request.data.get('quantity'),
                user=request.user,
                remarks=request.data.get('remarks', ''),
                **extra,
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        item.refresh_from_db()
        return Response(InventoryItemSerializer(item).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='stock-in')
    def stock_in(self, request, pk=None):
        return self._apply(request, InventoryService.stock_in)

    @action(detail=True, methods=['POST'], url_path='reserve')
    def reserve(self, request, pk=None):
        return self._apply(request, InventoryService.reserve, order=self._order(request))

    @action(detail=True, methods=['POST'], url_path='release')
    def release(self, request, pk=None):
        return self._apply(request, InventoryService.release, order=self._order(request))

    # issue/damage/scrap/adjust used to name no location at all, while
    # consume, waste, goods-receipt, supplier-return, customer-return and
    # transfer all resolved one through _location. record_movement then
    # substituted default_location() for any stock-out that named none -- so
    # once the owner used the Locations tab to move material to the Workshop,
    # Main Store held zero and every one of these four failed against a
    # location they had never chosen. Four actions ignoring a helper their six
    # siblings honour was the whole bug.
    @action(detail=True, methods=['POST'], url_path='issue')
    def issue(self, request, pk=None):
        return self._apply(
            request, InventoryService.issue,
            order=self._order(request),
            stage_key=request.data.get('stage_key'),
            from_location=self._location(request, 'from_location'),
        )

    @action(detail=True, methods=['POST'], url_path='return')
    def return_material(self, request, pk=None):
        return self._apply(request, InventoryService.return_stock, order=self._order(request))

    @action(detail=True, methods=['POST'], url_path='damage')
    def damage(self, request, pk=None):
        return self._apply(request, InventoryService.damage,
                           from_location=self._location(request, 'from_location'))

    @action(detail=True, methods=['POST'], url_path='scrap')
    def scrap(self, request, pk=None):
        return self._apply(request, InventoryService.scrap,
                           from_location=self._location(request, 'from_location'))

    @action(detail=True, methods=['POST'], url_path='goods-receipt')
    def goods_receipt(self, request, pk=None):
        return self._apply(request, InventoryService.goods_receipt,
                           to_location=self._location(request, 'to_location'))

    @action(detail=True, methods=['POST'], url_path='consume')
    def consume(self, request, pk=None):
        return self._apply(
            request, InventoryService.consume,
            order=self._order(request),
            stage_key=request.data.get('stage_key'),
            from_location=self._location(request, 'from_location'),
        )

    @action(detail=True, methods=['POST'], url_path='waste')
    def waste(self, request, pk=None):
        return self._apply(request, InventoryService.waste,
                           order=self._order(request),
                           from_location=self._location(request, 'from_location'))

    @action(detail=True, methods=['POST'], url_path='customer-return')
    def customer_return(self, request, pk=None):
        return self._apply(request, InventoryService.customer_return,
                           order=self._order(request),
                           to_location=self._location(request, 'to_location'))

    @action(detail=True, methods=['POST'], url_path='supplier-return')
    def supplier_return(self, request, pk=None):
        return self._apply(request, InventoryService.supplier_return,
                           from_location=self._location(request, 'from_location'))

    @action(detail=True, methods=['POST'], url_path='transfer')
    def transfer(self, request, pk=None):
        """Move stock between two locations."""
        item = self.get_object()
        try:
            InventoryService.transfer(
                item, request.data.get('quantity'),
                from_location=self._location(request, 'from_location', required=True),
                to_location=self._location(request, 'to_location', required=True),
                user=request.user, remarks=request.data.get('remarks', ''),
                order=self._order(request),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        item.refresh_from_db()
        return Response(InventoryItemSerializer(item).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'], url_path='locations')
    def locations(self, request, pk=None):
        """Where this item's stock actually is."""
        item = self.get_object()
        return Response({
            'item': item.name,
            'total': item.current_stock,
            'breakdown': InventoryService.location_breakdown(item),
        })

    @staticmethod
    def _location(request, key, required=False):
        """Resolve a location id from the request body.

        Raises DRF's ValidationError rather than ValueError: these are evaluated
        while building the arguments to _apply, outside its try block, so a
        ValueError here would escape as a 500 instead of the 400 it is.
        """
        value = request.data.get(key)
        if not value:
            if required:
                raise ValidationError({key: 'This field is required.'})
            return None
        # A UUID primary key raises at filter() build time for a malformed
        # value, before the None check below could report it as a 400.
        try:
            location = StockLocation.objects.filter(pk=value).first()
        except (ValueError, TypeError, DjangoValidationError):
            raise ValidationError({key: f'{value!r} is not a valid location id.'})
        if location is None:
            raise ValidationError({key: f'No stock location with id {value}.'})
        return location

    @action(detail=True, methods=['POST'], url_path='adjust')
    def adjust(self, request, pk=None):
        item = self.get_object()
        try:
            InventoryService.adjust(
                item, request.data.get('counted_quantity'),
                user=request.user, remarks=request.data.get('remarks', ''),
                from_location=self._location(request, 'from_location'),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        item.refresh_from_db()
        return Response(InventoryItemSerializer(item).data, status=status.HTTP_200_OK)

    @staticmethod
    def _order(request):
        from crm_api.models import Order
        order_id = request.data.get('order_id')
        return Order.objects.filter(id=order_id).first() if order_id else None


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """The ledger is append-only, so it is read-only over HTTP."""

    serializer_class = StockMovementSerializer

    def get_queryset(self):
        queryset = StockMovement.objects.select_related('item', 'order', 'performed_by')
        params = self.request.query_params
        if item_id := params.get('item'):
            queryset = queryset.filter(item_id=item_id)
        if order_id := params.get('order'):
            queryset = queryset.filter(order_id=order_id)
        if movement_type := params.get('movement_type'):
            queryset = queryset.filter(movement_type=movement_type)
        return queryset


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    # What the boutique pays, and to whom. Same commercial position OwnerOnly
    # already protects on the reports endpoint.
    permission_classes = [OwnerOnly]
    serializer_class = PurchaseOrderSerializer

    def get_queryset(self):
        return PurchaseOrder.objects.select_related('supplier').prefetch_related('lines__item')

    @action(detail=True, methods=['POST'], url_path='receive')
    def receive(self, request, pk=None):
        """Book in what actually arrived, line by line.

        Body: {"lines": [{"line_id": "...", "quantity": 5}, ...]}. Each receipt
        writes a PURCHASE movement, so goods-in is visible in the ledger.
        """
        purchase_order = self.get_object()
        received = request.data.get('lines') or []
        if not received:
            return Response({'error': 'Provide the lines received.'},
                            status=status.HTTP_400_BAD_REQUEST)

        lines_by_id = {str(line.id): line for line in purchase_order.lines.all()}
        try:
            for entry in received:
                line = lines_by_id.get(str(entry.get('line_id')))
                if not line:
                    raise ValueError(f"Line {entry.get('line_id')} is not on this purchase order.")
                quantity = entry.get('quantity')
                if quantity in (None, ''):
                    continue
                from decimal import Decimal
                quantity = Decimal(str(quantity))
                if quantity <= 0:
                    raise ValueError('Received quantity must be greater than zero.')
                if line.quantity_received + quantity > line.quantity_ordered:
                    raise ValueError(
                        f"Cannot receive {quantity} of {line.item.name} -- only "
                        f"{line.quantity_outstanding} outstanding on this order."
                    )
                InventoryService.purchase(
                    line.item, quantity, user=request.user,
                    remarks=f"Received against {purchase_order.po_number}",
                )
                line.quantity_received += quantity
                if entry.get('batch_number'):
                    line.batch_number = entry['batch_number']
                line.save(update_fields=['quantity_received', 'batch_number'])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        lines = purchase_order.lines.all()
        if all(line.quantity_outstanding <= 0 for line in lines):
            purchase_order.status = PurchaseOrder.Status.RECEIVED
            purchase_order.received_date = timezone.now().date()
        elif any(line.quantity_received > 0 for line in lines):
            purchase_order.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
        purchase_order.save(update_fields=['status', 'received_date'])

        return Response(PurchaseOrderSerializer(purchase_order).data, status=status.HTTP_200_OK)


class CatalogSectionViewSet(viewsets.ReadOnlyModelViewSet):
    """The published catalogue's sections, with how many items each holds."""

    serializer_class = CatalogSectionSerializer

    def get_queryset(self):
        queryset = CatalogSection.objects.annotate(item_count=Count('items'))
        if doc := self.request.query_params.get('doc'):
            queryset = queryset.filter(doc=doc)
        return queryset


class CatalogItemViewSet(viewsets.ReadOnlyModelViewSet):
    """Browse the catalogue, and stock a row from it.

    Read-only by design: the catalogue is loaded from the source documents by a
    migration, so it is not something a boutique edits. What a boutique does is
    decide which of these it actually holds, which is what `stock` does.
    """

    serializer_class = CatalogItemSerializer

    def get_queryset(self):
        queryset = (CatalogItem.objects
                    .select_related('section')
                    .prefetch_related('stocked_as')
                    .filter(is_active=True))
        params = self.request.query_params
        if section := params.get('section'):
            queryset = queryset.filter(section_id=section)
        if doc := params.get('doc'):
            queryset = queryset.filter(section__doc=doc)
        if name := params.get('section_name'):
            queryset = queryset.filter(section__name=name)
        if item_type := params.get('item_type'):
            queryset = queryset.filter(item_type=item_type)
        if params.get('stockable') == 'true':
            queryset = queryset.filter(item_type__in=STOCKABLE_ITEM_TYPES)
        if search := params.get('search'):
            queryset = queryset.filter(name__icontains=search)
        return queryset

    @action(detail=False, methods=['get'])
    def sections(self, request):
        """The whole taxonomy in one call, for the catalogue browser's tree."""
        rows = (CatalogSection.objects.annotate(item_count=Count('items'))
                .order_by('doc', 'sequence', 'subsection'))
        return Response(CatalogSectionSerializer(rows, many=True).data)

    @action(detail=True, methods=['post'])
    def stock(self, request, pk=None):
        """Start stocking this catalogue row: create the InventoryItem for it.

        Idempotent -- a second call returns the existing row rather than making a
        duplicate, because the obvious way to double-click a button should not
        leave the boutique with the same material twice.
        """
        catalog_item = self.get_object()
        if not catalog_item.is_stockable:
            return Response(
                {'detail': f"'{catalog_item.name}' is a "
                           f"{catalog_item.get_item_type_display().lower()} and cannot hold stock."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = InventoryItem.objects.filter(catalog_item=catalog_item).first()
        if existing:
            return Response(InventoryItemSerializer(existing).data, status=status.HTTP_200_OK)

        payload = request.data or {}
        item = InventoryItem.objects.create(
            item_code=payload.get('item_code') or _next_item_code(catalog_item),
            name=payload.get('name') or catalog_item.name,
            category=catalog_item.legacy_category,
            sub_category=catalog_item.section.full_name,
            catalog_item=catalog_item,
            unit=payload.get('unit') or catalog_item.default_unit,
            purchase_price=payload.get('purchase_price') or 0,
            selling_price=payload.get('selling_price') or 0,
            reorder_level=payload.get('reorder_level') or 0,
            minimum_stock=payload.get('minimum_stock') or 0,
        )
        return Response(InventoryItemSerializer(item).data, status=status.HTTP_201_CREATED)


def _next_item_code(catalog_item):
    """A readable, unique code: first letters of the section plus a counter."""
    import re

    initials = ''.join(word[0] for word in re.findall(r'[A-Za-z]+', catalog_item.section.name))[:3].upper()
    prefix = f"CAT-{initials or 'GEN'}"
    taken = set(InventoryItem.objects.filter(item_code__startswith=prefix)
                .values_list('item_code', flat=True))
    n = 1
    while f"{prefix}-{n:04d}" in taken:
        n += 1
    return f"{prefix}-{n:04d}"


class StockLocationViewSet(viewsets.ModelViewSet):
    """The places stock can be. Seeded with the eight the specification names."""

    serializer_class = StockLocationSerializer

    def get_queryset(self):
        queryset = StockLocation.objects.all()
        if self.request.query_params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        if kind := self.request.query_params.get('kind'):
            queryset = queryset.filter(kind=kind)
        return queryset

    def perform_destroy(self, instance):
        """Refuse to delete a location that still holds something.

        PROTECT on LocationStock would raise a 500 here; this turns the same
        refusal into an answer that says what is still there.
        """
        held = instance.stocks.filter(quantity__gt=0).count()
        if held:
            raise ValidationError(
                {'detail': f"'{instance.name}' still holds {held} item(s). "
                           f"Move them elsewhere before removing it."}
            )
        if instance.is_default:
            raise ValidationError({'detail': 'The default location cannot be removed.'})
        instance.delete()

    @action(detail=True, methods=['GET'], url_path='stock')
    def stock(self, request, pk=None):
        """Everything currently held at this location."""
        rows = (LocationStock.objects.filter(location=self.get_object(), quantity__gt=0)
                .select_related('item', 'location').order_by('item__name'))
        return Response(LocationStockSerializer(rows, many=True).data)


class LocationStockViewSet(viewsets.ReadOnlyModelViewSet):
    """The per-location breakdown, filterable by item or location."""

    serializer_class = LocationStockSerializer

    def get_queryset(self):
        queryset = (LocationStock.objects.select_related('item', 'location')
                    .filter(quantity__gt=0))
        params = self.request.query_params
        if item := params.get('item'):
            queryset = queryset.filter(item_id=item)
        if location := params.get('location'):
            queryset = queryset.filter(location_id=location)
        return queryset


class BillOfMaterialsViewSet(viewsets.ModelViewSet):
    """A garment's recipe, and what it needs for a given set of measurements."""

    serializer_class = BillOfMaterialsSerializer

    def get_queryset(self):
        queryset = (BillOfMaterials.objects
                    .select_related('template')
                    .prefetch_related('lines__inventory_item', 'lines__catalog_item'))
        params = self.request.query_params
        if template := params.get('template'):
            queryset = queryset.filter(template_id=template)
        if design := params.get('design'):
            queryset = queryset.filter(design_id=design)
        if params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    @action(detail=True, methods=['POST'], url_path='requirements')
    def requirements(self, request, pk=None):
        """What this BOM needs, given a set of measurements.

        POST rather than GET because the measurements are a body, not a filter,
        and there can be a dozen of them.
        """
        from . import bom as bom_service

        # request.data is only dict-like when the body is a JSON object; a bare
        # list or string has no .get and would be an AttributeError 500.
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'Expected a JSON object.'})

        variables = request.data.get('variables')
        if variables is None:
            variables = {}
        if not isinstance(variables, dict):
            raise ValidationError({'variables': 'Expected an object of measurement values.'})

        include_optional = _as_bool(request.data.get('include_optional'))
        try:
            summary = bom_service.summarise(
                self.get_object(), variables, include_optional=include_optional)
        except bom_service.BomError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(summary)

    @action(detail=True, methods=['POST'], url_path='new-version')
    def new_version(self, request, pk=None):
        """Copy this BOM to the next version, and deactivate the old one.

        A BOM an order was costed against must keep meaning what it meant, so a
        change raises a version rather than rewriting history.
        """
        source = self.get_object()
        if not source.is_active:
            raise ValidationError(
                {'detail': f"Version {source.version} has already been superseded. "
                           f"Version the active BOM instead."})

        # Locked and atomic: two people pressing the button at once would
        # otherwise both read the same highest version and both write it, and
        # the unique constraint does not catch it when template or design is
        # NULL, so the duplicate would simply stand.
        with transaction.atomic():
            siblings = BillOfMaterials.objects.select_for_update().filter(
                template=source.template, design=source.design)
            if source.template_id is None and source.design_id is None:
                # A standalone BOM has no template or design to be scoped by, so
                # its own name is the only identity it has. Without this every
                # standalone BOM in the tenant shares one version counter.
                siblings = siblings.filter(name=source.name)
            highest = siblings.order_by('-version').values_list(
                'version', flat=True).first() or 0
            return self._make_version(request, source, highest + 1)

    def _make_version(self, request, source, version):
        copy = BillOfMaterials.objects.create(
            name=source.name, template=source.template, design=source.design,
            version=version, notes=source.notes,
            created_by=request.user if request.user.is_authenticated else None,
        )
        BomLine.objects.bulk_create([
            BomLine(
                bom=copy, role=line.role, inventory_item=line.inventory_item,
                catalog_item=line.catalog_item, description=line.description,
                quantity=line.quantity, quantity_formula=line.quantity_formula,
                unit=line.unit, waste_percent=line.waste_percent,
                is_optional=line.is_optional, is_customer_supplied=line.is_customer_supplied,
                sequence=line.sequence, notes=line.notes,
            )
            for line in source.lines.all()
        ])
        source.is_active = False
        source.save(update_fields=['is_active', 'updated_at'])
        return Response(BillOfMaterialsSerializer(copy).data, status=status.HTTP_201_CREATED)


class BomLineViewSet(viewsets.ModelViewSet):
    serializer_class = BomLineSerializer

    def get_queryset(self):
        queryset = BomLine.objects.select_related('inventory_item', 'catalog_item')
        if bom := self.request.query_params.get('bom'):
            queryset = queryset.filter(bom_id=bom)
        return queryset


class UnitConversionViewSet(viewsets.ModelViewSet):
    serializer_class = UnitConversionSerializer

    def get_queryset(self):
        queryset = UnitConversion.objects.select_related('item')
        if item := self.request.query_params.get('item'):
            queryset = queryset.filter(item_id=item)
        return queryset


class OrderMaterialPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """An order's materials, through the whole ten-step lifecycle.

    Read-only as a resource: every state change is an explicit action, because
    "reserve" and "consume" are events with consequences in the stock ledger,
    not fields to be PATCHed.
    """

    serializer_class = OrderMaterialPlanSerializer

    def get_queryset(self):
        queryset = (OrderMaterialPlan.objects
                    .select_related('order', 'bom')
                    .prefetch_related('lines__item'))
        params = self.request.query_params
        if order := params.get('order'):
            try:
                queryset = queryset.filter(order_id=order)
            except (ValueError, TypeError, DjangoValidationError):
                raise ValidationError({'order': f'{order!r} is not a valid order id.'})
        if plan_status := params.get('status'):
            queryset = queryset.filter(status=plan_status)
        if params.get('live') == 'true':
            queryset = queryset.filter(status__in=[
                OrderMaterialPlan.Status.DRAFT, OrderMaterialPlan.Status.RESERVED,
                OrderMaterialPlan.Status.IN_PRODUCTION])
        return queryset

    @action(detail=False, methods=['POST'], url_path='plan')
    def plan(self, request):
        """Step 1: generate the plan for an order from a BOM."""
        from crm_api.models import Order
        from . import order_materials

        order = _get_or_400(Order, request.data.get('order'), 'order')
        bom = _get_or_400(BillOfMaterials, request.data.get('bom'), 'bom')
        variables = request.data.get('variables') or {}
        if not isinstance(variables, dict):
            raise ValidationError({'variables': 'Expected an object of measurement values.'})

        try:
            plan = order_materials.plan_materials(
                order, bom, variables, user=request.user,
                include_optional=_as_bool(request.data.get('include_optional')))
        except order_materials.MaterialPlanError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderMaterialPlanSerializer(plan).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['GET'], url_path='availability')
    def availability(self, request, pk=None):
        """Step 2: what this plan cannot currently be satisfied from."""
        from . import order_materials
        shortfalls = order_materials.check_availability(self.get_object())
        return Response({'is_available': not shortfalls, 'shortfalls': shortfalls})

    @action(detail=True, methods=['POST'], url_path='reserve')
    def reserve(self, request, pk=None):
        """Steps 3 and 4: reserve, once."""
        from . import order_materials
        try:
            result = order_materials.reserve(
                self.get_object(), user=request.user,
                allow_partial=_as_bool(request.data.get('allow_partial')))
        except (order_materials.MaterialPlanError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)

    @action(detail=True, methods=['POST'], url_path='consume')
    def consume(self, request, pk=None):
        """Steps 5, 6 and 7: what was actually used, and what was spoiled."""
        from . import order_materials
        plan = self.get_object()
        try:
            line = OrderMaterialLine.objects.filter(
                pk=request.data.get('line'), plan=plan).first()
        except (ValueError, TypeError, DjangoValidationError):
            raise ValidationError({'line': 'Not a valid line id.'})
        if line is None:
            raise ValidationError({'line': 'No such line on this plan.'})
        try:
            order_materials.confirm_consumption(
                line, request.data.get('used', 0),
                wasted=request.data.get('wasted', 0), user=request.user,
                from_location=self._location(request, 'from_location'))
        except (order_materials.MaterialPlanError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        plan.refresh_from_db()
        return Response(OrderMaterialPlanSerializer(plan).data)

    @action(detail=True, methods=['POST'], url_path='release-unused')
    def release_unused(self, request, pk=None):
        """Step 8: hand back what was reserved and never used."""
        from . import order_materials
        try:
            released = order_materials.release_unused(self.get_object(), user=request.user)
        except (order_materials.MaterialPlanError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'released': released})

    @action(detail=True, methods=['POST'], url_path='deduct-packaging')
    def deduct_packaging(self, request, pk=None):
        """Step 9: consume packaging and labels at dispatch."""
        from . import order_materials
        try:
            deducted = order_materials.deduct_packaging(
                self.get_object(), user=request.user,
                from_location=self._location(request, 'from_location'))
        except (order_materials.MaterialPlanError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'deducted': deducted})

    @action(detail=True, methods=['GET'], url_path='reconcile')
    def reconcile(self, request, pk=None):
        """Step 10: does this order's material account add up?"""
        from . import order_materials
        return Response(order_materials.reconcile(self.get_object()))

    @action(detail=True, methods=['POST'], url_path='close')
    def close(self, request, pk=None):
        from . import order_materials
        try:
            plan = order_materials.close(
                self.get_object(), user=request.user,
                release_outstanding=_as_bool(request.data.get('release_outstanding', True)))
        except (order_materials.MaterialPlanError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderMaterialPlanSerializer(plan).data)

    @action(detail=True, methods=['POST'], url_path='cancel')
    def cancel(self, request, pk=None):
        from . import order_materials
        try:
            plan = order_materials.cancel(self.get_object(), user=request.user)
        except (order_materials.MaterialPlanError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderMaterialPlanSerializer(plan).data)

    @staticmethod
    def _location(request, key):
        value = request.data.get(key)
        if not value:
            return None
        # StockLocation.id is a UUID, so a malformed value raises at filter()
        # build time -- before the None check below could ever report it.
        try:
            location = StockLocation.objects.filter(pk=value).first()
        except (ValueError, TypeError, DjangoValidationError):
            raise ValidationError({key: f'{value!r} is not a valid location id.'})
        if location is None:
            raise ValidationError({key: f'No stock location with id {value}.'})
        return location


class CustomerMaterialViewSet(viewsets.ModelViewSet):
    """What the customer brought in. Never boutique stock.

    No DELETE: removing a row cascades away its movement ledger, and "where did
    the other two metres of my sari go" is precisely the question that ledger
    exists to answer. Material recorded in error is returned or corrected, not
    erased.
    """

    serializer_class = CustomerMaterialSerializer
    http_method_names = ['get', 'post', 'patch', 'put', 'head', 'options']

    def get_queryset(self):
        queryset = CustomerMaterial.objects.select_related('order')
        if order := self.request.query_params.get('order'):
            try:
                queryset = queryset.filter(order_id=order)
            except (ValueError, TypeError, DjangoValidationError):
                raise ValidationError({'order': f'{order!r} is not a valid order id.'})
        if kind := self.request.query_params.get('kind'):
            queryset = queryset.filter(kind=kind)
        return queryset

    def create(self, request, *args, **kwargs):
        """Receiving material goes through the service, so it is logged."""
        from crm_api.models import Order
        from . import order_materials

        order = _get_or_400(Order, request.data.get('order'), 'order')

        # Validated rather than trusted: this action does not go through the
        # serializer's create(), so nothing else checks the payload at all.
        name = str(request.data.get('name') or '').strip()
        if not name:
            raise ValidationError({'name': 'This field is required.'})
        unit = request.data.get('unit') or Unit.METER
        if unit not in Unit.values:
            raise ValidationError({'unit': f'{unit!r} is not a valid unit.'})
        kind = request.data.get('kind') or CustomerMaterial.Kind.FABRIC
        if kind not in CustomerMaterial.Kind.values:
            raise ValidationError({'kind': f'{kind!r} is not a valid kind.'})

        try:
            material = order_materials.receive_customer_material(
                order,
                name=name[:200],
                quantity=request.data.get('received_quantity', 0),
                unit=unit,
                kind=kind,
                description=request.data.get('description'),
                notes=request.data.get('notes'),
                user=request.user,
            )
        except order_materials.MaterialPlanError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CustomerMaterialSerializer(material).data,
                        status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        """Descriptive fields only.

        `order` and `unit` are fixed once the material is in the boutique's
        hands: re-pointing it at another order hands one customer's silk to
        another, and changing the unit silently reinterprets every balance and
        every movement already recorded against it.
        """
        for locked_field in ('order', 'unit'):
            if locked_field in serializer.validated_data:
                if getattr(serializer.instance, locked_field) != serializer.validated_data[locked_field]:
                    raise ValidationError({locked_field: (
                        f'{locked_field} cannot be changed once the material has '
                        f'been received.')})
        serializer.save()

    def _record(self, request, movement_type):
        from . import order_materials
        try:
            material = order_materials.record_customer_material(
                self.get_object(), movement_type, request.data.get('quantity', 0),
                user=request.user, remarks=request.data.get('remarks', ''))
        except order_materials.MaterialPlanError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CustomerMaterialSerializer(material).data)

    @action(detail=True, methods=['POST'], url_path='use')
    def use(self, request, pk=None):
        return self._record(request, CustomerMaterialMovement.Type.USED)

    @action(detail=True, methods=['POST'], url_path='return')
    def return_to_customer(self, request, pk=None):
        return self._record(request, CustomerMaterialMovement.Type.RETURNED)

    @action(detail=True, methods=['POST'], url_path='damage')
    def damage(self, request, pk=None):
        return self._record(request, CustomerMaterialMovement.Type.DAMAGED)

    @action(detail=True, methods=['GET'], url_path='movements')
    def movements(self, request, pk=None):
        rows = self.get_object().movements.all()[:100]
        return Response(CustomerMaterialMovementSerializer(rows, many=True).data)


def _get_or_400(model, pk, field):
    """Resolve a related object, reporting a bad id as a 400.

    The filter itself can raise: Order has an integer primary key, so a UUID
    string reaches the database layer as ValueError and would escape as a 500
    rather than as the bad request it plainly is.
    """
    if not pk:
        raise ValidationError({field: 'This field is required.'})
    try:
        instance = model.objects.filter(pk=pk).first()
    except (ValueError, TypeError, DjangoValidationError):
        raise ValidationError({field: f'{pk!r} is not a valid {model.__name__} id.'})
    if instance is None:
        raise ValidationError({field: f'No {model.__name__} with id {pk}.'})
    return instance


class InventoryReportViewSet(viewsets.ViewSet):
    """The sixteen figures the specification asks the inventory to state.

    Owner only. Stock valuation, cost per order and supplier performance are
    the boutique's commercial position, and a tailor needs none of it to sew.

    A ViewSet rather than a ModelViewSet: a report is not a resource with a
    primary key, it is a question asked of several tables at once.
    """

    permission_classes = [OwnerOnly]

    @staticmethod
    def _window(request):
        """Parse ?since= / ?until=, reporting a bad date rather than ignoring it.

        Silently dropping an unparseable date is the worst option: the caller
        gets a report over all time and no indication it is not the period they
        asked for.
        """
        import datetime

        from django.utils import timezone
        from django.utils.dateparse import parse_date, parse_datetime

        window = {}
        for key in ('since', 'until'):
            raw = request.query_params.get(key)
            if not raw:
                continue
            # The parser is chosen by what the string actually contains, not by
            # trying one and falling back. parse_datetime() accepts a bare date
            # and hands back midnight, so `parse_datetime(raw) or parse_date(raw)`
            # never reaches the date branch at all -- and ?until=<today> silently
            # meant "up to midnight this morning", excluding everything that
            # happened today, which is the opposite of what it plainly means.
            raw = raw.strip()
            has_time = 'T' in raw or ':' in raw
            parsed = parse_datetime(raw) if has_time else parse_date(raw)
            if parsed is None:
                raise ValidationError({key: f'{raw!r} is not a valid date.'})

            if not has_time:
                moment = datetime.time.max if key == 'until' else datetime.time.min
                parsed = datetime.datetime.combine(parsed, moment)
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            window[key] = parsed
        return window

    @staticmethod
    def _limit(request, default=100, ceiling=500):
        raw = request.query_params.get('limit')
        if not raw:
            return default
        try:
            limit = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({'limit': f'{raw!r} is not a number.'})
        if limit < 1:
            raise ValidationError({'limit': 'Must be at least 1.'})
        return min(limit, ceiling)

    @action(detail=False, methods=['GET'], url_path='stock-position')
    def stock_position(self, request):
        """Current, reserved, available, low stock, reorder and value."""
        from . import reports
        return Response(reports.stock_position())

    @action(detail=False, methods=['GET'], url_path='low-stock')
    def low_stock(self, request):
        from . import reports
        return Response(reports.low_stock(limit=self._limit(request)))

    @action(detail=False, methods=['GET'], url_path='consumption')
    def consumption(self, request):
        """?scope=fabric|embroidery|packaging, or omit for all material."""
        from . import reports
        try:
            return Response(reports.consumption(
                request.query_params.get('scope') or None,
                limit=self._limit(request), **self._window(request)))
        except ValueError as exc:
            raise ValidationError({'scope': str(exc)})

    @action(detail=False, methods=['GET'], url_path='loss-rates')
    def loss_rates(self, request):
        """Waste % and damage %, with the figures behind them."""
        from . import reports
        return Response(reports.loss_rates(**self._window(request)))

    @action(detail=False, methods=['GET'], url_path='cost-per-order')
    def cost_per_order(self, request):
        from . import reports
        return Response(reports.cost_per_order(limit=self._limit(request)))

    @action(detail=False, methods=['GET'], url_path='order-usage')
    def order_usage(self, request):
        """?order=<id> -- everything one order used."""
        from crm_api.models import Order
        from . import reports
        order = _get_or_400(Order, request.query_params.get('order'), 'order')
        return Response(reports.order_material_usage(order))

    @action(detail=False, methods=['GET'], url_path='suppliers')
    def suppliers(self, request):
        from . import reports
        window = self._window(request)
        return Response(reports.supplier_performance(
            since=window.get('since'), limit=self._limit(request, default=50)))

    @action(detail=False, methods=['GET'], url_path='movements')
    def movements(self, request):
        from crm_api.models import Order
        from . import reports

        params = self.request.query_params
        item = order = location = None
        if value := params.get('item'):
            item = _get_or_400(InventoryItem, value, 'item')
        if value := params.get('order'):
            order = _get_or_400(Order, value, 'order')
        if value := params.get('location'):
            location = _get_or_400(StockLocation, value, 'location')

        movement_type = params.get('movement_type')
        if movement_type and movement_type not in StockMovement.Type.values:
            raise ValidationError(
                {'movement_type': f'{movement_type!r} is not a movement type.'})

        return Response(reports.movement_history(
            item=item, order=order, location=location, movement_type=movement_type,
            limit=self._limit(request, default=200), **self._window(request)))

    @action(detail=False, methods=['GET'], url_path='movement-summary')
    def movement_summary(self, request):
        from . import reports
        return Response(reports.movement_summary(**self._window(request)))

    @action(detail=False, methods=['GET'], url_path='dashboard')
    def dashboard(self, request):
        """Every report at once, for the module's landing screen."""
        from . import reports
        return Response(reports.dashboard(**self._window(request)))
