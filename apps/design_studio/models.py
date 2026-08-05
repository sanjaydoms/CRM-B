"""Persistence for the design library.

DesignAsset is the boutique's whole library: uploads, saved favourites, imported
references, and -- since the catalogue moved out of crm_api.BoutiqueDesign -- the
boutique's own catalogue too. One table, so one set of filters, one attribution
and one approval path covers every design rather than half of them.

The earlier note here argued against *copying* catalogue rows in, on the grounds
that two records would drift apart. That still holds, and it is why the rows were
moved rather than duplicated: BoutiqueDesign stopped being written to in the same
commit that moved them.

Past orders are still projected by their provider rather than stored, because an
order is not a library entry.

A board is the unit of decision: references are collected on it, one item is
selected, and once approved the board is what the order carries into production.
"""

import uuid

from django.contrib.auth.models import User
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from apps.catalog.models import GarmentTemplate
from crm_api.models import Customer, Order, Tailor


class Designer(models.Model):
    """Someone who contributes designs to the boutique.

    Attribution first: a designer is a credit on a design, not an account. Both
    links out of here are optional, and that is the point --

      `user`  is null until designers are given their own login. Nothing in this
              module needs it, so the security surface can wait.
      `staff` is set only when the designer is also on the production floor. Most
              are not, and a designer is deliberately *not* a Tailor role: the
              workflow asserts every staff role has a production stage it can
              work on, and design work has no stage.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, db_index=True)
    employee_id = models.CharField(max_length=50, blank=True, default='')

    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designer_profile',
        help_text='Set once designers have their own login. Null means credit only.',
    )
    staff = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designer_profiles',
        help_text='Set when this designer also works on the production floor.',
    )

    profile_image = models.CharField(max_length=500, blank=True, default='')
    specialisation = models.CharField(max_length=150, blank=True, default='')
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    bio = models.TextField(blank=True, default='')

    is_active = models.BooleanField(default=True, db_index=True)
    joined_at = models.DateField(null=True, blank=True)
    last_active_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            # Two designers with the same name are almost certainly the same
            # person entered twice, which splits a portfolio in half.
            models.UniqueConstraint(fields=['name'], name='designer_unique_name'),
        ]

    def __str__(self):
        return self.name


class DesignAsset(models.Model):
    """A design reference the boutique stores in its own library."""

    SOURCE_UPLOAD = 'upload'
    SOURCE_FAVOURITE = 'favourite'
    SOURCE_PINTEREST = 'pinterest'
    SOURCE_GOOGLE = 'google'
    # The two the boutique's own catalogue arrives as. They were BoutiqueDesign
    # rows distinguished by an is_boutique flag; the flag is the source now.
    SOURCE_CATALOGUE = 'catalogue'
    SOURCE_SUGGESTION = 'suggestion'
    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, 'Team Upload'),
        (SOURCE_FAVOURITE, 'Saved Favourite'),
        (SOURCE_PINTEREST, 'Pinterest'),
        (SOURCE_GOOGLE, 'Google Images'),
        (SOURCE_CATALOGUE, 'Boutique Catalogue'),
        (SOURCE_SUGGESTION, 'Suggestion Template'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_UPLOAD, db_index=True)
    # The originating platform's own id, used to avoid importing the same pin
    # or image twice. Blank for uploads, which have no upstream identity.
    external_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    title = models.CharField(max_length=200)
    image_url = models.CharField(max_length=500)
    source_url = models.CharField(max_length=500, blank=True, default='')
    # The credit as the source gave it -- a Pinterest pin names its designer as
    # free text and there is nobody to link to. Kept as the fallback and as the
    # provenance of an import; `designer_ref` is what the portfolio counts.
    designer = models.CharField(max_length=150, blank=True, default='')
    designer_ref = models.ForeignKey(
        Designer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designs', db_index=True,
    )

    garment_type = models.CharField(max_length=100, blank=True, default='', db_index=True)
    occasion = models.CharField(max_length=100, blank=True, default='', db_index=True)
    # Structured garment attributes: neck_type, sleeve, fabric, embroidery,
    # colour, fit, pattern. Kept as JSON because the useful set differs by
    # garment and grows as new sources are added.
    attributes = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    colour_palette = models.JSONField(default=list, blank=True)

    # The garment this design is for, as the catalogue defines it. A string
    # here would be a second taxonomy: `garment_type` above says "Lehenga" and
    # nothing guarantees it matches the template a customer's order was built
    # from. See docs/design-management.md section 2.
    template = models.ForeignKey(
        GarmentTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designs', db_index=True,
    )
    # Template-vocabulary tags: {"sleeve_length": "elbow", "occasion": "wedding"}.
    # Same shape and same values as GarmentJob.spec, which is what lets "designs
    # matching this order" be a query rather than a fuzzy string comparison.
    spec_tags = models.JSONField(default=dict, blank=True)

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING = 'PENDING', 'Pending approval'
        ACTIVE = 'ACTIVE', 'Active'
        ARCHIVED = 'ARCHIVED', 'Archived'

    class Visibility(models.TextChoices):
        BOUTIQUE = 'BOUTIQUE', 'Whole boutique'
        DESIGNER_ONLY = 'DESIGNER_ONLY', 'Designer only'

    # Existing rows are live work, so ACTIVE is the default; the approval queue
    # in a later step is what starts putting uploads into PENDING.
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.BOUTIQUE)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_designs')
    approved_at = models.DateTimeField(null=True, blank=True)

    description = models.TextField(blank=True, default='')
    video_url = models.CharField(max_length=500, blank=True, default='')

    class Difficulty(models.TextChoices):
        SIMPLE = 'SIMPLE', 'Simple'
        MODERATE = 'MODERATE', 'Moderate'
        COMPLEX = 'COMPLEX', 'Complex'

    difficulty = models.CharField(
        max_length=20, choices=Difficulty.choices, blank=True, default='')
    stitch_hours = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Estimated stitch time.')

    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    popularity = models.IntegerField(default=0)
    is_favourite = models.BooleanField(default=False, db_index=True)

    # Denormalised because the dashboard sorts on them. A COUNT(*) across the
    # library on every page load is exactly what makes a gallery of thousands
    # slow, so these are incremented at the point of the event instead.
    view_count = models.IntegerField(default=0)
    order_count = models.IntegerField(default=0)

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
        indexes = [
            # Filtering the library by sleeve, neck or occasion is a containment
            # query into spec_tags. Without this index that is a sequential scan
            # of every design in the boutique, which is the slow gallery this
            # module exists to avoid.
            GinIndex(fields=['spec_tags'], name='design_asset_spec_tags_gin'),
            models.Index(fields=['status', 'template'], name='design_asset_status_template'),
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
