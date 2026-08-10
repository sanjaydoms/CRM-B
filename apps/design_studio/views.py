import json
import os
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status, viewsets, views
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.activities.models import UniversalActivity
from core.roles import OWNER, resolve_user_role
from crm_api.models import Customer, Order

from . import services
from .context import build_context
from .intelligence.registry import get_intelligence
from apps.catalog.models import GarmentTemplate

from .models import Collection, Designer, DesignApproval, DesignAsset, DesignBoard, DesignBoardItem
from .permissions import (
    MASTER, DesignLibraryPermission, DesignStudioPermission, OwnerOnly, visible_boards,
)
from .providers.registry import source_status
from .serializers import (
    DesignAssetSerializer, DesignBoardItemSerializer, DesignBoardSerializer,
    DesignerSerializer, CollectionSerializer, DesignApprovalSerializer,
    DiscoverRequestSerializer, TailorBriefSerializer,
)


def _log(request, board, action_name, title, description, new_value=None):
    user = request.user if request.user.is_authenticated else None
    UniversalActivity.objects.create(
        user=user,
        user_name_snapshot=(user.get_full_name() or user.username) if user else "System",
        module="design_studio",
        entity_type="DesignBoard",
        entity_id=str(board.id),
        action=action_name,
        title=title,
        description=description,
        new_value=new_value or {},
    )


class DesignContextView(views.APIView):
    """What the studio knows about a customer before it searches anything."""

    permission_classes = [OwnerOnly]

    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        if not customer_id:
            return Response({'detail': 'customer_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        customer = get_object_or_404(Customer.objects.select_related('measurements'), pk=customer_id)
        order_input = {
            key: request.query_params[key]
            for key in ('garment_type', 'occasion', 'budget', 'delivery_timeline')
            if request.query_params.get(key)
        }
        context = build_context(customer, order_input)
        return Response({
            'context': context.to_dict(),
            'suggested_queries': get_intelligence().generate_queries(context),
            'sources': source_status(),
        })


class DesignDiscoveryView(views.APIView):
    """Search every available source and return ranked, explained results."""

    permission_classes = [OwnerOnly]

    def post(self, request):
        payload = DiscoverRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        customer = get_object_or_404(
            Customer.objects.select_related('measurements'), pk=data['customer_id'])

        outcome = services.discover(
            customer,
            order_input={
                'garment_type': data.get('garment_type', ''),
                'occasion': data.get('occasion', ''),
                'budget': data.get('budget'),
                'delivery_timeline': data.get('delivery_timeline', ''),
            },
            extra_keywords=data.get('keywords'),
            sources=data.get('sources'),
            limit=data.get('limit', 40),
        )

        return Response({
            'context': outcome['context'].to_dict(),
            'queries': outcome['queries'],
            'sources': outcome['sources'],
            'results': [candidate.to_dict() for candidate in outcome['results']],
        })


class DesignAssetViewSet(viewsets.ModelViewSet):
    """The boutique's own design library: uploads, favourites, imports."""

    serializer_class = DesignAssetSerializer
    permission_classes = [DesignLibraryPermission]

    # Columns a caller may filter on directly. Anything else in the query string
    # is looked up inside spec_tags, so the library filters on the same
    # vocabulary the order form uses without this list growing per garment.
    DIRECT_FILTERS = {
        'template': 'template__key',
        'designer': 'designer_ref_id',
        'collection': 'collection_id',
        'status': 'status',
        'source': 'source',
    }
    # `occasion` is deliberately not above. It exists twice -- as a legacy column
    # and as a template field key -- so filtering it as a column silently missed
    # every design tagged the new way. It matches either, until the column goes.
    
    RESERVED = {'search', 'ordering', 'price_min', 'price_max', 'favourite', 'occasion',
                'page', 'page_size', 'format'}

    ORDERINGS = {
        'newest': '-created_at',
        'oldest': 'created_at',
        'most_viewed': '-view_count',
        'most_ordered': '-order_count',
        'name': 'title',
    }

    def get_queryset(self):
        queryset = DesignAsset.objects.select_related('designer_ref', 'template')
        params = self.request.query_params

        for name, field in self.DIRECT_FILTERS.items():
            if value := params.get(name):
                queryset = queryset.filter(**{field: value})

        if occasion := params.get('occasion'):
            queryset = queryset.filter(
                Q(occasion__iexact=occasion) | Q(spec_tags__contains={'occasion': occasion})
            )

        if search := params.get('search'):
            queryset = queryset.filter(title__icontains=search)
        if params.get('favourite') == 'true':
            queryset = queryset.filter(is_favourite=True)
        if price_min := params.get('price_min'):
            queryset = queryset.filter(estimated_price__gte=price_min)
        if price_max := params.get('price_max'):
            queryset = queryset.filter(estimated_price__lte=price_max)

        # Everything left is template vocabulary: ?sleeve_length=elbow becomes a
        # containment query, which the GIN index on spec_tags serves.
        for key, value in params.items():
            if key in self.DIRECT_FILTERS or key in self.RESERVED:
                continue
            queryset = queryset.filter(spec_tags__contains={key: value})

        return queryset.order_by(self.ORDERINGS.get(params.get('ordering'), '-created_at'))

    def create(self, request, *args, **kwargs):
        """Upload a design, with its photographs.

        Accepts multipart so the browser can post the files themselves rather
        than the boutique having to host an image somewhere first and paste a
        URL, which is what the catalogue form made them do.
        """
        # Not request.data.copy(). That deep-copies the QueryDict, and any
        # photograph over FILE_UPLOAD_MAX_MEMORY_SIZE (2.5MB by default) is not
        # an in-memory BytesIO but a TemporaryUploadedFile wrapping an open file
        # handle, which cannot be deep-copied -- it raises
        # "TypeError: cannot pickle 'BufferedRandom' instances" before any of
        # this method's own logic runs. A photograph taken on a phone is always
        # bigger than that, so the copy failed for precisely the uploads this
        # endpoint exists to accept, while the small test images used on a
        # desktop stayed under the threshold and passed. The files are read
        # separately by _store_images(), so the serializer only needs the
        # non-file fields.
        data = {key: value for key, value in request.data.items() if key != 'images'}

        # Rebuilding the QueryDict above costs the JSON parsing DRF would
        # normally do for us. rest_framework.fields.JSONField only treats an
        # incoming value as encoded text when the container looks like an HTML
        # form -- it tests hasattr(dictionary, 'getlist') -- and a plain dict
        # fails that test, so a multipart "{\"neckline\":\"V\"}" was saved into
        # the JSONField verbatim as a string. Every upload from the browser is
        # multipart and api.js JSON.stringify()s these fields, so this was all
        # of them; the library's own filters then matched nothing. Decoding by
        # field type rather than by name keeps any JSONField added later
        # working, which naming spec_tags alone would not.
        for name, field in self.get_serializer().fields.items():
            if isinstance(field, serializers.JSONField) and isinstance(data.get(name), str):
                try:
                    data[name] = json.loads(data[name])
                except (TypeError, ValueError):
                    pass  # leave it; the serializer reports the real error

        uploaded = self._store_images(request)
        if uploaded:
            # The first photograph is the one the cards show; the rest are the
            # gallery. Any image_url that was posted alongside wins, so an
            # imported reference is not overwritten by an accidental upload.
            data.setdefault('image_url', uploaded[0])
            if not data.get('image_url'):
                data['image_url'] = uploaded[0]

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        # The gate is per-boutique. A caller cannot post their way past it: the
        # serializer never exposes `status` as writable on create (see below),
        # so this is the only place a new design's status is decided.
        from crm_api.models import BoutiqueSettings
        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        role = resolve_user_role(request.user)
        initial_status = (
            DesignAsset.Status.ACTIVE if role == OWNER or not config.design_approval_required
            else DesignAsset.Status.PENDING
        )

        asset = serializer.save(
            created_by=request.user if request.user.is_authenticated else None,
            # A signed-in designer is credited on their own upload by default.
            # The Upload modal leaves designer_ref as '' ("Unattributed") and
            # api.js drops empty values, so a designer's own work was saved with
            # designer_ref None -- and DesignLibraryPermission gates their
            # edit/delete carve-out on designer_ref_id matching, so they were
            # then locked out of the design they had just uploaded.
            designer_ref=(serializer.validated_data.get('designer_ref')
                          or getattr(request.user, 'designer_profile', None)),
            gallery=uploaded[1:] if len(uploaded) > 1 else [],
            status=initial_status,
        )
        return Response(self.get_serializer(asset).data, status=status.HTTP_201_CREATED)

    def _store_images(self, request):
        files = request.FILES.getlist('images')
        stored = []
        for f in files:
            path = f"design_library/{uuid.uuid4()}_{f.name}"
            saved = default_storage.save(path, ContentFile(f.read()))
            stored.append(request.build_absolute_uri(default_storage.url(saved)))
        return stored

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    def retrieve(self, request, *args, **kwargs):
        """Opening a design counts as a view.

        An UPDATE rather than a save() so two people opening the same design at
        once cannot overwrite each other's increment with a stale value.
        """
        response = super().retrieve(request, *args, **kwargs)
        DesignAsset.objects.filter(pk=kwargs.get('pk')).update(view_count=F('view_count') + 1)
        return response

    @action(detail=True, methods=['POST'], url_path='favourite')
    def favourite(self, request, pk=None):
        asset = self.get_object()
        asset.is_favourite = not asset.is_favourite
        asset.save(update_fields=['is_favourite', 'updated_at'])
        return Response(self.get_serializer(asset).data)

    @action(detail=True, methods=['POST'], url_path='review')
    def review(self, request, pk=None):
        """Approve, request changes on, or reject a pending design.

        Owner-only by construction: DesignStudioPermission denies every non-safe
        method to anyone but the Owner, and there is deliberately no separate
        role check here to duplicate or drift from that.
        """
        asset = self.get_object()
        decision = request.data.get('decision')
        valid = {c[0] for c in DesignApproval.Decision.choices}
        if decision not in valid:
            return Response(
                {'decision': f"Must be one of {sorted(valid)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        DesignApproval.objects.create(
            design=asset,
            reviewer=request.user if request.user.is_authenticated else None,
            decision=decision,
            note=request.data.get('note', ''),
        )

        if decision == DesignApproval.Decision.APPROVED:
            asset.status = DesignAsset.Status.ACTIVE
            asset.approved_by = request.user if request.user.is_authenticated else None
            asset.approved_at = timezone.now()
            asset.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        elif decision == DesignApproval.Decision.REJECTED:
            asset.status = DesignAsset.Status.ARCHIVED
            asset.save(update_fields=['status', 'updated_at'])
        # CHANGES_REQUESTED leaves status at PENDING: the designer edits the
        # existing row and resubmits, rather than the design vanishing from
        # the queue while still needing work.

        return Response(self.get_serializer(asset).data)

    @action(detail=True, methods=['GET'], url_path='approval-history')
    def approval_history(self, request, pk=None):
        asset = self.get_object()
        history = asset.approvals.select_related('reviewer').all()
        return Response(DesignApprovalSerializer(history, many=True).data)


class CollectionViewSet(viewsets.ModelViewSet):
    """Curated sets, owned by a designer."""

    serializer_class = CollectionSerializer
    permission_classes = [DesignStudioPermission]

    def get_queryset(self):
        queryset = (Collection.objects
                    .select_related('designer')
                    .annotate(design_count=Count('designs')))
        params = self.request.query_params
        if designer := params.get('designer'):
            queryset = queryset.filter(designer_id=designer)
        if params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        return queryset


class DesignDashboardView(views.APIView):
    """Counters and leaderboards for the module's landing page.

    Deliberately one endpoint. The main CRM dashboard already fires eight
    parallel requests on load; this module should not add nine more just to
    show a handful of numbers.
    """

    permission_classes = [DesignStudioPermission]

    def get(self, request):
        assets = DesignAsset.objects.all()
        active = assets.filter(status=DesignAsset.Status.ACTIVE)
        week_ago = timezone.now() - timedelta(days=7)

        top = lambda qs, field: DesignAssetSerializer(qs.order_by(f'-{field}')[:5], many=True).data

        return Response({
            'total_designs': assets.count(),
            'active_designs': active.count(),
            'designers': Designer.objects.filter(is_active=True).count(),
            'collections': Collection.objects.filter(is_active=True).count(),
            'pending_approval': assets.filter(status=DesignAsset.Status.PENDING).count(),
            'recent_uploads': DesignAssetSerializer(
                assets.order_by('-created_at')[:8], many=True).data,
            'most_viewed': top(active, 'view_count'),
            'most_ordered': top(active, 'order_count'),
            # "Trending" is recency-weighted, not a lifetime total: a design
            # from a year ago with many views should not permanently outrank
            # one the boutique is showing customers this week. Scoping the
            # window to designs updated (viewed) in the last 7 days is a cheap
            # proxy for that without needing a time-series table.
            'trending': DesignAssetSerializer(
                active.filter(updated_at__gte=week_ago).order_by('-view_count')[:5],
                many=True).data,
        })


class DesignCategoryView(views.APIView):
    """Garment types with live design counts, for the library's section list.

    One query, not one per garment. The library opens on these counts, so a
    COUNT(*) per template would make the landing page cost grow with the
    catalogue -- the thing this module is supposed to survive.
    """

    permission_classes = [DesignStudioPermission]

    def get(self, request):
        counts = dict(
            DesignAsset.objects
            .filter(status=DesignAsset.Status.ACTIVE, template__isnull=False)
            .values_list('template_id')
            .annotate(n=Count('id'))
        )
        templates = GarmentTemplate.objects.filter(is_active=True).order_by('sequence', 'name')

        categories = [
            {'key': t.key, 'name': t.name, 'count': counts.get(t.id, 0)}
            for t in templates
        ]
        # Designs that predate the template link, or came from a source that
        # never named a garment. Hiding them would mean the section counts do
        # not add up to the library, and nobody would find them again.
        untagged = DesignAsset.objects.filter(
            status=DesignAsset.Status.ACTIVE, template__isnull=True).count()
        if untagged:
            categories.append({'key': '', 'name': 'Uncategorised', 'count': untagged})

        return Response({
            'categories': categories,
            'total': sum(c['count'] for c in categories),
        })


class DesignerViewSet(viewsets.ModelViewSet):
    """The people credited on designs.

    Most rows carry no login and never need to -- attribution alone covers
    steps 1-6. create_login is what turns a credited designer into someone who
    can sign in and use the module for themselves.
    """

    serializer_class = DesignerSerializer
    permission_classes = [DesignStudioPermission]

    def get_queryset(self):
        # design_count is read per row by the serializer; annotate it once here
        # so a list of designers is one query rather than one per designer.
        queryset = Designer.objects.annotate(design_count=Count('designs'))

        params = self.request.query_params
        if params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        if search := params.get('search'):
            queryset = queryset.filter(name__icontains=search)
        return queryset

    @action(detail=True, methods=['POST'], url_path='create-login')
    def create_login(self, request, pk=None):
        """Give a credited designer a login of their own.

        Owner-only by construction: DesignStudioPermission denies every
        non-safe method to anyone but the Owner, so no separate role check is
        duplicated here. Idempotent by email in the same way
        TailorViewSet._ensure_user_account is -- a second call with the same
        address links the existing account rather than erroring or duplicating
        it, so retrying a failed request is always safe.
        """
        designer = self.get_object()
        if designer.user_id:
            return Response(
                {'detail': f'{designer.name} already has a login.'},
                status=status.HTTP_400_BAD_REQUEST)

        email = request.data.get('email') or designer.email
        if not email:
            return Response({'email': 'An email address is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email=email).first()
        if user is None:
            username = email.split('@')[0]
            original, counter = username, 1
            while User.objects.filter(username=username).exists():
                username = f"{original}{counter}"
                counter += 1
            # Shared bootstrap password, the same pattern as staff accounts
            # (see TailorViewSet._ensure_user_account): override with
            # DESIGNER_DEFAULT_PASSWORD, or every designer shares one
            # credential that is visible in this repository.
            user = User.objects.create_user(
                username=username, email=email,
                password=os.environ.get('DESIGNER_DEFAULT_PASSWORD', 'DesignerSecure2026!'),
                first_name=designer.name,
            )

        designer.user = user
        designer.email = email
        designer.save(update_fields=['user', 'email', 'updated_at'])

        return Response(
            DesignerSerializer(
                Designer.objects.annotate(design_count=Count('designs')).get(pk=designer.pk)
            ).data,
            status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'])
    def portfolio(self, request, pk=None):
        """Everything this designer has contributed, newest first, plus how it
        is doing -- what the designer's own dashboard reads (step 6)."""
        designer = self.get_object()
        designs = designer.designs.all().order_by('-created_at')
        totals = designs.aggregate(
            views=Sum('view_count'), orders=Sum('order_count'))
        return Response({
            'designer': DesignerSerializer(
                Designer.objects.annotate(design_count=Count('designs')).get(pk=designer.pk)
            ).data,
            'designs': DesignAssetSerializer(designs, many=True).data,
            'stats': {
                'total_views': totals['views'] or 0,
                'total_orders': totals['orders'] or 0,
                'active': designs.filter(status=DesignAsset.Status.ACTIVE).count(),
                'pending': designs.filter(status=DesignAsset.Status.PENDING).count(),
                'collections': designer.collections.filter(is_active=True).count(),
                'most_viewed': DesignAssetSerializer(
                    designs.order_by('-view_count').first()).data if designs.exists() else None,
            },
        })


class DesignBoardViewSet(viewsets.ModelViewSet):
    serializer_class = DesignBoardSerializer
    permission_classes = [DesignStudioPermission]

    def get_queryset(self):
        queryset = (DesignBoard.objects
                    .select_related('customer', 'order')
                    .prefetch_related('items'))
        customer_id = self.request.query_params.get('customer_id')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        order_id = self.request.query_params.get('order_id')
        if order_id:
            queryset = queryset.filter(order__order_id=order_id)
        return visible_boards(queryset, self.request.user)

    def get_serializer_class(self):
        # A tailor gets the production brief, not the whole deliberation.
        if resolve_user_role(self.request.user) == 'Tailor':
            return TailorBriefSerializer
        return DesignBoardSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    @action(detail=True, methods=['POST'], url_path='items')
    def add_item(self, request, pk=None):
        """Shortlist a gallery result onto this board."""
        board = self.get_object()
        position = board.items.count()
        item = services.item_from_candidate(board, request.data, position=position)
        item.full_clean(exclude=['board'])
        item.save()
        _log(request, board, "DESIGN_SHORTLISTED",
             f"Design shortlisted: {item.title or item.source}",
             f"Added a {item.source} reference to {board.customer.first_name}'s design board.",
             {"title": item.title, "source": item.source, "match_score": item.match_score})
        return Response(DesignBoardItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['DELETE'], url_path=r'items/(?P<item_id>[^/.]+)')
    def remove_item(self, request, pk=None, item_id=None):
        board = self.get_object()
        item = get_object_or_404(board.items, pk=item_id)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['POST'], url_path=r'items/(?P<item_id>[^/.]+)/select')
    def select_item(self, request, pk=None, item_id=None):
        board = self.get_object()
        item = get_object_or_404(board.items, pk=item_id)
        services.select_item(board, item)
        _log(request, board, "DESIGN_SELECTED", f"Design selected: {item.title or item.source}",
             f"Selected the final design for {board.customer.first_name}.",
             {"title": item.title, "match_score": item.match_score})
        return Response(self.get_serializer(board).data)

    @action(detail=True, methods=['PATCH'], url_path=r'items/(?P<item_id>[^/.]+)/customise')
    def customise_item(self, request, pk=None, item_id=None):
        """Owner edits to the design: attributes, notes, tailor instructions."""
        board = self.get_object()
        item = get_object_or_404(board.items, pk=item_id)

        attributes = request.data.get('attributes')
        if isinstance(attributes, dict):
            merged = dict(item.attributes or {})
            merged.update(attributes)
            item.attributes = merged
        for field in ('customer_notes', 'tailor_instructions'):
            if field in request.data:
                setattr(item, field, request.data[field] or '')
        item.save(update_fields=['attributes', 'customer_notes', 'tailor_instructions'])
        return Response(DesignBoardItemSerializer(item).data)

    @action(detail=True, methods=['PATCH'], url_path=r'items/(?P<item_id>[^/.]+)/production-notes')
    def production_notes(self, request, pk=None, item_id=None):
        """A Master's note on how the approved design should be executed."""
        board = self.get_object()
        item = get_object_or_404(board.items, pk=item_id)
        role = resolve_user_role(request.user)
        if role == MASTER and board.status != DesignBoard.STATUS_APPROVED:
            return Response(
                {'detail': 'Production notes can only be added to an approved design.'},
                status=status.HTTP_400_BAD_REQUEST)
        item.production_notes = request.data.get('production_notes', '') or ''
        item.production_notes_by = getattr(request.user, 'tailor_profile', None)
        item.save(update_fields=['production_notes', 'production_notes_by'])
        return Response(DesignBoardItemSerializer(item).data)

    @action(detail=True, methods=['POST'], url_path='approve')
    def approve(self, request, pk=None):
        board = self.get_object()
        try:
            services.approve_board(board, request.user)
        except ValueError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        _log(request, board, "DESIGN_APPROVED", "Design approved",
             f"Design approved for {board.customer.first_name}.")
        return Response(self.get_serializer(board).data)

    @action(detail=True, methods=['POST'], url_path='save-to-order')
    def save_to_order(self, request, pk=None):
        board = self.get_object()
        order_ref = request.data.get('order_id')
        if not order_ref:
            return Response({'detail': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        order = get_object_or_404(Order, order_id=order_ref)
        try:
            services.save_to_order(board, order)
        except ValueError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        _log(request, board, "DESIGN_SAVED_TO_ORDER", f"Design saved to {order.order_id}",
             f"The approved design is now attached to order {order.order_id}.")
        return Response(self.get_serializer(board).data)
