from django.db.models import F, Sum, DecimalField, ExpressionWrapper
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Category, InventoryItem, PurchaseOrder, StockMovement, Supplier, Unit,
    DEFAULT_UNIT_BY_CATEGORY,
)
from .serializers import (
    InventoryItemSerializer, InventoryItemSummarySerializer, PurchaseOrderSerializer,
    StockMovementSerializer, SupplierSerializer,
)
from .services import InventoryService


class SupplierViewSet(viewsets.ModelViewSet):
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

    @action(detail=True, methods=['POST'], url_path='issue')
    def issue(self, request, pk=None):
        return self._apply(
            request, InventoryService.issue,
            order=self._order(request),
            stage_key=request.data.get('stage_key'),
        )

    @action(detail=True, methods=['POST'], url_path='return')
    def return_material(self, request, pk=None):
        return self._apply(request, InventoryService.return_stock, order=self._order(request))

    @action(detail=True, methods=['POST'], url_path='damage')
    def damage(self, request, pk=None):
        return self._apply(request, InventoryService.damage)

    @action(detail=True, methods=['POST'], url_path='scrap')
    def scrap(self, request, pk=None):
        return self._apply(request, InventoryService.scrap)

    @action(detail=True, methods=['POST'], url_path='adjust')
    def adjust(self, request, pk=None):
        item = self.get_object()
        try:
            InventoryService.adjust(
                item, request.data.get('counted_quantity'),
                user=request.user, remarks=request.data.get('remarks', ''),
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
