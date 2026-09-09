"""Manual business costs, and the one thing this app is really for: a place to
enter the money the boutique spends that nothing else records.

Inventory spend and staff salaries are NOT stored here -- they already live in
apps.inventory (PurchaseOrder) and apps.payroll (Payout), and the P&L service
reads them straight from those. Duplicating them here would double-count the
moment someone entered a purchase both as a PO and as an expense. So the
categories below are exactly the recurring costs that had no home before: rent,
utilities, and the rest.
"""

import uuid

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from crm_api.models import IMAGE_PATH_MAX_LENGTH, _unguessable_path


def _receipt_storage():
    """Raw storage under Cloudinary -- a receipt is usually a PDF or a photo.

    Same reasoning as apps.staff.StaffDocument: the image-only Cloudinary
    endpoint rejects a PDF, so read the resolved default backend and fall back
    to raw when it is Cloudinary. Local checkouts and tests keep the disk.
    """
    from django.conf import settings
    if 'cloudinary' in settings.STORAGES['default']['BACKEND']:
        from cloudinary_storage.storage import RawMediaCloudinaryStorage
        return RawMediaCloudinaryStorage()
    from django.core.files.storage import default_storage
    return default_storage


def upload_to_receipts(instance, filename):
    return _unguessable_path('expense_receipts', filename)


class Expense(models.Model):
    """One cost the owner paid that no other part of the system records.

    `incurred_on` is the date the cost belongs to -- the month it lands in on
    the P&L -- which is not always the day it was typed in. Windowing is done
    on it, not on created_at, so a rent bill entered late still counts in the
    month it was for.
    """

    class Category(models.TextChoices):
        RENT = 'RENT', 'Rent'
        UTILITIES = 'UTILITIES', 'Utilities'
        MARKETING = 'MARKETING', 'Marketing'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance & repairs'
        SUPPLIES = 'SUPPLIES', 'Shop supplies'
        PROFESSIONAL = 'PROFESSIONAL', 'Professional fees'
        OTHER = 'OTHER', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=20, choices=Category.choices,
                                default=Category.OTHER, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(0)])
    incurred_on = models.DateField(db_index=True)
    paid_to = models.CharField(max_length=150, blank=True, default='')
    note = models.TextField(blank=True, default='')
    receipt = models.FileField(upload_to=upload_to_receipts,
                               storage=_receipt_storage,
                               max_length=IMAGE_PATH_MAX_LENGTH,
                               blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='expenses_created')

    class Meta:
        ordering = ['-incurred_on', '-created_at']
        indexes = [models.Index(fields=['incurred_on', 'category'])]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0),
                                   name='finance_expense_amount_not_negative'),
        ]

    def __str__(self):
        return f"{self.get_category_display()} · {self.amount} · {self.incurred_on}"
