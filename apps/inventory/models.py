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
from decimal import Decimal

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


class ItemType(models.TextChoices):
    """What a catalogue row actually is.

    The source documents are an inventory of a whole apparel business, not only
    of stockable materials: they list machines, fixtures, software and the
    garment categories the boutique sells. Everything is catalogued because the
    specification forbids omitting anything, and typed here so that only the
    rows that can sensibly hold stock reach stock and BOM logic.
    """

    MATERIAL = 'MATERIAL', 'Material'
    CONSUMABLE = 'CONSUMABLE', 'Consumable'
    TOOL = 'TOOL', 'Tool'
    MACHINE = 'MACHINE', 'Machine'
    ASSET = 'ASSET', 'Asset'
    DOCUMENT = 'DOCUMENT', 'Document'
    SYSTEM = 'SYSTEM', 'System / Software'
    PRODUCT_CATEGORY = 'PRODUCT_CATEGORY', 'Product Category'


#: Rows that may carry stock. A garment category and a payment gateway cannot be
#: counted, reserved or consumed; a machine or a pair of scissors can be owned in
#: a quantity, so they stay stockable.
STOCKABLE_ITEM_TYPES = frozenset({
    ItemType.MATERIAL, ItemType.CONSUMABLE, ItemType.TOOL,
    ItemType.MACHINE, ItemType.ASSET, ItemType.DOCUMENT,
})


class CatalogSection(models.Model):
    """One section of the source catalogue, e.g. "Beads" or "Sewing Machines".

    Sections are kept exactly as the documents order and name them -- flattening
    them into the eight legacy `Category` values would merge materials the
    specification requires to stay distinct. `Category` is retained alongside
    this for the rows and screens that already use it.
    """

    class Doc(models.TextChoices):
        MAGGAM = 'MAGGAM', 'Maggam / Aari / Zardosi materials'
        APPAREL = 'APPAREL', 'Apparel ecosystem checklist'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc = models.CharField(max_length=20, choices=Doc.choices, db_index=True)
    sequence = models.PositiveIntegerField()
    name = models.CharField(max_length=150)
    subsection = models.CharField(max_length=150, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['doc', 'sequence', 'subsection']
        constraints = [
            models.UniqueConstraint(
                fields=['doc', 'name', 'subsection'],
                name='uniq_catalog_section',
            ),
        ]

    @property
    def full_name(self):
        return f"{self.name} · {self.subsection}" if self.subsection else self.name

    def __str__(self):
        return f"{self.get_doc_display()} — {self.full_name}"


class CatalogItem(models.Model):
    """A material the boutique *could* stock, as published in the source docs.

    This is a reference list, not stock. A boutique that actually holds an item
    creates an InventoryItem from it; the ones it never touches stay here rather
    than filling every tenant's stock screen with hundreds of zero rows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        CatalogSection, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=200, db_index=True)
    item_type = models.CharField(
        max_length=20, choices=ItemType.choices, default=ItemType.MATERIAL, db_index=True)
    default_unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)
    #: The nearest of the eight legacy categories, so a catalogue row can be
    #: turned into an InventoryItem without the operator picking one by hand.
    legacy_category = models.CharField(max_length=30, choices=Category.choices, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['section', 'name']
        indexes = [models.Index(fields=['item_type', 'is_active'])]
        constraints = [
            models.UniqueConstraint(fields=['section', 'name'], name='uniq_catalog_item'),
        ]

    @property
    def is_stockable(self):
        return self.item_type in STOCKABLE_ITEM_TYPES

    def __str__(self):
        return f"{self.name} ({self.section.full_name})"


#: Conversions that are true everywhere, as (from, to): factor.
#: Only the unambiguous ones live here. A ROLL or a PACKET is however many
#: metres or pieces a particular supplier winds onto it, so those are per-item
#: and live in UnitConversion instead of being guessed globally.
GLOBAL_UNIT_CONVERSIONS = {
    ('KILOGRAM', 'GRAM'): Decimal('1000'),
    ('GRAM', 'KILOGRAM'): Decimal('0.001'),
    ('PAIR', 'PIECE'): Decimal('2'),
    ('PIECE', 'PAIR'): Decimal('0.5'),
}


class UnitConversion(models.Model):
    """How one unit of an item converts into another.

    Per item, because the answer is a property of the goods rather than of the
    words: a roll of lining is 50 metres and a roll of piping is 20, and a
    system that assumed one number for "roll" would silently order the wrong
    quantity of one of them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(
        'InventoryItem', on_delete=models.CASCADE, related_name='unit_conversions')
    from_unit = models.CharField(max_length=20, choices=Unit.choices)
    to_unit = models.CharField(max_length=20, choices=Unit.choices)
    factor = models.DecimalField(
        max_digits=14, decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text='One from_unit equals this many to_unit.')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'from_unit', 'to_unit'], name='uniq_item_unit_conversion'),
            models.CheckConstraint(
                condition=~models.Q(from_unit=models.F('to_unit')),
                name='unit_conversion_differs'),
        ]

    def __str__(self):
        return f"{self.item.name}: 1 {self.from_unit} = {self.factor} {self.to_unit}"


class StockLocation(models.Model):
    """Somewhere stock can physically be.

    A boutique's material does not sit in one place: it arrives at the store,
    waits in the warehouse, goes out to the cutting unit, then to embroidery,
    then to a tailor. `InventoryItem.current_stock` stays the authoritative
    total; LocationStock below is the breakdown of where that total is, and the
    two are kept in step by InventoryService.
    """

    class Kind(models.TextChoices):
        MAIN_STORE = 'MAIN_STORE', 'Main Store'
        WAREHOUSE = 'WAREHOUSE', 'Warehouse'
        WORKSHOP = 'WORKSHOP', 'Workshop'
        CUTTING_UNIT = 'CUTTING_UNIT', 'Cutting Unit'
        EMBROIDERY_UNIT = 'EMBROIDERY_UNIT', 'Embroidery Unit'
        TAILOR = 'TAILOR', 'Tailor / Master'
        FINISHING_UNIT = 'FINISHING_UNIT', 'Finishing Unit'
        SHOWROOM = 'SHOWROOM', 'Showroom'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=30, choices=Kind.choices, db_index=True)
    #: Where stock lands when a movement does not name a location. Exactly one
    #: row carries this, which is what lets every existing caller keep working
    #: without passing a location it never had to think about before.
    is_default = models.BooleanField(default=False)
    #: A TAILOR location can be tied to the person holding the material, so
    #: "where is it" and "who has it" are the same answer.
    tailor = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_locations')
    is_active = models.BooleanField(default=True, db_index=True)
    sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sequence', 'name']
        constraints = [
            models.UniqueConstraint(fields=['name'], name='uniq_stock_location_name'),
            models.UniqueConstraint(
                fields=['is_default'], condition=models.Q(is_default=True),
                name='one_default_stock_location',
            ),
        ]

    def __str__(self):
        return self.name


class LocationStock(models.Model):
    """How much of one item is at one location.

    Written only by InventoryService, alongside the movement that caused it.
    The sum of these across locations equals InventoryItem.current_stock; the
    reconciliation test asserts exactly that.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # A string reference because InventoryItem is declared further down.
    item = models.ForeignKey(
        'InventoryItem', on_delete=models.CASCADE, related_name='location_stocks')
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='stocks')
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['location__sequence']
        constraints = [
            models.UniqueConstraint(fields=['item', 'location'], name='uniq_item_location_stock'),
        ]

    def __str__(self):
        return f"{self.item.name} @ {self.location.name}: {self.quantity}"


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
    #: Where this came from in the published catalogue, when it came from there
    #: at all. Null for an item the boutique invented itself, which stays legal.
    catalog_item = models.ForeignKey(
        CatalogItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stocked_as')
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

    def refresh_from_db(self, *args, **kwargs):
        """Re-read the row, and re-take the snapshot with it.

        Without this the two disagree after a refresh -- the fields hold the new
        balance and the snapshot the old one -- so the guard reads a legitimate
        refresh as an illegal edit and refuses the next save of any field at all.
        """
        super().refresh_from_db(*args, **kwargs)
        self._snapshot_stock()

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
            # The check above compares the instance against its OWN snapshot, so
            # it cannot see a stale instance: one loaded before a movement still
            # holds the balance from then, agrees with its snapshot, and a plain
            # save() writes that old figure back over the real one. Nothing is
            # "changed" from the instance's point of view, and stock is silently
            # rewound. Re-reading the columns here makes the write a no-op for
            # them whatever the instance believes.
            fresh = (type(self).objects.filter(pk=self.pk)
                     .values(*self._STOCK_FIELDS).first())
            if fresh:
                for field, value in fresh.items():
                    setattr(self, field, value)
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
        #: Stock arriving against a purchase order, as distinct from STOCK_IN,
        #: which is any other way material turns up on the shelf.
        GOODS_RECEIPT = 'GOODS_RECEIPT', 'Goods Receipt'
        STOCK_IN = 'STOCK_IN', 'Stock In'
        RESERVATION = 'RESERVATION', 'Reservation'
        RELEASE = 'RELEASE', 'Reservation Released'
        ISSUE = 'ISSUE', 'Issued to Production'
        CONSUMPTION = 'CONSUMPTION', 'Consumed'
        RETURN = 'RETURN', 'Return to Stock'
        TRANSFER = 'TRANSFER', 'Transfer'
        DAMAGE = 'DAMAGE', 'Damaged'
        #: Waste is material lost in the making -- offcuts, spoilage. Damage is
        #: material that was fine until something happened to it. They are
        #: separate lines because waste % is a production metric and damage % is
        #: a handling one, and averaging them together tells you nothing.
        WASTE = 'WASTE', 'Waste'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
        SCRAP = 'SCRAP', 'Scrapped'
        CUSTOMER_RETURN = 'CUSTOMER_RETURN', 'Customer Return'
        SUPPLIER_RETURN = 'SUPPLIER_RETURN', 'Supplier Return'

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
    #: Where the material came from and went to. A transfer sets both; a receipt
    #: sets only `to_location`; an issue or a waste line only `from_location`.
    #: Together they are what makes a movement traceable rather than just a
    #: change in a number.
    from_location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, null=True, blank=True,
        related_name='movements_out')
    to_location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, null=True, blank=True,
        related_name='movements_in')
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


class BillOfMaterials(models.Model):
    """What one garment is made of.

    A recipe rather than a shopping list: lines carry formulas and waste
    allowances, so the same BOM produces different quantities for different
    measurements. Stage 4 turns a BOM plus an order into reservations; this
    holds the recipe and can work out what it needs.

    Versioned rather than edited in place. An order that was costed and reserved
    against version 3 must keep meaning what it meant, so raising a new version
    supersedes the old one instead of rewriting it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    #: Which garment this is the recipe for. String references: apps.catalog
    #: already imports this module, so importing it back would be a cycle.
    template = models.ForeignKey(
        'catalog.GarmentTemplate', on_delete=models.CASCADE,
        null=True, blank=True, related_name='boms')
    #: Or a specific design, when one design's recipe differs from the garment's.
    design = models.ForeignKey(
        'design_studio.DesignAsset', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='boms')
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', '-version']
        # Four partial indexes rather than one over (template, design, version).
        # Postgres treats NULLs as distinct in a unique index, so a single
        # constraint fires only when template AND design are both set -- which
        # is the rare case. The ordinary case is a template-scoped BOM with no
        # design, and there the constraint was silently inert: two active
        # "version 1" recipes for the same garment could coexist, and a version
        # number stopped identifying anything. Each pattern is constrained by
        # the identity it actually has, and a standalone BOM has only its name.
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'design', 'version'],
                condition=models.Q(template__isnull=False, design__isnull=False),
                name='uniq_bom_version_template_design'),
            models.UniqueConstraint(
                fields=['template', 'version'],
                condition=models.Q(template__isnull=False, design__isnull=True),
                name='uniq_bom_version_template'),
            models.UniqueConstraint(
                fields=['design', 'version'],
                condition=models.Q(template__isnull=True, design__isnull=False),
                name='uniq_bom_version_design'),
            models.UniqueConstraint(
                fields=['name', 'version'],
                condition=models.Q(template__isnull=True, design__isnull=True),
                name='uniq_bom_version_standalone'),
        ]

    def __str__(self):
        return f"{self.name} v{self.version}"


class BomLine(models.Model):
    """One material a garment needs, and how much of it."""

    class Role(models.TextChoices):
        """The part a material plays. Every role the specification names."""

        FABRIC = 'FABRIC', 'Fabric'
        LINING = 'LINING', 'Lining'
        INTERLINING = 'INTERLINING', 'Interlining'
        EMBROIDERY = 'EMBROIDERY', 'Embroidery material'
        THREAD = 'THREAD', 'Thread'
        ACCESSORY = 'ACCESSORY', 'Accessory'
        LABEL = 'LABEL', 'Label'
        PACKAGING = 'PACKAGING', 'Packaging'
        OTHER = 'OTHER', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='lines')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.FABRIC, db_index=True)

    #: What the line asks for. An inventory item names a specific stocked thing;
    #: a catalogue item names the material generically, for a BOM written before
    #: the boutique has decided which supplier's version of it to hold.
    inventory_item = models.ForeignKey(
        'InventoryItem', on_delete=models.PROTECT, null=True, blank=True, related_name='bom_lines')
    catalog_item = models.ForeignKey(
        CatalogItem, on_delete=models.PROTECT, null=True, blank=True, related_name='bom_lines')
    #: For a customer-supplied line, which needs neither: the customer is
    #: bringing "her own gold border" and there is no boutique row for it.
    description = models.CharField(max_length=200, blank=True, null=True)

    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Fixed quantity, used when no formula is given.')
    #: An arithmetic expression over the garment's measurements. Takes precedence
    #: over `quantity` when set. Evaluated by formula.evaluate, never by eval().
    quantity_formula = models.CharField(max_length=500, blank=True, null=True)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)

    #: Added on top of the computed quantity. Cutting loses fabric at every
    #: layout, so a BOM that reserves the exact finished measurement always
    #: reserves too little.
    waste_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0'))])

    is_optional = models.BooleanField(
        default=False, help_text='Skipped unless the order asks for it.')
    is_customer_supplied = models.BooleanField(
        default=False,
        help_text='Brought by the customer. Never reserved from boutique stock.')
    sequence = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['sequence', 'role']
        constraints = [
            # A line has to ask for *something*. Customer-supplied lines are the
            # exception: they are described rather than stocked.
            models.CheckConstraint(
                condition=(
                    models.Q(inventory_item__isnull=False)
                    | models.Q(catalog_item__isnull=False)
                    | models.Q(is_customer_supplied=True)
                ),
                name='bom_line_names_a_material',
            ),
        ]

    @property
    def material_name(self):
        if self.inventory_item_id:
            return self.inventory_item.name
        if self.catalog_item_id:
            return self.catalog_item.name
        return self.description or 'Unnamed material'

    def __str__(self):
        return f"{self.material_name} ({self.get_role_display()})"


class OrderMaterialPlan(models.Model):
    """A BOM, resolved against one order, with what happened to it.

    The specification's order integration in one object: the plan is generated
    from a BOM when the order is created, reserves against stock, records what
    was actually consumed and wasted, returns what was not used, and has to
    reconcile before the order can close.

    The requirement is snapshotted onto the lines rather than recomputed from
    the BOM each time. A BOM can be re-versioned and a customer's measurements
    can be corrected; neither should silently change what an order already
    reserved.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        RESERVED = 'RESERVED', 'Reserved'
        IN_PRODUCTION = 'IN_PRODUCTION', 'In production'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='material_plans')
    bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.PROTECT, related_name='plans')
    #: The BOM version this was generated from, frozen. The BOM may move on.
    bom_version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    #: The measurements the formulas were evaluated against, kept so a plan can
    #: be explained months later without re-deriving where its numbers came from.
    variables = models.JSONField(default=dict, blank=True)
    packaging_deducted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # One live plan per order. A second would reserve the same materials
            # twice over, which is precisely what step 4 forbids.
            models.UniqueConstraint(
                fields=['order'],
                condition=models.Q(status__in=['DRAFT', 'RESERVED', 'IN_PRODUCTION']),
                name='one_live_material_plan_per_order',
            ),
        ]

    @property
    def is_live(self):
        return self.status in (self.Status.DRAFT, self.Status.RESERVED,
                               self.Status.IN_PRODUCTION)

    def __str__(self):
        return f"Materials for {self.order.order_id} ({self.get_status_display()})"


class OrderMaterialLine(models.Model):
    """One material an order needs, and its running account.

    Quantities are cumulative and only ever move forward: reserved, consumed,
    wasted, returned. The reconciliation check reads them back.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(OrderMaterialPlan, on_delete=models.CASCADE, related_name='lines')
    bom_line = models.ForeignKey(
        BomLine, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_lines')
    item = models.ForeignKey(
        'InventoryItem', on_delete=models.PROTECT, null=True, blank=True,
        related_name='order_material_lines')
    role = models.CharField(max_length=20, choices=BomLine.Role.choices,
                            default=BomLine.Role.FABRIC, db_index=True)
    material_name = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)

    required_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    reserved_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    consumed_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    wasted_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    returned_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    #: A customer-supplied line is part of the recipe but never touches boutique
    #: stock. It is satisfied from CustomerMaterial instead.
    is_customer_supplied = models.BooleanField(default=False, db_index=True)
    sequence = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sequence', 'role']

    @property
    def outstanding_reservation(self):
        """Still reserved and not yet accounted for."""
        return self.reserved_quantity - self.consumed_quantity - self.wasted_quantity - self.returned_quantity

    def __str__(self):
        return f"{self.material_name} x{self.required_quantity} {self.unit}"


class CustomerMaterial(models.Model):
    """Material the customer brought, tracked entirely apart from boutique stock.

    The specification is explicit that these must never be added to inventory,
    and the reason is not bookkeeping neatness: a customer's silk is not the
    boutique's to reserve against another order, to value as an asset, or to
    reorder when it runs low. So this is its own ledger, with its own balances,
    linked only to the order it arrived for.
    """

    class Kind(models.TextChoices):
        FABRIC = 'FABRIC', 'Fabric'
        BORDER = 'BORDER', 'Border'
        LACE = 'LACE', 'Lace'
        ACCESSORY = 'ACCESSORY', 'Accessory'
        EMBROIDERY = 'EMBROIDERY', 'Embroidery material'
        OTHER = 'OTHER', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='customer_materials')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.FABRIC, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.METER)

    received_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(Decimal('0'))])
    used_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    returned_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    damaged_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    received_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['order', 'name']

    @property
    def remaining_quantity(self):
        """What is still the customer's, in the boutique's hands."""
        return (self.received_quantity - self.used_quantity
                - self.returned_quantity - self.damaged_quantity)

    def __str__(self):
        return f"{self.name} ({self.order.order_id}) — {self.remaining_quantity} {self.unit} left"


class CustomerMaterialMovement(models.Model):
    """The customer ledger's audit line.

    Boutique stock is only ever changed through a movement; the customer's
    material deserves the same treatment, because "where did the other two
    metres of my sari go" is a question the boutique has to be able to answer.
    """

    class Type(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received from customer'
        USED = 'USED', 'Used in the garment'
        RETURNED = 'RETURNED', 'Returned to customer'
        DAMAGED = 'DAMAGED', 'Damaged'
        CORRECTION = 'CORRECTION', 'Correction'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.ForeignKey(
        CustomerMaterial, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    previous_remaining = models.DecimalField(max_digits=12, decimal_places=3)
    new_remaining = models.DecimalField(max_digits=12, decimal_places=3)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    user_name_snapshot = models.CharField(max_length=150, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} of {self.material.name}"
