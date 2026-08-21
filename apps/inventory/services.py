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

from .models import InventoryItem, LocationStock, StockLocation, StockMovement


def _as_quantity(value, field='quantity'):
    """A positive, finite, storable quantity -- or a ValueError callers expect.

    Two values got past the old version, and both are reachable from a JSON
    body:

      * 'NaN' -- Decimal('NaN') is a perfectly valid Decimal, so the parse
        succeeded. The `quantity <= 0` comparison then raised InvalidOperation,
        which is an ArithmeticError rather than a ValueError, so it escaped the
        handler every caller wraps this in and surfaced as an unhandled 500.
      * 'Infinity' -- parses, and `Infinity <= 0` is simply False, so it passed
        validation entirely and went on to a DecimalField write that cannot
        store it.

    The comparison moves inside the try for the first, and is_finite() plus an
    upper bound close the second. The bound matches what the columns can hold
    (max_digits=12, decimal_places=3), so a quantity that would die in the
    driver is refused here with a sentence instead.
    """
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
        """The location a movement lands at when the caller does not name one.

        Every operation predates locations, so none of them passed one. Rather
        than make the argument required and break every existing call site, an
        unlocated movement is treated as happening at the default -- which is
        what the boutique means by "in stock" before it starts tracking units.
        """
        return StockLocation.objects.filter(is_default=True, is_active=True).first()

    @staticmethod
    def _shift_location(item, location, delta, quantity):
        """Move `quantity` into (delta=+1) or out of (delta=-1) one location."""
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
        """Apply a stock change and write its ledger line.

        stock_delta and reserved_delta are signed; a reservation moves only the
        reserved figure, an issue moves both down, a purchase moves stock up.

        clamp_reserved is for issuing: material is often handed to the workroom
        without having been reserved first, so an issue consumes whatever
        reservation exists and takes the rest from free stock, rather than
        failing because there was nothing reserved to release.
        """
        quantity = _as_quantity(quantity)
        if reserved_backed is not None:
            reserved_backed = Decimal(str(reserved_backed))
            if reserved_backed < 0 or reserved_backed > quantity:
                raise ValueError(
                    f'reserved_backed must be between 0 and {quantity}, got {reserved_backed}.')

        # Lock so two concurrent issues cannot both read the same balance.
        locked = InventoryItem.objects.select_for_update().get(pk=item.pk)

        previous_stock = locked.current_stock
        previous_reserved = locked.reserved_stock
        new_stock = previous_stock + (stock_delta * quantity)
        if reserved_backed is not None and reserved_delta < 0:
            # The caller knows how much of this movement was actually covered by
            # ITS OWN reservation. Without that, the clamp below is the only
            # option and it clamps against the item's *global* reserved figure --
            # so consuming more than one order reserved silently ate another
            # order's reservation, leaving that order unable to release what it
            # still thought it held. Anything beyond `reserved_backed` comes out
            # of free stock, which is what over-consumption actually is.
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
            # Nothing is being reserved here -- this is DAMAGE, SCRAP, a
            # supplier return or a stock count, all of which reduce physical
            # stock and carry reserved_delta == 0. Refusing them because the
            # material happened to be spoken for meant a real loss could not be
            # recorded at all, and the refusal talked about a reservation the
            # owner had never attempted. The stock is gone either way; the
            # reservation it was backing cannot outlive it, so release the
            # difference implicitly and let the movement row carry the fact.
            released = new_reserved - new_stock
            new_reserved = new_stock
            notes = f"Reservation reduced by {released} -- stock no longer available."
            remarks = f"{remarks} {notes}".strip() if remarks else notes

        # Keep the per-location breakdown in step with the total, inside the same
        # transaction, so the two can never drift. A movement that adds stock
        # lands somewhere; one that removes it comes from somewhere; a transfer
        # does both and leaves the total alone.
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
            # Which dress this was for. An order holds several, so "left stock
            # for order X" is not on its own an answer anyone can act on.
            garment_job=garment_job,
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
    def issue(item, quantity, **kw):
        """Handed to production. Leaves the shelf, consuming any reservation.

        Issuing more than was reserved is normal -- the surplus simply comes from
        free stock. Only the physical balance can block an issue.
        """
        return InventoryService.record_movement(
            item, StockMovement.Type.ISSUE, quantity,
            stock_delta=-1, reserved_delta=-1, clamp_reserved=True, **kw
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
    def goods_receipt(item, quantity, **kw):
        """Material arriving against a purchase order."""
        return InventoryService.record_movement(
            item, StockMovement.Type.GOODS_RECEIPT, quantity,
            stock_delta=1, reserved_delta=0, **kw
        )

    @staticmethod
    def consume(item, quantity, **kw):
        """Material actually used up in production.

        Distinct from issue(): issuing moves material to the workroom, consuming
        records that it went into the garment. A boutique that only ever issues
        cannot tell how much of what it handed over came back.
        """
        return InventoryService.record_movement(
            item, StockMovement.Type.CONSUMPTION, quantity,
            stock_delta=-1, reserved_delta=-1, clamp_reserved=True, **kw
        )


    @staticmethod
    def waste(item, quantity, **kw):
        """Material lost in the making -- offcuts, spoilage, failed embroidery.

        Releases any reservation it consumes, exactly as issuing and consuming
        do. Wasted material has left the shelf, so it cannot still be spoken for
        by the order that spoiled it -- leaving the reservation behind would
        strand that quantity, invisible to every other order and never released.
        Clamped, because waste is often recorded against stock nobody reserved.
        """
        return InventoryService.record_movement(
            item, StockMovement.Type.WASTE, quantity,
            stock_delta=-1, reserved_delta=-1, clamp_reserved=True, **kw
        )

    @staticmethod
    def customer_return(item, quantity, **kw):
        """A finished garment's material coming back from the customer."""
        return InventoryService.record_movement(
            item, StockMovement.Type.CUSTOMER_RETURN, quantity,
            stock_delta=1, reserved_delta=0, **kw
        )

    @staticmethod
    def supplier_return(item, quantity, **kw):
        """Material sent back to the supplier -- wrong shade, short delivery, faulty."""
        return InventoryService.record_movement(
            item, StockMovement.Type.SUPPLIER_RETURN, quantity,
            stock_delta=-1, reserved_delta=0, **kw
        )

    @staticmethod
    @transaction.atomic
    def transfer(item, quantity, *, from_location, to_location, **kw):
        """Move stock between two locations. The total never changes.

        This is the one operation where stock_delta is zero: nothing enters or
        leaves the boutique, it just stops being in one place and starts being in
        another. Both sides move in a single transaction, so a transfer can never
        leave material counted twice or not at all.
        """
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
        """Where this item's stock currently sits, heaviest first."""
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
        # A count is taken somewhere. Naming the location lets a shortfall come
        # off the shelf that was actually counted, rather than off whichever one
        # record_movement would have defaulted to.
        return InventoryService.record_movement(
            item, StockMovement.Type.ADJUSTMENT, abs(difference),
            stock_delta=1 if difference > 0 else -1, reserved_delta=0,
            user=user, remarks=remarks or f'Stock count adjusted to {counted}.',
            from_location=from_location if difference < 0 else None,
            to_location=from_location if difference > 0 else None,
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
