
from decimal import Decimal

from django.db import transaction

from crm_api.models import Notification

from .models import InventoryItem, LocationStock, StockLocation, StockMovement


def _as_quantity(value, field='quantity'):
    try:
        quantity = Decimal(str(value))
        if not quantity.is_finite():
            raise ValueError(f'{field} must be a number.')
        if quantity <= 0:
            raise ValueError(f'{field} must be greater than zero.')
        if quantity >= 10 ** 9:
            raise ValueError(f'{field} is too large.')
    except ValueError:
        raise
    except Exception:
        raise ValueError(f'{field} must be a number.')
    return quantity


class InventoryService:

    @staticmethod
    def default_location():
        return StockLocation.objects.filter(is_default=True, is_active=True).first()

    @staticmethod
    def _shift_location(item, location, delta, quantity):
        if location is None or delta == 0:
            return
        row, _ = LocationStock.objects.select_for_update().get_or_create(
            item=item, location=location, defaults={'quantity': Decimal('0')})
        new_quantity = row.quantity + (delta * quantity)
        if new_quantity < 0:
            raise ValueError(
                f"Cannot take {quantity} {item.get_unit_display()} of '{item.name}' from "
                f"{location.name} -- only {row.quantity} is there."
            )
        row.quantity = new_quantity
        row.save(update_fields=['quantity', 'updated_at'])

    @staticmethod
    @transaction.atomic
    def record_movement(item, movement_type, quantity, *, stock_delta, reserved_delta,
                        clamp_reserved=False, reserved_backed=None, user=None, order=None,
                        garment_job=None, stage_key=None, performed_by=None, remarks='',
                        from_location=None, to_location=None):
        quantity = _as_quantity(quantity)
        if reserved_backed is not None:
            reserved_backed = Decimal(str(reserved_backed))
            if reserved_backed < 0 or reserved_backed > quantity:
                raise ValueError(
                    f'reserved_backed must be between 0 and {quantity}, got {reserved_backed}.')

        locked = InventoryItem.objects.select_for_update().get(pk=item.pk)

        previous_stock = locked.current_stock
        previous_reserved = locked.reserved_stock
        new_stock = previous_stock + (stock_delta * quantity)
        if reserved_backed is not None and reserved_delta < 0:
            new_reserved = max(Decimal('0'), previous_reserved - reserved_backed)
        elif clamp_reserved and reserved_delta < 0:
            new_reserved = max(Decimal('0'), previous_reserved - quantity)
        else:
            new_reserved = previous_reserved + (reserved_delta * quantity)

        if new_stock < 0:
            raise ValueError(
                f"Cannot {movement_type.lower()} {quantity} {locked.get_unit_display()} of "
                f"'{locked.name}' -- only {previous_stock} in stock."
            )
        if new_reserved < 0:
            raise ValueError(
                f"Cannot release {quantity} of '{locked.name}' -- only "
                f"{previous_reserved} is reserved."
            )
        if new_reserved > new_stock:
            if reserved_delta > 0:
                raise ValueError(
                    f"Cannot reserve {quantity} {locked.get_unit_display()} of '{locked.name}' -- "
                    f"only {previous_stock - previous_reserved} available."
                )
            released = new_reserved - new_stock
            new_reserved = new_stock
            notes = f"Reservation reduced by {released} -- stock no longer available."
            remarks = f"{remarks} {notes}".strip() if remarks else notes

        if stock_delta > 0 and to_location is None:
            to_location = InventoryService.default_location()
        if stock_delta < 0 and from_location is None:
            from_location = InventoryService.default_location()
        InventoryService._shift_location(locked, from_location, -1, quantity)
        InventoryService._shift_location(locked, to_location, +1, quantity)

        locked.current_stock = new_stock
        locked.reserved_stock = new_reserved
        locked._allow_stock_write = True
        locked.save(update_fields=['current_stock', 'reserved_stock', 'updated_at'])

        movement = StockMovement.objects.create(
            item=locked,
            movement_type=movement_type,
            quantity=quantity,
            from_location=from_location,
            to_location=to_location,
            previous_stock=previous_stock,
            new_stock=new_stock,
            previous_reserved=previous_reserved,
            new_reserved=new_reserved,
            user=user if (user and user.is_authenticated) else None,
            user_name_snapshot=(
                (user.get_full_name() or user.username)
                if (user and user.is_authenticated) else 'System'
            ),
            order=order,
            garment_job=garment_job,
            stage_key=stage_key,
            performed_by=performed_by,
            remarks=remarks,
        )

        InventoryService._raise_alerts(locked)
        return movement


    @staticmethod
    def stock_in(item, quantity, **kw):
        kw.setdefault('remarks', '')
        return InventoryService.record_movement(
            item, StockMovement.Type.STOCK_IN, quantity, stock_delta=1, reserved_delta=0, **kw
        )

    @staticmethod
    def purchase(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.PURCHASE, quantity, stock_delta=1, reserved_delta=0, **kw
        )

    @staticmethod
    def reserve(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.RESERVATION, quantity, stock_delta=0, reserved_delta=1, **kw
        )

    @staticmethod
    def release(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.RELEASE, quantity, stock_delta=0, reserved_delta=-1, **kw
        )

    @staticmethod
    def issue(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.ISSUE, quantity,
            stock_delta=-1, reserved_delta=-1, clamp_reserved=True, **kw
        )

    @staticmethod
    def return_stock(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.RETURN, quantity, stock_delta=1, reserved_delta=0, **kw
        )

    @staticmethod
    def damage(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.DAMAGE, quantity, stock_delta=-1, reserved_delta=0, **kw
        )

    @staticmethod
    def scrap(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.SCRAP, quantity, stock_delta=-1, reserved_delta=0, **kw
        )

    @staticmethod
    def goods_receipt(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.GOODS_RECEIPT, quantity,
            stock_delta=1, reserved_delta=0, **kw
        )

    @staticmethod
    def consume(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.CONSUMPTION, quantity,
            stock_delta=-1, reserved_delta=-1, clamp_reserved=True, **kw
        )


    @staticmethod
    def waste(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.WASTE, quantity,
            stock_delta=-1, reserved_delta=-1, clamp_reserved=True, **kw
        )

    @staticmethod
    def customer_return(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.CUSTOMER_RETURN, quantity,
            stock_delta=1, reserved_delta=0, **kw
        )

    @staticmethod
    def supplier_return(item, quantity, **kw):
        return InventoryService.record_movement(
            item, StockMovement.Type.SUPPLIER_RETURN, quantity,
            stock_delta=-1, reserved_delta=0, **kw
        )

    @staticmethod
    @transaction.atomic
    def transfer(item, quantity, *, from_location, to_location, **kw):
        if from_location is None or to_location is None:
            raise ValueError('A transfer needs both a source and a destination location.')
        if from_location.pk == to_location.pk:
            raise ValueError(f"'{from_location.name}' is both the source and the destination.")
        return InventoryService.record_movement(
            item, StockMovement.Type.TRANSFER, quantity,
            stock_delta=0, reserved_delta=0,
            from_location=from_location, to_location=to_location, **kw
        )

    @staticmethod
    def location_breakdown(item):
        rows = (LocationStock.objects.filter(item=item, quantity__gt=0)
                .select_related('location').order_by('-quantity'))
        return [
            {
                'location_id': str(row.location_id),
                'location': row.location.name,
                'kind': row.location.kind,
                'quantity': row.quantity,
            }
            for row in rows
        ]

    @staticmethod
    @transaction.atomic
    def adjust(item, new_quantity, *, user=None, remarks='', from_location=None):
        try:
            counted = Decimal(str(new_quantity))
        except Exception:
            raise ValueError('Counted quantity must be a number.')
        if counted < 0:
            raise ValueError('Counted quantity cannot be negative.')

        on_hand = (
            InventoryItem.objects.select_for_update()
            .values_list('current_stock', flat=True)
            .get(pk=item.pk)
        )
        difference = counted - on_hand
        if difference == 0:
            return None
        return InventoryService.record_movement(
            item, StockMovement.Type.ADJUSTMENT, abs(difference),
            stock_delta=1 if difference > 0 else -1, reserved_delta=0,
            user=user, remarks=remarks or f'Stock count adjusted to {counted}.',
            from_location=from_location if difference < 0 else None,
            to_location=from_location if difference > 0 else None,
        )


    @staticmethod
    def _raise_alerts(item):
        if item.is_out_of_stock:
            title = f"Out of stock: {item.name}"
            message = f"{item.name} ({item.item_code}) has no available stock left."
        elif item.needs_reorder:
            title = f"Reorder level reached: {item.name}"
            message = (
                f"{item.name} ({item.item_code}) is down to {item.available_stock} "
                f"{item.get_unit_display()}, at or below its reorder level of "
                f"{item.reorder_level}."
            )
        else:
            return None

        if Notification.objects.filter(title=title, is_read=False).exists():
            return None
        return Notification.objects.create(title=title, message=message, recipient_role='Owner')


    @staticmethod
    def stock_summary(queryset=None):
        items = queryset if queryset is not None else InventoryItem.objects.all()
        total_value = Decimal('0')
        reorder, out_of_stock = [], []
        for item in items:
            total_value += item.current_stock * item.purchase_price
            if item.is_out_of_stock:
                out_of_stock.append(item)
            elif item.needs_reorder:
                reorder.append(item)
        return {
            'item_count': len(items) if isinstance(items, list) else items.count(),
            'inventory_value': total_value,
            'needs_reorder': reorder,
            'out_of_stock': out_of_stock,
        }
