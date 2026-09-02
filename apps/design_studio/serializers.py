from rest_framework import serializers

from .models import (
    Collection, Designer, DesignApproval, DesignAsset, DesignAssignment, DesignBoard,
    DesignBoardItem, DesignImage,
)


class DesignerSerializer(serializers.ModelSerializer):
    design_count = serializers.IntegerField(read_only=True)
    # Present so the UI can tell a credit-only designer from one with a login,
    # without exposing which account it is.
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Designer
        fields = [
            'id', 'name', 'employee_id', 'email', 'profile_image', 'specialisation',
            'experience_years', 'bio', 'is_active', 'joined_at', 'last_active_at',
            'staff', 'design_count', 'has_login', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_has_login(self, designer):
        return designer.user_id is not None

    def to_representation(self, instance):
        """A colleague's address is also their username.

        DesignStudioPermission opens all safe methods to every signed-in role,
        so this shipped every designer's email AND whether that address can be
        signed in as -- a map of live accounts, next to a bootstrap password
        written in this repository and in the browser bundle. TailorSerializer
        was narrowed for exactly this reason; one of the two staff serializers
        was fixed and the other was not. The library's designer filter needs
        only id, name and design_count.
        """
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request is not None:
            from core.roles import OWNER, resolve_user_role
            if resolve_user_role(request.user) != OWNER:
                data.pop('email', None)
                data.pop('has_login', None)
        return data


class CollectionSerializer(serializers.ModelSerializer):
    design_count = serializers.IntegerField(read_only=True)
    designer_name = serializers.CharField(source='designer.name', read_only=True)

    class Meta:
        model = Collection
        fields = [
            'id', 'designer', 'designer_name', 'name', 'description', 'cover_image',
            'season', 'is_active', 'sequence', 'design_count', 'created_at',
        ]
        read_only_fields = ['created_at']


class DesignApprovalSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source='reviewer.first_name', read_only=True, default='')

    class Meta:
        model = DesignApproval
        fields = ['id', 'decision', 'note', 'reviewer_name', 'created_at']


class DesignImageSerializer(serializers.ModelSerializer):
    """One photograph of one part of a design."""

    class Meta:
        model = DesignImage
        fields = ['id', 'part', 'image_url', 'caption', 'sequence']


class DesignAssetSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    # Every photograph of this design, each labelled with the part of the
    # garment it shows. Read-only here for the same reason `gallery` is: the
    # rows are written from the files that were actually stored, not from a
    # claim in the request body.
    images = DesignImageSerializer(many=True, read_only=True)
    # The credited name, whichever way the design carries it: a linked designer
    # where there is one, the imported free text otherwise.
    designer_name = serializers.SerializerMethodField()
    collection_name = serializers.CharField(source='collection.name', read_only=True, default='')

    class Meta:
        model = DesignAsset
        fields = '__all__'
        # status/approved_by/approved_at are decided by the upload gate and the
        # review action, never by whatever a client happened to post. gallery
        # is filled from the files that were actually stored, not a claim.
        read_only_fields = [
            'created_by', 'created_at', 'updated_at',
            'status', 'approved_by', 'approved_at', 'gallery', 'images',
            # `source` is provenance, and provenance is what defines the
            # catalogue: BoutiqueDesignViewSet selects on source alone. Leaving
            # it writable let a designer PATCH their own unreviewed upload to
            # source='catalogue' and put it in front of customers with its
            # status still PENDING and no approval recorded -- straight past the
            # gate the approval queue exists to be. The counters are here for
            # the same reason: they are earned by the library recording views
            # and orders, not claimed by whoever posts.
            'source', 'external_id',
            'view_count', 'order_count', 'popularity', 'is_favourite',
        ]

    def get_designer_name(self, asset):
        if asset.designer_ref_id:
            return asset.designer_ref.name
        return asset.designer or ''


class DesignBoardItemSerializer(serializers.ModelSerializer):
    production_notes_by_name = serializers.CharField(
        source='production_notes_by.name', read_only=True, default='')

    class Meta:
        model = DesignBoardItem
        fields = '__all__'
        read_only_fields = ['board', 'is_selected', 'production_notes', 'production_notes_by']


class DesignBoardSerializer(serializers.ModelSerializer):
    items = DesignBoardItemSerializer(many=True, read_only=True)
    selected = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    order_id_display = serializers.CharField(source='order.order_id', read_only=True, default='')

    class Meta:
        model = DesignBoard
        fields = '__all__'
        read_only_fields = ['status', 'created_by', 'approved_by', 'approved_at', 'order']

    def get_selected(self, obj):
        item = obj.selected_item
        return DesignBoardItemSerializer(item).data if item else None

    def get_customer_name(self, obj):
        customer = obj.customer
        return f"{customer.first_name} {customer.last_name}".strip()


class TailorBriefSerializer(serializers.ModelSerializer):
    """What a Tailor is shown: the approved design and how to make it."""

    customer_name = serializers.SerializerMethodField()
    order_id_display = serializers.CharField(source='order.order_id', read_only=True, default='')
    design = serializers.SerializerMethodField()

    class Meta:
        model = DesignBoard
        fields = ['id', 'status', 'customer_name', 'order_id_display', 'approved_at', 'design']

    def get_customer_name(self, obj):
        customer = obj.customer
        return f"{customer.first_name} {customer.last_name}".strip()

    def get_design(self, obj):
        item = obj.selected_item
        if item is None:
            return None
        return {
            # The item id is what the production-notes endpoint is keyed on.
            # Without it the brief could be read but never annotated, which is
            # half of why that endpoint had no caller.
            'id': str(item.id),
            'title': item.title,
            'image_url': item.image_url,
            'source': item.source,
            'source_url': item.source_url,
            'attributes': item.attributes,
            'colour_palette': item.colour_palette,
            'customer_notes': item.customer_notes,
            'tailor_instructions': item.tailor_instructions,
            'production_notes': item.production_notes,
        }


class DiscoverRequestSerializer(serializers.Serializer):
    # Both optional, and neither required.
    #
    # A saved customer personalises off their profile and history; a draft off
    # what has been typed so far. Neither means an anonymous browse, which is
    # the first screen of the order wizard: the boutique shows a walk-in
    # customer the catalogue and lets them pick a design and a fabric BEFORE
    # anyone asks for their name. There is nothing to personalise from at that
    # point and nothing that should have to be invented -- no Customer row, and
    # no empty draft parked in the resume list -- so the search simply runs
    # unpersonalised and ranks on the garment alone.
    customer_id = serializers.UUIDField(required=False)
    draft_id = serializers.UUIDField(required=False)
    #: Which dress on the order. A draft garment's key, or a confirmed
    #: GarmentJob id once the order exists.
    garment_key = serializers.CharField(required=False, allow_blank=True)
    garment_type = serializers.CharField(required=False, allow_blank=True)
    occasion = serializers.CharField(required=False, allow_blank=True)
    budget = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    delivery_timeline = serializers.CharField(required=False, allow_blank=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)
    sources = serializers.ListField(child=serializers.CharField(), required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)


class _AssignmentDesignMixin:
    """The submitted design, flattened. Shared so both audiences see one shape."""

    def get_design_detail(self, obj):
        if obj.design_id is None:
            return None
        design = obj.design
        return {
            'id': str(design.id),
            'title': design.title,
            'image_url': design.image_url,
            'source': design.source,
            'status': design.status,
            'description': design.description,
            'gallery': design.gallery,
            'spec_tags': design.spec_tags,
        }


class DesignAssignmentSerializer(_AssignmentDesignMixin, serializers.ModelSerializer):
    """The Owner/Master view: who is doing what, on which garment, for whom."""

    designer_name = serializers.CharField(source='designer.name', read_only=True)
    garment_name = serializers.CharField(source='garment_job.template.name', read_only=True)
    order_id = serializers.CharField(source='garment_job.order.order_id', read_only=True)
    customer_name = serializers.SerializerMethodField()
    design_detail = serializers.SerializerMethodField()

    class Meta:
        model = DesignAssignment
        fields = [
            'id', 'garment_job', 'garment_name', 'order_id', 'customer_name',
            'designer', 'designer_name', 'status', 'brief', 'due_date',
            'design', 'design_detail', 'submission_note', 'review_note',
            'assigned_at', 'submitted_at', 'reviewed_at', 'updated_at',
        ]
        # Status moves through the submit/review endpoints, which log and stamp
        # it. A writable status here would let the same PATCH that edits a brief
        # mark the work approved, with no reviewer and no timestamp.
        read_only_fields = [
            'status', 'design', 'submission_note', 'review_note',
            'assigned_at', 'submitted_at', 'reviewed_at', 'updated_at',
        ]
        extra_kwargs = {
            # The OneToOne's implicit UniqueValidator rejects a second POST for
            # the same garment with a 400 before the view is ever reached, and a
            # second POST is how an owner moves the work to a different
            # designer. DesignAssignmentViewSet.create owns that decision --
            # it reassigns an open row and refuses an approved one with a 409 --
            # so the uniqueness check has to be there, where the two cases can
            # be told apart, rather than here where they cannot.
            'garment_job': {'validators': []},
        }

    def get_customer_name(self, obj):
        customer = obj.garment_job.order.customer
        return f"{customer.first_name} {customer.last_name}".strip()


class DesignerAssignmentSerializer(_AssignmentDesignMixin, serializers.ModelSerializer):
    """The Designer's own view of a job on their desk.

    Deliberately narrower than the serializer above, and narrower in one
    specific direction: it carries everything needed to *do* the work -- the
    garment, its spec, its measurements, the brief -- and nothing that
    identifies the customer or prices the order. §4.2 of docs/design-management
    lists "view customer information" and "view revenue / margin" as Owner-only,
    and until now that was a frontend courtesy because a designer had no
    order-shaped endpoint at all. This is that endpoint, so the line is drawn
    here in the payload rather than left to the client to respect.

    `order_ref` is the order id and not the customer, because a designer has to
    be able to say which job they mean when they ask the owner a question.
    """

    designer_name = serializers.CharField(source='designer.name', read_only=True)
    garment_name = serializers.CharField(source='garment_job.template.name', read_only=True)
    order_ref = serializers.CharField(source='garment_job.order.order_id', read_only=True)
    spec = serializers.JSONField(source='garment_job.spec', read_only=True)
    measurements = serializers.JSONField(source='garment_job.measurements', read_only=True)
    design_detail = serializers.SerializerMethodField()

    class Meta:
        model = DesignAssignment
        fields = [
            'id', 'garment_job', 'garment_name', 'order_ref', 'spec', 'measurements',
            'designer', 'designer_name', 'status', 'brief', 'due_date',
            'design', 'design_detail', 'submission_note', 'review_note',
            'assigned_at', 'submitted_at', 'reviewed_at',
        ]
        read_only_fields = fields
