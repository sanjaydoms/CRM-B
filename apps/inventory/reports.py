
from decimal import Decimal

from django.db.models import (
    Case, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When,
)
from django.db.models.functions import Coalesce, TruncDate

from .models import (
    Category, CustomerMaterial, InventoryItem, OrderMaterialLine, OrderMaterialPlan,
    PurchaseOrder, StockMovement,
)

MONEY = DecimalField(max_digits=16, decimal_places=2)
QUANTITY = DecimalField(max_digits=16, decimal_places=3)

ZERO_MONEY = Value(Decimal('0'), output_field=MONEY)
ZERO_QUANTITY = Value(Decimal('0'), output_field=QUANTITY)

CONSUMPTION_SCOPES = {
    'fabric': [Category.FABRIC, Category.LINING],
    'embroidery': [Category.MAGGAM, Category.EMBELLISHMENT],
    'packaging': [Category.PACKAGING],
}


def _value_expression():
    return ExpressionWrapper(F('current_stock') * F('purchase_price'), output_field=MONEY)


def _percentage(part, whole):
    if not whole:
        return None
    return (Decimal(part) / Decimal(whole) * Decimal('100')).quantize(Decimal('0.01'))


def _movement_totals(queryset, types):
    rows = (queryset.filter(movement_type__in=types)
            .values('movement_type')
            .annotate(total=Coalesce(Sum('quantity'), ZERO_QUANTITY)))
    totals = {t: Decimal('0') for t in types}
    for row in rows:
        totals[row['movement_type']] = row['total']
    return totals



def stock_position(queryset=None):
    items = queryset if queryset is not None else InventoryItem.objects.all()

    totals = items.aggregate(
        item_count=Count('id'),
        current=Coalesce(Sum('current_stock'), ZERO_QUANTITY),
        reserved=Coalesce(Sum('reserved_stock'), ZERO_QUANTITY),
        value=Coalesce(Sum(_value_expression()), ZERO_MONEY),
    )
    available = totals['current'] - totals['reserved']

    at_reorder = items.filter(
        current_stock__lte=F('reserved_stock') + F('reorder_level'))
    below_minimum = items.filter(
        current_stock__lte=F('reserved_stock') + F('minimum_stock'))
    out_of_stock = items.filter(current_stock__lte=F('reserved_stock'))

    return {
        'item_count': totals['item_count'],
        'current_stock': totals['current'],
        'reserved_stock': totals['reserved'],
        'available_stock': available,
        'inventory_value': totals['value'],
        'at_or_below_reorder_level': at_reorder.count(),
        'below_minimum_stock': below_minimum.count(),
        'out_of_stock': out_of_stock.count(),
    }


def low_stock(queryset=None, limit=100):
    items = queryset if queryset is not None else InventoryItem.objects.all()
    rows = (items
            .filter(current_stock__lte=F('reserved_stock') + F('reorder_level'))
            .annotate(available=ExpressionWrapper(
                F('current_stock') - F('reserved_stock'), output_field=QUANTITY))
            .order_by('available')[:limit])
    return [
        {
            'item_id': str(item.id), 'item_code': item.item_code, 'name': item.name,
            'category': item.category, 'unit': item.unit,
            'current_stock': item.current_stock, 'reserved_stock': item.reserved_stock,
            'available_stock': item.available, 'reorder_level': item.reorder_level,
            'minimum_stock': item.minimum_stock,
            'short_by': max(Decimal('0'), item.reorder_level - item.available),
            'supplier': item.supplier.name if item.supplier_id else None,
        }
        for item in rows.select_related('supplier')
    ]



def consumption(scope=None, *, since=None, until=None, limit=100):
    movements = StockMovement.objects.filter(
        movement_type=StockMovement.Type.CONSUMPTION)
    if since:
        movements = movements.filter(created_at__gte=since)
    if until:
        movements = movements.filter(created_at__lte=until)
    if scope:
        categories = CONSUMPTION_SCOPES.get(scope)
        if categories is None:
            raise ValueError(
                f"Unknown consumption scope {scope!r}; "
                f"expected one of {', '.join(sorted(CONSUMPTION_SCOPES))}.")
        movements = movements.filter(item__category__in=categories)

    rows = (movements
            .values('item_id', 'item__item_code', 'item__name', 'item__unit',
                    'item__category', 'item__purchase_price')
            .annotate(
                quantity=Coalesce(Sum('quantity'), ZERO_QUANTITY),
                movements=Count('id'))
            .order_by('-quantity')[:limit])

    out = []
    for row in rows:
        quantity = row['quantity']
        price = row['item__purchase_price'] or Decimal('0')
        out.append({
            'item_id': str(row['item_id']),
            'item_code': row['item__item_code'],
            'name': row['item__name'],
            'category': row['item__category'],
            'unit': row['item__unit'],
            'quantity': quantity,
            'movements': row['movements'],
            'value': (quantity * price).quantize(Decimal('0.01')),
        })
    return {'scope': scope or 'all', 'rows': out,
            'total_quantity': sum((r['quantity'] for r in out), Decimal('0')),
            'total_value': sum((r['value'] for r in out), Decimal('0'))}



def loss_rates(*, since=None, until=None):
    movements = StockMovement.objects.all()
    if since:
        movements = movements.filter(created_at__gte=since)
    if until:
        movements = movements.filter(created_at__lte=until)

    T = StockMovement.Type
    totals = _movement_totals(movements, [
        T.CONSUMPTION, T.WASTE, T.DAMAGE, T.SCRAP, T.GOODS_RECEIPT,
        T.STOCK_IN, T.PURCHASE,
    ])

    to_production = totals[T.CONSUMPTION] + totals[T.WASTE]
    taken_in = totals[T.GOODS_RECEIPT] + totals[T.STOCK_IN] + totals[T.PURCHASE]

    return {
        'consumed': totals[T.CONSUMPTION],
        'wasted': totals[T.WASTE],
        'damaged': totals[T.DAMAGE],
        'scrapped': totals[T.SCRAP],
        'received': taken_in,
        'waste_percent': _percentage(totals[T.WASTE], to_production),
        'damage_percent': _percentage(totals[T.DAMAGE], taken_in),
        'waste_basis': 'consumption + waste',
        'damage_basis': 'goods receipt + stock in + purchase',
    }



def cost_per_order(*, order=None, limit=100):
    lines = (OrderMaterialLine.objects
             .filter(is_customer_supplied=False, item__isnull=False)
             .select_related('plan__order', 'item'))
    if order is not None:
        lines = lines.filter(plan__order=order)

    consumed_value = ExpressionWrapper(
        F('consumed_quantity') * F('item__purchase_price'), output_field=MONEY)
    wasted_value = ExpressionWrapper(
        F('wasted_quantity') * F('item__purchase_price'), output_field=MONEY)

    rows = (lines
            .values('plan__order_id', 'plan__order__order_id', 'plan_id', 'plan__status')
            .annotate(
                material_cost=Coalesce(Sum(consumed_value), ZERO_MONEY),
                waste_cost=Coalesce(Sum(wasted_value), ZERO_MONEY),
                line_count=Count('id'))
            .order_by('-material_cost')[:limit])

    return [
        {
            'order_id': row['plan__order_id'],
            'order_code': row['plan__order__order_id'],
            'plan_id': str(row['plan_id']),
            'plan_status': row['plan__status'],
            'line_count': row['line_count'],
            'material_cost': row['material_cost'],
            'waste_cost': row['waste_cost'],
            'total_cost': row['material_cost'] + row['waste_cost'],
        }
        for row in rows
    ]


def order_material_usage(order):
    plans = (OrderMaterialPlan.objects.filter(order=order)
             .select_related('bom').prefetch_related('lines__item'))

    boutique = []
    for plan in plans:
        for line in plan.lines.all():
            if line.is_customer_supplied:
                continue
            price = line.item.purchase_price if line.item_id else Decimal('0')
            boutique.append({
                'plan_id': str(plan.id), 'plan_status': plan.status,
                'material': line.material_name, 'role': line.role, 'unit': line.unit,
                'required': line.required_quantity,
                'reserved': line.reserved_quantity,
                'consumed': line.consumed_quantity,
                'wasted': line.wasted_quantity,
                'returned': line.returned_quantity,
                'cost': ((line.consumed_quantity + line.wasted_quantity)
                         * price).quantize(Decimal('0.01')),
            })

    customer = [
        {
            'material': material.name, 'kind': material.kind, 'unit': material.unit,
            'received': material.received_quantity, 'used': material.used_quantity,
            'returned': material.returned_quantity, 'damaged': material.damaged_quantity,
            'remaining': material.remaining_quantity,
        }
        for material in CustomerMaterial.objects.filter(order=order)
    ]

    return {
        'order': order.order_id,
        'boutique_materials': boutique,
        'customer_materials': customer,
        'material_cost': sum((row['cost'] for row in boutique), Decimal('0')),
    }



def supplier_performance(*, since=None, limit=50):
    orders = PurchaseOrder.objects.all()
    if since:
        orders = orders.filter(order_date__gte=since)

    judged = Q(expected_date__isnull=False, received_date__isnull=False)
    rows = (orders
            .values('supplier_id', 'supplier__name')
            .annotate(
                order_count=Count('id'),
                received_count=Count('id', filter=Q(received_date__isnull=False)),
                judged_count=Count('id', filter=judged),
                on_time_count=Count('id', filter=judged & Q(
                    received_date__lte=F('expected_date'))),
                cancelled_count=Count('id', filter=Q(status='CANCELLED')),
            )
            .order_by('-order_count')[:limit])

    out = []
    for row in rows:
        out.append({
            'supplier_id': str(row['supplier_id']),
            'supplier': row['supplier__name'],
            'order_count': row['order_count'],
            'received_count': row['received_count'],
            'judged_count': row['judged_count'],
            'on_time_count': row['on_time_count'],
            'cancelled_count': row['cancelled_count'],
            'on_time_percent': _percentage(row['on_time_count'], row['judged_count']),
        })
    return out



def movement_history(*, item=None, order=None, movement_type=None, location=None,
                     since=None, until=None, limit=200):
    movements = (StockMovement.objects
                 .select_related('item', 'order', 'from_location', 'to_location'))
    if item is not None:
        movements = movements.filter(item=item)
    if order is not None:
        movements = movements.filter(order=order)
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    if location is not None:
        movements = movements.filter(
            Q(from_location=location) | Q(to_location=location))
    if since:
        movements = movements.filter(created_at__gte=since)
    if until:
        movements = movements.filter(created_at__lte=until)

    return [
        {
            'id': str(movement.id),
            'created_at': movement.created_at,
            'item': movement.item.name,
            'item_code': movement.item.item_code,
            'movement_type': movement.movement_type,
            'quantity': movement.quantity,
            'previous_stock': movement.previous_stock,
            'new_stock': movement.new_stock,
            'from_location': movement.from_location.name if movement.from_location_id else None,
            'to_location': movement.to_location.name if movement.to_location_id else None,
            'order': movement.order.order_id if movement.order_id else None,
            'user': movement.user_name_snapshot,
            'remarks': movement.remarks,
        }
        for movement in movements.order_by('-created_at')[:limit]
    ]


def movement_summary(*, since=None, until=None):
    movements = StockMovement.objects.all()
    if since:
        movements = movements.filter(created_at__gte=since)
    if until:
        movements = movements.filter(created_at__lte=until)
    rows = (movements.values('movement_type')
            .annotate(total=Coalesce(Sum('quantity'), ZERO_QUANTITY), count=Count('id'))
            .order_by('-count'))
    return [
        {'movement_type': row['movement_type'], 'quantity': row['total'],
         'count': row['count']}
        for row in rows
    ]



def dashboard(*, since=None, until=None):
    return {
        'stock': stock_position(),
        'low_stock': low_stock(limit=10),
        'consumption': {
            scope: consumption(scope, since=since, until=until, limit=10)
            for scope in ('fabric', 'embroidery', 'packaging')
        },
        'losses': loss_rates(since=since, until=until),
        'cost_per_order': cost_per_order(limit=10),
        'suppliers': supplier_performance(limit=10),
        'movements': movement_summary(since=since, until=until),
    }
