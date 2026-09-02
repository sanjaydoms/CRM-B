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

from apps.catalog.models import GarmentJob, GarmentTemplate
from crm_api.models import Customer, Order, Tailor


class Designer(models.Model):
    """Someone who contributes designs to the boutique.

    Attribution came first: a designer started as a credit on a design, not an
    account, and `user` stayed null through steps 1-6 -- nothing in the module
    needed a login, so the security surface could wait. It cannot wait forever,
    because the whole point of a designer role is a person who signs in and
    uploads their own work. DesignerViewSet.create_login is what an Owner uses
    to switch a credited designer on; core.roles.resolve_user_role is what makes
    the resulting account a Designer rather than an accidental Owner.

      `user`  null means credit only; set means the designer can sign in.
      `staff` is set only when the designer is also on the production floor. Most
              are not, and a designer is deliberately *not* a Tailor role: the
              workflow asserts every staff role has a production stage it can
              work on, and design work has no stage.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, db_index=True)
    employee_id = models.CharField(max_length=50, blank=True, default='')
    # Used to create the login, and to find a User that already exists under
    # this address -- the same idempotency Tailor's own account bootstrap uses.
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
            # Two designers with the same name are almost certainly the same
            # person entered twice, which splits a portfolio in half.
            models.UniqueConstraint(fields=['name'], name='designer_unique_name'),
        ]

    def __str__(self):
        return self.name


class Collection(models.Model):
    """A curated set of designs, owned by the designer who assembles it.

    A collection is not a category. "Bridal 2026" and "Lehenga" answer different
    questions -- one is what the boutique is presenting this season, the other is
    what the garment is -- and a design belongs to one of each. Folding them into
    a single list is what makes counts stop adding up.
    """

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
            # Two designers may both have a "Bridal 2026"; one designer with two
            # is the same collection entered twice.
            models.UniqueConstraint(
                fields=['designer', 'name'], name='collection_unique_per_designer'),
        ]

    def __str__(self):
        return f"{self.name} ({self.designer.name})"


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

    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='designs', db_index=True)

    description = models.TextField(blank=True, default='')
    video_url = models.CharField(max_length=500, blank=True, default='')
    # Extra images beyond image_url, which stays the one the cards show. A list
    # rather than a table: a design has a handful of photographs, and they are
    # only ever read together with the design.
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


class DesignApproval(models.Model):
    """One review decision on a design. A log, not a status column.

    Overwriting a `status` field loses the history: the second time a design is
    submitted, there is no way to see why it was rejected in March. Each review
    writes a new row here and DesignAsset.status is only ever the current state.
    """

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
    # Which dress on the order this reference is for. Null for a board built
    # before garments were priced and designed individually, and for an
    # order-level reference that genuinely applies to the whole order.
    #
    # Deliberately on the ITEM and not the board: the board stays one per
    # order, owned by one customer, with one lifecycle -- a second, draft-owned
    # kind of board would have to be handled correctly by every query that
    # reads boards, and missing one is how a shortlist shows up on a tailor's
    # screen. A two-garment order is one board carrying items that each know
    # their garment.
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
    # Master's notes, added after the owner has approved the design.
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
    """One garment's design work, given to one designer.

    Keyed on GarmentJob, not Order. A DesignBoard is per-order (OneToOne), which
    was fine when an order meant one dress: the board *was* the design. It stops
    being fine the moment an order carries a lehenga and its blouse, because one
    board cannot say which of the two a design belongs to -- and a design that
    cannot name its garment is a design that can be stitched onto the wrong one.
    A job-keyed row makes that structural rather than a convention: there is no
    field here in which a lehenga's design could be recorded against the blouse.

    OneToOne rather than a list, because a garment has one design owner at a
    time. Reassigning replaces the designer on the existing row and the activity
    log carries the history -- see DesignApproval for the case where the history
    is load-bearing enough to need its own table. It is not here: an assignment
    has one live answer ("whose desk is this on?"), and the review verdict that
    would need a log is the design's own, which DesignApproval already keeps.
    """

    class Status(models.TextChoices):
        ASSIGNED = 'ASSIGNED', 'Assigned'
        SUBMITTED = 'SUBMITTED', 'Submitted for review'
        APPROVED = 'APPROVED', 'Approved'
        CHANGES_REQUESTED = 'CHANGES_REQUESTED', 'Changes requested'

    # Everything short of approved. Work is "open" while it is on ANYONE's
    # desk: the designer's (assigned, or sent back for changes) or the
    # reviewer's (submitted). Leaving SUBMITTED out hid a design from the
    # owner's default queue at the exact moment it was waiting on them.
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

    # The submitted work. Null until the designer submits; a library asset
    # rather than a loose upload, so the design a garment carries is the same
    # row the portfolio, the approval queue and the gallery already count.
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
            # The designer's work queue: their own rows, open ones first. This
            # is the one query the module runs on every designer page load.
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
