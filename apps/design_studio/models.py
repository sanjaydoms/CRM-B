
import uuid

from django.contrib.auth.models import User
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from apps.catalog.models import GarmentJob, GarmentTemplate
from crm_api.models import Customer, Order, Tailor


class Designer(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, db_index=True)
    employee_id = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')

    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designer_profile',
        help_text='Set once the designer has a login. Null means credit only.',
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
            models.UniqueConstraint(fields=['name'], name='designer_unique_name'),
        ]

    def __str__(self):
        return self.name


class Collection(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    designer = models.ForeignKey(
        Designer, on_delete=models.CASCADE, related_name='collections')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')
    cover_image = models.CharField(max_length=500, blank=True, default='')
    season = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Free text: 'Bridal 2026', 'Summer'.")
    is_active = models.BooleanField(default=True, db_index=True)
    sequence = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['designer', 'name'], name='collection_unique_per_designer'),
        ]

    def __str__(self):
        return f"{self.name} ({self.designer.name})"


class DesignAsset(models.Model):


    SOURCE_UPLOAD = 'upload'
    SOURCE_FAVOURITE = 'favourite'
    SOURCE_PINTEREST = 'pinterest'
    SOURCE_GOOGLE = 'google'
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
    external_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    title = models.CharField(max_length=200)
    image_url = models.CharField(max_length=500)
    source_url = models.CharField(max_length=500, blank=True, default='')
    designer = models.CharField(max_length=150, blank=True, default='')
    designer_ref = models.ForeignKey(
        Designer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designs', db_index=True,
    )

    garment_type = models.CharField(max_length=100, blank=True, default='', db_index=True)
    occasion = models.CharField(max_length=100, blank=True, default='', db_index=True)
    attributes = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    colour_palette = models.JSONField(default=list, blank=True)

    template = models.ForeignKey(
        GarmentTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designs', db_index=True,
    )
    spec_tags = models.JSONField(default=dict, blank=True)

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING = 'PENDING', 'Pending approval'
        ACTIVE = 'ACTIVE', 'Active'
        ARCHIVED = 'ARCHIVED', 'Archived'

    class Visibility(models.TextChoices):
        BOUTIQUE = 'BOUTIQUE', 'Whole boutique'
        DESIGNER_ONLY = 'DESIGNER_ONLY', 'Designer only'

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.BOUTIQUE)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_designs')
    approved_at = models.DateTimeField(null=True, blank=True)

    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designs', db_index=True)

    description = models.TextField(blank=True, default='')
    video_url = models.CharField(max_length=500, blank=True, default='')
    gallery = models.JSONField(default=list, blank=True)

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
            GinIndex(fields=['spec_tags'], name='design_asset_spec_tags_gin'),
            models.Index(fields=['status', 'template'], name='design_asset_status_template'),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_source_display()})"


class DesignApproval(models.Model):

    class Decision(models.TextChoices):
        APPROVED = 'APPROVED', 'Approved'
        CHANGES_REQUESTED = 'CHANGES_REQUESTED', 'Changes requested'
        REJECTED = 'REJECTED', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    design = models.ForeignKey(
        DesignAsset, on_delete=models.CASCADE, related_name='approvals')
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.design.title}: {self.decision}"


class DesignBoard(models.Model):


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
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='design_board')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    title = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    board = models.ForeignKey(DesignBoard, on_delete=models.CASCADE, related_name='items')
    garment_job = models.ForeignKey(
        'catalog.GarmentJob', on_delete=models.CASCADE, null=True, blank=True,
        related_name='design_items', db_index=True)

    # Which part of the garment this reference is for -- 'pallu_design',
    # 'border_design', matching a key in GarmentTemplate.design_parts.
    #
    # A customer does not choose one saree. They choose THIS pallu and THAT
    # border, off two different sarees, and the boutique stitches the
    # combination. So a selection is per part, and the board carries one
    # selected item for each -- which is what the constraint below enforces.
    #
    # 'overall' is the whole-garment reference every board had before parts
    # existed, so a board written then still reads as one selection of the
    # whole dress rather than becoming unselected.
    part = models.CharField(max_length=60, db_index=True, default='overall')

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
    production_notes = models.TextField(blank=True, default='')
    production_notes_by = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='design_notes')
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', '-match_score', 'created_at']
        constraints = [
            # One selection per garment PER PART. The rule was one per board,
            # then one per garment when an order came to mean several dresses;
            # it is now one per part of each dress, because a customer picks a
            # pallu off one saree and a border off another and the order has to
            # carry both. Without `part` in here, choosing a border would
            # unselect the pallu -- the same failure the per-garment widening
            # fixed one level up. Items with no garment keep their own rule.
            models.UniqueConstraint(
                fields=['board', 'garment_job', 'part'],
                condition=models.Q(is_selected=True),
                name='design_board_single_selection_per_garment',
            ),
            models.UniqueConstraint(
                fields=['board', 'part'],
                condition=models.Q(is_selected=True, garment_job__isnull=True),
                name='design_board_single_selection',
            ),
        ]

    def __str__(self):
        return f"{self.title or self.source_ref} on {self.board_id}"


class DesignAssignment(models.Model):

    class Status(models.TextChoices):
        ASSIGNED = 'ASSIGNED', 'Assigned'
        SUBMITTED = 'SUBMITTED', 'Submitted for review'
        APPROVED = 'APPROVED', 'Approved'
        CHANGES_REQUESTED = 'CHANGES_REQUESTED', 'Changes requested'

    OPEN_STATUSES = (Status.ASSIGNED, Status.SUBMITTED, Status.CHANGES_REQUESTED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    garment_job = models.OneToOneField(
        GarmentJob, on_delete=models.CASCADE, related_name='design_assignment')
    designer = models.ForeignKey(
        Designer, on_delete=models.PROTECT, related_name='assignments', db_index=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ASSIGNED, db_index=True)
    brief = models.TextField(
        blank=True, default='',
        help_text='What the owner is asking for, beyond what the spec already says.')
    due_date = models.DateField(null=True, blank=True)

    design = models.ForeignKey(
        DesignAsset, on_delete=models.PROTECT, null=True, blank=True,
        related_name='assignments')
    submission_note = models.TextField(blank=True, default='')
    review_note = models.TextField(blank=True, default='')

    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='design_assignments_made')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='design_assignments_reviewed')

    assigned_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['designer', 'status'], name='design_assignment_queue'),
        ]

    def __str__(self):
        return f"{self.garment_job} -> {self.designer.name} ({self.status})"


class DesignImage(models.Model):
    """One photograph of one part of a design.

    A saree design is not one picture. It is the pallu, the border, the body and
    the overall drape -- several photographs each showing a different part of the
    same garment, and a boutique shows a customer the part they asked about.

    A table rather than more entries in `DesignAsset.gallery`, which is a flat
    list of URL strings: the part has to be queryable ("show me every pallu
    design"), each image has to be removable on its own, and the order within a
    part is the boutique's choice. None of those survive a JSON blob without the
    application doing the database's job by hand.

    `part` is a plain string, not a foreign key: the vocabulary lives in
    GarmentTemplate.design_parts, which a boutique may override, and a design
    keeps its filing even if the template it was uploaded against is later
    edited. The same reasoning DesignAsset.spec_tags already uses.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    design = models.ForeignKey(
        DesignAsset, on_delete=models.CASCADE, related_name='images')
    # Matches a key in the garment template's design_parts. 'overall' is the
    # fallback every garment has, and is what pre-existing gallery images become.
    part = models.CharField(max_length=60, db_index=True, default='overall')
    image_url = models.CharField(max_length=500)
    caption = models.CharField(max_length=200, blank=True, default='')
    sequence = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['part', 'sequence', 'created_at']
        indexes = [
            # The detail view reads every image of one design, grouped by part.
            models.Index(fields=['design', 'part'], name='design_image_by_part'),
        ]

    def __str__(self):
        return f"{self.design_id} · {self.part}"
