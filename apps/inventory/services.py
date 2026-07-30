"""The only writer of stock quantities.

Every operation locks the item row, applies the change, writes the matching
StockMovement and saves both in one transaction, so the ledger and the balance
can never disagree. Callers get a ValueError with a readable message when a move
is not possible -- there is not enough stock, or more is being released than was
ever reserved.
"""

from decimal import Decimal

from django.db import transaction

from crm_api.models import Notification

from .models import InventoryItem, StockMovement


def _as_quantity(value, field='quantity'):
    try:
        quantity = Decimal(str(value))
    except Exception:
        raise ValueError(f'{field} must be a number.')
    if quantity <= 0:
        raise ValueError(f'{field} must be greater than zero.')
    return quantity


class InventoryService:

    @staticmethod
    @transaction.atomic
    def record_movement(item, movement_type, quantity, *, stock_delta, reserved_delta,
                        user=None, order=None, stage_key=None, performed_by=None, remarks=''):
        """Apply a stock change and write its ledger line.

        stock_delta and reserved_delta are signed; a reservation moves only the
        reserved figure, an issue moves both down, a purchase moves stock up.
        """
        quantity = _as_quantity(quantity)

        # Lock so two concurrent issues cannot both read the same balance.
        locked = InventoryItem.objects.select_for_update().get(pk=item.pk)

        previous_stock = locked.current_stock
        previous_reserved = locked.reserved_stock
        new_stock = previous_stock + (stock_delta * quantity)
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
            raise ValueError(
                f"Cannot reserve {quantity} {locked.get_unit_display()} of '{locked.name}' -- "
                f"only {previous_stock - previous_reserved} available."
            )

        locked.current_stock = new_stock
        locked.reserved_stock = new_reserved
        locked._allow_stock_write = True
        locked.save(update_fields=['current_stock', 'reserved_stock', 'updated_at'])

        movement = StockMovement.objects.create(
            item=locked,
            movement_type=movement_type,
            quantity=quantity,
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
            stage_key=stage_key,
            performed_by=performed_by,
            remarks=remarks,
        )

        InventoryService._raise_alerts(locked)
        return movement

    # --- the operations -------------------------------------------------

    @staticmethod
    def stock_in(item, quantity, **kw):
        """Goods received into the boutique."""
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
        """Spoken for by an order, but still physically on the shelf."""
        return InventoryService.record_movement(
            item, StockMovement.Type.RESERVATION, quantity, stock_delta=0, reserved_delta=1, **kw
        )

    @staticmethod
    def release(item, quantity, **kw):
        """Reservation cancelled; stock becomes available again."""
        return InventoryService.record_movement(
            item, StockMovement.Type.RELEASE, quantity, stock_delta=0, reserved_delta=-1, **kw
        )

    @staticmethod
    def issue(item, quantity, *, from_reservation=True, **kw):
        """Handed to production. Leaves the shelf, and clears its reservation."""
        return InventoryService.record_movement(
            item, StockMovement.Type.ISSUE, quantity,
            stock_delta=-1, reserved_delta=-1 if from_reservation else 0, **kw
        )

    @staticmethod
    def return_stock(item, quantity, **kw):
        """Unused material coming back from the workroom."""
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
    @transaction.atomic
    def adjust(item, new_quantity, *, user=None, remarks=''):
        """Correct the book figure to a counted one, in one auditable step."""
        try:
            counted = Decimal(str(new_quantity))
        except Exception:
            raise ValueError('Counted quantity must be a number.')
        if counted < 0:
            raise ValueError('Counted quantity cannot be negative.')

        # Read the balance from the row, not from the caller's copy -- an instance
        # held across an earlier movement is stale, and the difference would be
        # computed against a figure that is no longer true.
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
        )

    # --- alerts ---------------------------------------------------------

    @staticmethod
    def _raise_alerts(item):
        """Notify the owner when an item crosses out of stock or below reorder.

        Only fires on the crossing, not on every movement, so a busy day does not
        bury the inbox in duplicates of the same warning.
        """
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

    # --- reporting ------------------------------------------------------

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
