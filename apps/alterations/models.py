"""Post-delivery alteration records.

Deliberately a parallel graph to the production models rather than an
extension of them. `Order`, `OrderStage`, `GarmentJob`, `ProductionTask` and
`QCRecord` describe how a garment was made and are historical the moment the
order is Delivered; everything here describes what happened *after* that, and
only ever points at those rows.

The app lives in TENANT_APPS, so every table below is created inside each
boutique's own schema -- tenant isolation is the schema, not a column, exactly
as it is for orders and inventory.
"""

import uuid

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import GarmentJob
from crm_api.models import Customer, Order, Tailor


class AlterationType(models.TextChoices):
    FREE_BOUTIQUE_FAULT = 'FREE_BOUTIQUE_FAULT', 'Free / Boutique Fault'
    PAID_CLIENT_REQUEST = 'PAID_CLIENT_REQUEST', 'Paid / Customer Request'


class AlterationStatus(models.TextChoices):
    RECEIVED = 'RECEIVED', 'Received'
    INSPECTION = 'INSPECTION', 'Inspection'
    PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Approval'
    APPROVED = 'APPROVED', 'Approved'
    ASSIGNED = 'ASSIGNED', 'Assigned'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    QC = 'QC', 'Quality Check'
    READY_FOR_PICKUP = 'READY_FOR_PICKUP', 'Ready for Pickup'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


#: Nothing may change once an alteration reaches one of these.
TERMINAL_STATUSES = (AlterationStatus.COMPLETED, AlterationStatus.CANCELLED)


class AlterationTaskStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Cash'
    UPI = 'UPI', 'UPI / QR'
    CARD = 'CARD', 'Credit / Debit Card'
    BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
    OTHER = 'OTHER', 'Other'


class PaymentStatus(models.TextChoices):
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'
    REFUNDED = 'REFUNDED', 'Refunded'


class AlterationRequest(models.Model):
    """One garment, come back after delivery, needing work.

    `original_order` and `garment_job` are PROTECT rather than CASCADE: an
    alteration is a financial and audit record of its own, and deleting the
    order it refers to must not silently take the alteration's payment history
    with it. The customer stays CASCADE, matching Order.customer.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alteration_number = models.CharField(max_length=50, unique=True, db_index=True)

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE,
        related_name='alteration_requests', db_index=True,
    )
    original_order = models.ForeignKey(
        Order, on_delete=models.PROTECT,
        related_name='alteration_requests', db_index=True,
    )
    garment_job = models.ForeignKey(
        GarmentJob, on_delete=models.PROTECT,
        related_name='alteration_requests', db_index=True,
    )

    alteration_type = models.CharField(
        max_length=50, choices=AlterationType.choices,
        default=AlterationType.PAID_CLIENT_REQUEST, db_index=True,
    )
    issue_description = models.TextField(blank=True, default='')
    #: Free-form {"waist": "loosen 1 inch", ...} captured at intake.
    requested_adjustments = models.JSONField(default=dict, blank=True)
    #: What the person who handled the garment found, written during INSPECTION.
    inspection_notes = models.TextField(blank=True, default='')
    #: Measurement/specification changes agreed during inspection. Kept here
    #: rather than written back onto GarmentJob.spec, which is the historical
    #: record of what was originally made.
    inspection_adjustments = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=50, choices=AlterationStatus.choices,
        default=AlterationStatus.RECEIVED, db_index=True,
    )

    charge_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    #: Denormalised sum of COMPLETED payments. Written only by
    #: domains.alterations.services.record_alteration_payment, inside the same
    #: transaction that creates the payment row.
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    notes = models.TextField(blank=True, default='')

    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['original_order', '-created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(charge_amount__gte=0),
                name='alteration_charge_not_negative',
            ),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0),
                name='alteration_amount_paid_not_negative',
            ),
        ]

    def __str__(self):
        return (f"{self.alteration_number} - {self.customer.first_name} "
                f"{self.customer.last_name} ({self.status})")


class AlterationTask(models.Model):
    """The work itself, and who is holding the garment.

    Separate from production.ProductionTask on purpose. Forcing alteration
    work into the order's production task list is what would make the original
    order look unfinished again on every screen that reads it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alteration_request = models.ForeignKey(
        AlterationRequest, on_delete=models.CASCADE,
        related_name='tasks', db_index=True,
    )
    title = models.CharField(max_length=200)
    stage_key = models.CharField(max_length=100, db_index=True)
    status = models.CharField(
        max_length=50, choices=AlterationTaskStatus.choices,
        default=AlterationTaskStatus.PENDING, db_index=True,
    )
    assigned_to = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_alteration_tasks', db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    sequence = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['alteration_request', 'stage_key'],
                name='one_alteration_task_per_stage',
            ),
        ]

    def __str__(self):
        return f"{self.alteration_request.alteration_number} - {self.title} ({self.status})"


class AlterationActivity(models.Model):
    """Append-only audit trail. One row per meaningful transition or event."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alteration_request = models.ForeignKey(
        AlterationRequest, on_delete=models.CASCADE,
        related_name='activities', db_index=True,
    )
    event_type = models.CharField(max_length=100, db_index=True)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='alteration_activities',
    )
    #: Snapshot, because performed_by is SET_NULL and a staff account can be
    #: removed -- the audit line must still say who did it.
    performed_by_name = models.CharField(max_length=150, blank=True, default='')
    from_status = models.CharField(max_length=50, blank=True, default='')
    to_status = models.CharField(max_length=50, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['alteration_request', '-timestamp'])]
        verbose_name_plural = 'Alteration activities'

    def __str__(self):
        return (f"{self.alteration_request.alteration_number} - "
                f"{self.event_type} at {self.timestamp}")


class AlterationPayment(models.Model):
    """Money taken for a chargeable alteration.

    Its own ledger, never folded into Order.amount_paid. An alteration invoice
    is a second sale months after the first; adding it to the delivered
    order's totals would rewrite that order's books.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alteration_request = models.ForeignKey(
        AlterationRequest, on_delete=models.CASCADE,
        related_name='payments', db_index=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    transaction_reference = models.CharField(max_length=100, blank=True, default='', db_index=True)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.COMPLETED,
    )
    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='received_alteration_payments',
    )
    received_by_name = models.CharField(max_length=150, blank=True, default='')
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='alteration_payment_amount_positive',
            ),
            # Duplicate protection at the level that actually holds: two
            # concurrent requests carrying the same UPI reference cannot both
            # land, whatever the service layer happens to see.
            models.UniqueConstraint(
                fields=['alteration_request', 'transaction_reference'],
                condition=~Q(transaction_reference=''),
                name='unique_alteration_payment_reference',
            ),
        ]

    def __str__(self):
        return (f"Payment {self.amount} for "
                f"{self.alteration_request.alteration_number} ({self.payment_method})")


class AlterationMaterialLine(models.Model):
    """Stock consumed by an alteration.

    The `stock_movement` link is the traceability: every line points at the
    real InventoryService movement that moved the stock. That movement is
    written with no `order` and no `garment_job`, so the original order's
    material consumption history is neither extended nor rewritten.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alteration_request = models.ForeignKey(
        AlterationRequest, on_delete=models.CASCADE,
        related_name='material_lines', db_index=True,
    )
    item = models.ForeignKey(
        'inventory.InventoryItem', on_delete=models.PROTECT,
        related_name='alteration_material_lines', db_index=True,
    )
    #: Snapshot of the name at the time it was used, so a later rename does
    #: not rewrite what this alteration cost.
    material_name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=20, default='PIECE')
    stock_movement = models.ForeignKey(
        'inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='alteration_material_lines',
    )
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_alteration_material_lines',
    )
    recorded_by_name = models.CharField(max_length=150, blank=True, default='')
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name='alteration_material_quantity_positive',
            ),
        ]

    def __str__(self):
        return (f"{self.material_name} x{self.quantity} for "
                f"{self.alteration_request.alteration_number}")
