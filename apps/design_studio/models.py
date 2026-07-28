"""Persistence for the AI Design Studio.

Only designs the boutique actually owns get a row here. Catalogue entries and
past orders already live in crm_api and are projected into search results by
their providers instead of being copied -- duplicating them would leave two
records to keep in sync and a stale gallery the first time an owner edits a
catalogue design.

A board is the unit of decision: references are collected on it, one item is
selected, and once approved the board is what the order carries into
production.
"""

import uuid

from django.contrib.auth.models import User
from django.db import models

from crm_api.models import Customer, Order, Tailor


class DesignAsset(models.Model):
    """A design reference the boutique stores in its own library."""

    SOURCE_UPLOAD = 'upload'
    SOURCE_FAVOURITE = 'favourite'
    SOURCE_PINTEREST = 'pinterest'
    SOURCE_GOOGLE = 'google'
    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, 'Team Upload'),
        (SOURCE_FAVOURITE, 'Saved Favourite'),
        (SOURCE_PINTEREST, 'Pinterest'),
        (SOURCE_GOOGLE, 'Google Images'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_UPLOAD, db_index=True)
    # The originating platform's own id, used to avoid importing the same pin
    # or image twice. Blank for uploads, which have no upstream identity.
    external_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    title = models.CharField(max_length=200)
    image_url = models.CharField(max_length=500)
    source_url = models.CharField(max_length=500, blank=True, default='')
    designer = models.CharField(max_length=150, blank=True, default='')

    garment_type = models.CharField(max_length=100, blank=True, default='', db_index=True)
    occasion = models.CharField(max_length=100, blank=True, default='', db_index=True)
    # Structured garment attributes: neck_type, sleeve, fabric, embroidery,
    # colour, fit, pattern. Kept as JSON because the useful set differs by
    # garment and grows as new sources are added.
    attributes = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    colour_palette = models.JSONField(default=list, blank=True)

    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    popularity = models.IntegerField(default=0)
    is_favourite = models.BooleanField(default=False, db_index=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='design_assets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'external_id'],
                condition=~models.Q(external_id=''),
                name='design_asset_unique_external_ref',
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_source_display()})"


class DesignBoard(models.Model):
    """The shortlist an owner builds for one customer during order creation."""

    STATUS_DRAFT = 'DRAFT'
    STATUS_SHORTLISTED = 'SHORTLISTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SHORTLISTED, 'Shortlisted'),
        (STATUS_APPROVED, 'Approved'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='design_boards')
    # Set when the board is saved to an order. A board starts before the order
    # exists, so this stays null through the wizard.
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='design_board')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    title = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    # The context snapshot the search ran against, kept so a board can be
    # explained months later even after the customer's profile has moved on.
    context_snapshot = models.JSONField(default=dict, blank=True)
    search_queries = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='design_boards')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_design_boards')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Design board for {self.customer.first_name} ({self.status})"

    @property
    def selected_item(self):
        return self.items.filter(is_selected=True).first()


class DesignBoardItem(models.Model):
    """One design on a board, stored as a snapshot rather than a reference.

    Search results come from catalogue rows, past orders and external
    platforms alike, so there is no single foreign key that could point at all
    of them. Snapshotting also means an approved design keeps showing the tailor
    what was agreed even if the catalogue entry is later edited or deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    board = models.ForeignKey(DesignBoard, on_delete=models.CASCADE, related_name='items')

    source = models.CharField(max_length=32, db_index=True)
    source_ref = models.CharField(max_length=255, blank=True, default='')
    title = models.CharField(max_length=200, blank=True, default='')
    image_url = models.CharField(max_length=500, blank=True, default='')
    source_url = models.CharField(max_length=500, blank=True, default='')
    attributes = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    colour_palette = models.JSONField(default=list, blank=True)
    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    match_score = models.IntegerField(default=0)
    match_reasons = models.JSONField(default=list, blank=True)

    is_selected = models.BooleanField(default=False, db_index=True)
    customer_notes = models.TextField(blank=True, default='')
    tailor_instructions = models.TextField(blank=True, default='')
    # Master's notes, added after the owner has approved the design.
    production_notes = models.TextField(blank=True, default='')
    production_notes_by = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='design_notes')
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', '-match_score', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['board'],
                condition=models.Q(is_selected=True),
                name='design_board_single_selection',
            ),
        ]

    def __str__(self):
        return f"{self.title or self.source_ref} on {self.board_id}"
