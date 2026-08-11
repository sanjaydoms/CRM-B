from rest_framework import serializers

from .models import Collection, Designer, DesignApproval, DesignAsset, DesignBoard, DesignBoardItem


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


class DesignAssetSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source='get_source_display', read_only=True)
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
            'status', 'approved_by', 'approved_at', 'gallery',
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
    customer_id = serializers.UUIDField()
    garment_type = serializers.CharField(required=False, allow_blank=True)
    occasion = serializers.CharField(required=False, allow_blank=True)
    budget = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    delivery_timeline = serializers.CharField(required=False, allow_blank=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)
    sources = serializers.ListField(child=serializers.CharField(), required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
