from decimal import Decimal, InvalidOperation

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
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


class SupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [OwnerOnly]
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer


class InventoryItemViewSet(viewsets.ModelViewSet):
    permission_classes = [OwnerOnly]
    serializer_class = InventoryItemSerializer

    def get_serializer_class(self):
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

        return Response({
            'categories': [{'value': c.value, 'label': c.label} for c in Category],
            'units': [{'value': u.value, 'label': u.label} for u in Unit],
            'default_unit_by_category': {k: v for k, v in DEFAULT_UNIT_BY_CATEGORY.items()},
        })

    @action(detail=False, methods=['GET'], url_path='summary')
    def summary(self, request):

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

        item = self.get_object()
        return Response({
            'item': item.name,
            'total': item.current_stock,
            'breakdown': InventoryService.location_breakdown(item),
        })

    @staticmethod
    def _location(request, key, required=False):
        value = request.data.get(key)
        if not value:
            if required:
                raise ValidationError({key: 'This field is required.'})
            return None
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
    permission_classes = [OwnerOnly]
    serializer_class = PurchaseOrderSerializer

    def get_queryset(self):
        return PurchaseOrder.objects.select_related('supplier').prefetch_related('lines__item')

    @action(detail=True, methods=['POST'], url_path='receive')
    def receive(self, request, pk=None):
        purchase_order = self.get_object()
        received = request.data.get('lines') or []
        if not received:
            return Response({'error': 'Provide the lines received.'},
                            status=status.HTTP_400_BAD_REQUEST)

        lines_by_id = {str(line.id): line for line in purchase_order.lines.all()}
        try:
            with transaction.atomic():
                for entry in received:
                    line = lines_by_id.get(str(entry.get('line_id')))
                    if not line:
                        raise ValueError(
                            f"Line {entry.get('line_id')} is not on this purchase order.")
                    quantity = entry.get('quantity')
                    if quantity in (None, ''):
                        continue
                    try:
                        quantity = Decimal(str(quantity))
                    except InvalidOperation:
                        raise ValueError(f"{quantity!r} is not a quantity.")
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

                lines = purchase_order.lines.all()
                if all(line.quantity_outstanding <= 0 for line in lines):
                    purchase_order.status = PurchaseOrder.Status.RECEIVED
                    purchase_order.received_date = timezone.now().date()
                elif any(line.quantity_received > 0 for line in lines):
                    purchase_order.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
                purchase_order.save(update_fields=['status', 'received_date'])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        purchase_order.refresh_from_db()
        return Response(PurchaseOrderSerializer(purchase_order).data,
                        status=status.HTTP_200_OK)


class CatalogSectionViewSet(viewsets.ReadOnlyModelViewSet):


    serializer_class = CatalogSectionSerializer

    def get_queryset(self):
        queryset = CatalogSection.objects.annotate(item_count=Count('items'))
        if doc := self.request.query_params.get('doc'):
            queryset = queryset.filter(doc=doc)
        return queryset


class CatalogItemViewSet(viewsets.ReadOnlyModelViewSet):

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

        rows = (CatalogSection.objects.annotate(item_count=Count('items'))
                .order_by('doc', 'sequence', 'subsection'))
        return Response(CatalogSectionSerializer(rows, many=True).data)

    @action(detail=True, methods=['post'])
    def stock(self, request, pk=None):
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


    serializer_class = StockLocationSerializer

    def get_queryset(self):
        queryset = StockLocation.objects.all()
        if self.request.query_params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        if kind := self.request.query_params.get('kind'):
            queryset = queryset.filter(kind=kind)
        return queryset

    def perform_destroy(self, instance):
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

        rows = (LocationStock.objects.filter(location=self.get_object(), quantity__gt=0)
                .select_related('item', 'location').order_by('item__name'))
        return Response(LocationStockSerializer(rows, many=True).data)


class LocationStockViewSet(viewsets.ReadOnlyModelViewSet):


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
        from . import bom as bom_service

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
        source = self.get_object()
        if not source.is_active:
            raise ValidationError(
                {'detail': f"Version {source.version} has already been superseded. "
                           f"Version the active BOM instead."})

        with transaction.atomic():
            siblings = BillOfMaterials.objects.select_for_update().filter(
                template=source.template, design=source.design)
            if source.template_id is None and source.design_id is None:
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

        from . import order_materials
        shortfalls = order_materials.check_availability(self.get_object())
        return Response({'is_available': not shortfalls, 'shortfalls': shortfalls})

    @action(detail=True, methods=['POST'], url_path='reserve')
    def reserve(self, request, pk=None):

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

        from . import order_materials
        try:
            released = order_materials.release_unused(self.get_object(), user=request.user)
        except (order_materials.MaterialPlanError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'released': released})

    @action(detail=True, methods=['POST'], url_path='deduct-packaging')
    def deduct_packaging(self, request, pk=None):

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
        try:
            location = StockLocation.objects.filter(pk=value).first()
        except (ValueError, TypeError, DjangoValidationError):
            raise ValidationError({key: f'{value!r} is not a valid location id.'})
        if location is None:
            raise ValidationError({key: f'No stock location with id {value}.'})
        return location


class CustomerMaterialViewSet(viewsets.ModelViewSet):

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

        from crm_api.models import Order
        from . import order_materials

        order = _get_or_400(Order, request.data.get('order'), 'order')

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

    permission_classes = [OwnerOnly]

    @staticmethod
    def _window(request):
        import datetime

        from django.utils import timezone
        from django.utils.dateparse import parse_date, parse_datetime

        window = {}
        for key in ('since', 'until'):
            raw = request.query_params.get(key)
            if not raw:
                continue
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

        from . import reports
        return Response(reports.stock_position())

    @action(detail=False, methods=['GET'], url_path='low-stock')
    def low_stock(self, request):
        from . import reports
        return Response(reports.low_stock(limit=self._limit(request)))

    @action(detail=False, methods=['GET'], url_path='consumption')
    def consumption(self, request):

        from . import reports
        try:
            return Response(reports.consumption(
                request.query_params.get('scope') or None,
                limit=self._limit(request), **self._window(request)))
        except ValueError as exc:
            raise ValidationError({'scope': str(exc)})

    @action(detail=False, methods=['GET'], url_path='loss-rates')
    def loss_rates(self, request):

        from . import reports
        return Response(reports.loss_rates(**self._window(request)))

    @action(detail=False, methods=['GET'], url_path='cost-per-order')
    def cost_per_order(self, request):
        from . import reports
        return Response(reports.cost_per_order(limit=self._limit(request)))

    @action(detail=False, methods=['GET'], url_path='order-usage')
    def order_usage(self, request):

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

        from . import reports
        return Response(reports.dashboard(**self._window(request)))
