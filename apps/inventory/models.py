"""Boutique inventory: the item master, the stock ledger and procurement.

Two rules shape this module:

1. Stock quantities are never written directly. Every change goes through
   InventoryService, which records a StockMovement alongside it. The guard in
   InventoryItem.save() enforces this rather than leaving it to convention.
2. Boutique-owned stock and customer-supplied materials are separate ledgers.
   Only boutique stock lives here; customer materials arrive with the dress-level
   work, once an order can hold more than one garment.
"""

import uuid

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from crm_api.models import Order, Tailor


class Unit(models.TextChoices):
    METER = 'METER', 'Meter'
    PIECE = 'PIECE', 'Piece'
    PAIR = 'PAIR', 'Pair'
    ROLL = 'ROLL', 'Roll'
    PACKET = 'PACKET', 'Packet'
    BOX = 'BOX', 'Box'
    SET = 'SET', 'Set'
    KILOGRAM = 'KILOGRAM', 'Kilogram'
    GRAM = 'GRAM', 'Gram'
    STRING = 'STRING', 'String'
    UNIT = 'UNIT', 'Unit'


class Category(models.TextChoices):
    FABRIC = 'FABRIC', 'Fabric'
    BORDER = 'BORDER', 'Border & Trim'
    LINING = 'LINING', 'Lining'
    EMBELLISHMENT = 'EMBELLISHMENT', 'Embellishment'
    STITCHING = 'STITCHING', 'Stitching Material'
    PACKAGING = 'PACKAGING', 'Packaging'
    MAGGAM = 'MAGGAM', 'Maggam / Embroidery'
    OTHER = 'OTHER', 'Other'


# Each category proposes a unit; an item may still override it (thread is sold by
# the roll, elastic by the metre, and both are stitching materials).
DEFAULT_UNIT_BY_CATEGORY = {
    Category.FABRIC: Unit.METER,
    Category.BORDER: Unit.METER,
    Category.LINING: Unit.METER,
    Category.EMBELLISHMENT: Unit.PIECE,
    Category.STITCHING: Unit.PIECE,
    Category.PACKAGING: Unit.PIECE,
    Category.MAGGAM: Unit.PIECE,
    Category.OTHER: Unit.UNIT,
}


class DirectStockWriteError(RuntimeError):
    """Raised when stock is changed outside InventoryService."""


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, db_index=True)
    contact_person = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=30, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        DISCONTINUED = 'DISCONTINUED', 'Discontinued'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item_code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200, db_index=True)
    category = models.CharField(max_length=30, choices=Category.choices, db_index=True)
    sub_category = models.CharField(max_length=100, blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)

    # Fabric and trim carry a few extra descriptors; null elsewhere.
    material_type = models.CharField(max_length=100, blank=True, null=True)
    design_number = models.CharField(max_length=100, blank=True, null=True)
    width = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)

    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    hsn_code = models.CharField(max_length=20, blank=True, null=True)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='items'
    )

    # Written only by InventoryService. current_stock is what physically exists;
    # reserved_stock is spoken for but not yet issued. available = current - reserved.
    current_stock = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)]
    )
    reserved_stock = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)]
    )

    minimum_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    maximum_stock = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    rack_location = models.CharField(max_length=100, blank=True, null=True)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    purchase_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _STOCK_FIELDS = ('current_stock', 'reserved_stock')

    class Meta:
        ordering = ['category', 'name']
        indexes = [models.Index(fields=['category', 'status'])]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._allow_stock_write = False
        self._snapshot_stock()

    def _snapshot_stock(self):
        self._stock_snapshot = {f: getattr(self, f) for f in self._STOCK_FIELDS}

    @property
    def available_stock(self):
        return self.current_stock - self.reserved_stock

    @property
    def needs_reorder(self):
        return self.available_stock <= self.reorder_level

    @property
    def is_out_of_stock(self):
        return self.available_stock <= 0

    def save(self, *args, **kwargs):
        """Refuse a stock change that did not come through InventoryService.

        Catching this at the model means a stray `item.current_stock -= 2; save()`
        anywhere in the codebase fails loudly instead of silently leaving the
        ledger and the balance disagreeing.
        """
        if self.pk and not self._allow_stock_write:
            changed = [
                f for f in self._STOCK_FIELDS
                if self._stock_snapshot.get(f) != getattr(self, f)
            ]
            if changed:
                raise DirectStockWriteError(
                    f"{', '.join(changed)} on '{self.name}' must be changed through "
                    f"InventoryService so a StockMovement is recorded."
                )
        super().save(*args, **kwargs)
        self._allow_stock_write = False
        self._snapshot_stock()

    def __str__(self):
        return f"{self.item_code} · {self.name} ({self.available_stock} {self.get_unit_display()})"


class StockMovement(models.Model):
    """One immutable line of the stock ledger.

    Every quantity change writes one of these, with the balance before and after,
    so stock is always reconstructible from history.
    """

    class Type(models.TextChoices):
        PURCHASE = 'PURCHASE', 'Purchase'
        STOCK_IN = 'STOCK_IN', 'Stock In'
        RESERVATION = 'RESERVATION', 'Reservation'
        RELEASE = 'RELEASE', 'Reservation Released'
        ISSUE = 'ISSUE', 'Issued to Production'
        CONSUMPTION = 'CONSUMPTION', 'Consumed'
        RETURN = 'RETURN', 'Returned'
        TRANSFER = 'TRANSFER', 'Transfer'
        DAMAGE = 'DAMAGE', 'Damaged'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
        SCRAP = 'SCRAP', 'Scrapped'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    previous_stock = models.DecimalField(max_digits=12, decimal_places=3)
    new_stock = models.DecimalField(max_digits=12, decimal_places=3)
    previous_reserved = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    new_reserved = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    user_name_snapshot = models.CharField(max_length=150, blank=True, null=True)

    # Where the movement came from. Once an order can hold several garments these
    # point at the individual production job instead.
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements'
    )
    stage_key = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    performed_by = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements'
    )

    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['item', '-created_at'])]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} · {self.item.name}"


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ORDERED = 'ORDERED', 'Ordered'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially Received'
        RECEIVED = 'RECEIVED', 'Received'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'UNPAID', 'Unpaid'
        PARTIAL = 'PARTIAL', 'Partially Paid'
        PAID = 'PAID', 'Paid'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    po_number = models.CharField(max_length=50, unique=True, db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.DRAFT, db_index=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    order_date = models.DateField(auto_now_add=True)
    expected_date = models.DateField(blank=True, null=True)
    received_date = models.DateField(blank=True, null=True)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def subtotal(self):
        return sum((line.line_total for line in self.lines.all()), 0)

    @property
    def total(self):
        return self.subtotal + self.tax_amount

    def __str__(self):
        return f"{self.po_number} · {self.supplier.name} ({self.get_status_display()})"


class PurchaseOrderLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='purchase_lines')
    quantity_ordered = models.DecimalField(max_digits=12, decimal_places=3)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    batch_number = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['purchase_order', 'item__name']

    @property
    def quantity_outstanding(self):
        return self.quantity_ordered - self.quantity_received

    @property
    def line_total(self):
        return self.quantity_ordered * self.unit_cost

    def __str__(self):
        return f"{self.item.name} × {self.quantity_ordered}"
