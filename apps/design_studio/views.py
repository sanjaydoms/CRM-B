import json
import os
import secrets
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
from core.roles import DESIGNER, OWNER, resolve_user_role
from crm_api.models import Customer, Order

from . import services
from . import context as context_module
from .context import build_context
from .intelligence.registry import get_intelligence
from apps.catalog.models import GarmentTemplate

from .models import (
    Collection, Designer, DesignApproval, DesignAsset, DesignAssignment, DesignBoard,
    DesignBoardItem, DesignImage,
)
from .permissions import (
    MASTER, DesignAssignmentPermission, DesignLibraryPermission, DesignStudioPermission,
    OwnerOnly, visible_assignments, visible_boards,
)
from .providers.registry import source_status
from .serializers import (
    DesignAssetSerializer, DesignBoardItemSerializer, DesignBoardSerializer,
    DesignerSerializer, CollectionSerializer, DesignApprovalSerializer,
    DesignAssignmentSerializer, DesignerAssignmentSerializer,
    DiscoverRequestSerializer, TailorBriefSerializer,
)


def _log(request, entity, action_name, title, description, new_value=None,
         entity_type="DesignBoard"):
    user = request.user if request.user.is_authenticated else None
    UniversalActivity.objects.create(
        user=user,
        user_name_snapshot=(user.get_full_name() or user.username) if user else "System",
        module="design_studio",
        entity_type=entity_type,
        entity_id=str(entity.id),
        action=action_name,
        title=title,
        description=description,
        new_value=new_value or {},
    )


def _resolve_subject(request, *, customer_id=None, draft_id=None, garment_key=None):
    from crm_api.models import OrderDraft

    order_input = {}
    subject = None

    if draft_id:
        draft = OrderDraft.objects.filter(
            pk=draft_id, created_by=request.user).first()
        if draft is None:
            return None, None, 'That draft does not exist, or is not yours.'
        payload = draft.payload or {}

        if draft.customer_id:
            customer = (Customer.objects.select_related('measurements')
                        .filter(pk=draft.customer_id).first())
            if customer is not None:
                subject = context_module.subject_from_customer(customer)
        if subject is None:
            subject = context_module.subject_from_draft(payload)

        garments = payload.get('garments') or []
        garment = None
        if garment_key:
            garment = next(
                (g for g in garments
                 if str(g.get('key')) == str(garment_key)
                 or str(g.get('template_key')) == str(garment_key)), None)
        elif len(garments) == 1:
            garment = garments[0]
        if garment is not None:
            order_input = {
                'garment_type': garment.get('template_key') or garment.get('key') or '',
                'spec': garment.get('spec') or garment.get('values') or {},
                'measurements': garment.get('measurements') or {},
            }
        elif garment_key:
            return None, None, f'No garment "{garment_key}" on this draft.'
        return subject, order_input, None

    if not customer_id:
        # Neither a customer nor a draft: an anonymous browse. The wizard opens
        # on the design step so a walk-in can pick a design and a fabric before
        # giving their details, and at that point there is genuinely no subject
        # -- so one is built from an empty payload rather than refusing.
        #
        # This used to be an error, which is what made the first screen of the
        # order wizard show an empty gallery: the studio fired its search, the
        # server rejected it before any provider ran, and nothing was displayed.
        # Minting an empty draft to satisfy the old rule would have worked and
        # was the wrong fix -- it litters the resume list with orders nobody
        # started, the same way creating the Customer at step one used to leave
        # clients nobody asked for.
        #
        # The garment still narrows the search: `garment_type` arrives as its
        # own parameter and is merged in by the caller.
        return context_module.subject_from_draft({}), {}, None

    customer = get_object_or_404(
        Customer.objects.select_related('measurements'), pk=customer_id)
    subject = context_module.subject_from_customer(customer)

    if garment_key:
        from apps.catalog.models import GarmentJob
        job = (GarmentJob.objects.select_related('template')
               .filter(pk=garment_key, order__customer=customer).first())
        if job is None:
            return None, None, 'No such garment on this customer\'s orders.'
        order_input = {
            'garment_type': job.template.key,
            'spec': job.spec or {},
            'measurements': job.measurements or {},
        }
    return subject, order_input, None


class DesignContextView(views.APIView):


    permission_classes = [OwnerOnly]

    def get(self, request):
        subject, order_input, error = _resolve_subject(
            request,
            customer_id=request.query_params.get('customer_id'),
            draft_id=request.query_params.get('draft_id'),
            garment_key=request.query_params.get('garment_key'))
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        order_input = dict(order_input or {})
        order_input.update({
            key: request.query_params[key]
            for key in ('garment_type', 'occasion', 'budget', 'delivery_timeline')
            if request.query_params.get(key)
        })
        context = build_context(subject, order_input)
        return Response({
            'context': context.to_dict(),
            'suggested_queries': get_intelligence().generate_queries(context),
            'sources': source_status(),
        })


class DesignDiscoveryView(views.APIView):


    permission_classes = [OwnerOnly]

    def post(self, request):
        payload = DiscoverRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        subject, order_input, error = _resolve_subject(
            request,
            customer_id=data.get('customer_id'),
            draft_id=data.get('draft_id'),
            garment_key=data.get('garment_key'))
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        order_input = dict(order_input or {})
        order_input.update({
            key: value for key, value in (
                ('garment_type', data.get('garment_type', '')),
                ('occasion', data.get('occasion', '')),
                ('budget', data.get('budget')),
                ('delivery_timeline', data.get('delivery_timeline', '')),
            ) if value not in (None, '')
        })

        import hashlib
        from django.core.cache import cache

        cache_raw = {
            'user': request.user.id,
            'customer_id': str(data.get('customer_id') or ''),
            'draft_id': str(data.get('draft_id') or ''),
            'garment_type': str(order_input.get('garment_type', '')),
            'occasion': str(order_input.get('occasion', '')),
            'budget': str(order_input.get('budget', '')),
            'garment_key': str(data.get('garment_key', '')),
            'keywords': data.get('keywords') or [],
            'sources': data.get('sources') or [],
        }
        cache_key = f"design_disc:{hashlib.md5(json.dumps(cache_raw, sort_keys=True).encode()).hexdigest()}"
        cached_response = cache.get(cache_key)
        if cached_response is not None:
            return Response(cached_response)

        outcome = services.discover(
            subject,
            order_input=order_input,
            extra_keywords=data.get('keywords'),
            sources=data.get('sources'),
            limit=data.get('limit', 40),
        )

        response_data = {
            'context': outcome['context'].to_dict(),
            'queries': outcome['queries'],
            'sources': outcome['sources'],
            'results': [candidate.to_dict() for candidate in outcome['results']],
        }
        cache.set(cache_key, response_data, timeout=300)
        return Response(response_data)


class DesignAssetViewSet(viewsets.ModelViewSet):


    serializer_class = DesignAssetSerializer
    permission_classes = [DesignLibraryPermission]

    DIRECT_FILTERS = {
        'template': 'template__key',
        'designer': 'designer_ref_id',
        'collection': 'collection_id',
        'status': 'status',
        'source': 'source',
        # "show me every pallu design" -- the reason the images are a table.
        'part': 'images__part',
    }
    
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

        for key, value in params.items():
            if key in self.DIRECT_FILTERS or key in self.RESERVED:
                continue
            queryset = queryset.filter(spec_tags__contains={key: value})

        # `part` filters across a reverse join, so a design with three pallu
        # photographs would otherwise come back three times. Only paid for when
        # that filter is actually in play.
        if params.get('part'):
            queryset = queryset.distinct()

        return queryset.order_by(self.ORDERINGS.get(params.get('ordering'), '-created_at'))

    def create(self, request, *args, **kwargs):
        data = {key: value for key, value in request.data.items() if key != 'images'}

        for name, field in self.get_serializer().fields.items():
            if isinstance(field, serializers.JSONField) and isinstance(data.get(name), str):
                try:
                    data[name] = json.loads(data[name])
                except (TypeError, ValueError):
                    pass  # leave it; the serializer reports the real error

        uploaded = self._store_images(request)
        if uploaded:
            data.setdefault('image_url', uploaded[0])
            if not data.get('image_url'):
                data['image_url'] = uploaded[0]

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        from crm_api.models import BoutiqueSettings
        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        role = resolve_user_role(request.user)
        initial_status = (
            DesignAsset.Status.ACTIVE if role == OWNER or not config.design_approval_required
            else DesignAsset.Status.PENDING
        )

        # One part key per uploaded file, in the same order the files were
        # appended. A parallel list rather than nested `images[pallu]` field
        # names: multipart has no nesting, and every parser that fakes it does
        # so differently. Missing or short, the remainder falls back to
        # 'overall', which is what an upload with no part chosen honestly is.
        parts = request.POST.getlist('image_parts')

        asset = serializer.save(
            created_by=request.user if request.user.is_authenticated else None,
            designer_ref=(serializer.validated_data.get('designer_ref')
                          or getattr(request.user, 'designer_profile', None)),
            gallery=uploaded[1:] if len(uploaded) > 1 else [],
            status=initial_status,
        )

        # Every uploaded file becomes a DesignImage filed under its part, the
        # cover shot included -- the detail view reads these, and leaving the
        # first one out would make the cover the only photograph that could not
        # be found under a part heading.
        if uploaded:
            DesignImage.objects.bulk_create([
                DesignImage(
                    design=asset,
                    part=(parts[i] if i < len(parts) and parts[i] else 'overall'),
                    image_url=url,
                    sequence=i,
                )
                for i, url in enumerate(uploaded)
            ])

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

        return Response(self.get_serializer(asset).data)

    @action(detail=True, methods=['GET'], url_path='approval-history')
    def approval_history(self, request, pk=None):
        asset = self.get_object()
        history = asset.approvals.select_related('reviewer').all()
        return Response(DesignApprovalSerializer(history, many=True).data)


class CollectionViewSet(viewsets.ModelViewSet):


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
            'trending': DesignAssetSerializer(
                active.filter(updated_at__gte=week_ago).order_by('-view_count')[:5],
                many=True).data,
        })


class GarmentPartImageView(views.APIView):
    """The photographs available for each part of one garment.

    This is what the order wizard's part tabs read. A customer picking a saree
    does not pick one saree: they pick THIS pallu and THAT border off two
    different ones, so what they browse is photographs of a part, gathered
    across every design in the library, rather than a grid of whole designs.

    Counts for every part come back on each call because the tabs show them,
    and they are one grouped query. The photographs themselves come back for
    the requested part ONLY -- the same rule the design library follows for
    categories. A boutique with five hundred sarees has four thousand part
    photographs, and no screen needs them at once.
    """

    permission_classes = [DesignStudioPermission]

    def get(self, request):
        garment_key = request.query_params.get('garment_key') or ''
        template = GarmentTemplate.resolve(garment_key) if garment_key else None

        # Only designs a customer may actually be shown. ARCHIVED is a design
        # the owner took off the table and PENDING has not been approved, so
        # neither belongs in front of a customer -- the same rule the discovery
        # providers apply, for the same reason.
        images = DesignImage.objects.filter(
            design__status=DesignAsset.Status.ACTIVE)
        if template is not None:
            images = images.filter(design__template=template)
        elif garment_key:
            # A garment with no template row yet: fall back to the free-text
            # column rather than silently showing another garment's parts.
            images = images.filter(design__garment_type__iexact=garment_key)

        counts = dict(images.values_list('part').annotate(n=Count('id')))

        # Declared order, with the template's own labels. Parts the template
        # names but nothing has been uploaded for are still listed, at zero:
        # an empty Pallu tab tells the boutique what is missing, and hiding it
        # would make the gap invisible.
        declared = (template.design_parts if template else []) or []
        parts = [{'key': p['key'], 'label': p['label'], 'count': counts.get(p['key'], 0)}
                 for p in declared]

        # Anything filed under a part the template no longer declares -- an
        # older upload, or a boutique that renamed its parts. Listed after the
        # declared ones so the photographs stay reachable.
        for key, count in counts.items():
            if not any(p['key'] == key for p in parts):
                parts.append({'key': key, 'label': key.replace('_', ' ').title(),
                              'count': count})

        def row(image):
            return {
                'id': str(image.id),
                'part': image.part,
                'image_url': image.image_url,
                'caption': image.caption,
                # The design the photograph came off. Selecting a part records
                # this, so the workroom can still see the garment the customer
                # was pointing at.
                'design_id': str(image.design_id),
                'design_title': image.design.title,
                'designer': image.design.designer_ref.name if image.design.designer_ref_id
                            else (image.design.designer or ''),
                'estimated_price': float(image.design.estimated_price or 0),
            }

        chosen = request.query_params.get('part') or (parts[0]['key'] if parts else '')
        rows = []
        if chosen:
            rows = [row(i) for i in
                    images.filter(part=chosen).select_related('design')[:120]]

        return Response({'parts': parts, 'part': chosen, 'images': rows})


class DesignCategoryView(views.APIView):

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
        untagged = DesignAsset.objects.filter(
            status=DesignAsset.Status.ACTIVE, template__isnull=True).count()
        if untagged:
            categories.append({'key': '', 'name': 'Uncategorised', 'count': untagged})

        return Response({
            'categories': categories,
            'total': sum(c['count'] for c in categories),
        })


class DesignerViewSet(viewsets.ModelViewSet):

    serializer_class = DesignerSerializer
    permission_classes = [DesignStudioPermission]

    def perform_destroy(self, instance):
        user = instance.user
        super().perform_destroy(instance)
        if user is not None and user.is_active:
            user.is_active = False
            user.save(update_fields=['is_active'])

    def get_queryset(self):
        queryset = Designer.objects.annotate(design_count=Count('designs'))

        params = self.request.query_params
        if params.get('active') == 'true':
            queryset = queryset.filter(is_active=True)
        if search := params.get('search'):
            queryset = queryset.filter(name__icontains=search)
        return queryset

    @action(detail=True, methods=['POST'], url_path='create-login')
    def create_login(self, request, pk=None):
        designer = self.get_object()
        if designer.user_id:
            return Response(
                {'detail': f'{designer.name} already has a login.'},
                status=status.HTTP_400_BAD_REQUEST)

        email = (request.data.get('email') or designer.email or '').strip().lower()
        if not email:
            return Response({'email': 'An email address is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        bootstrap = None

        if user is not None:
            from django.db import connection
            tenant_owner = (getattr(connection.tenant, 'owner_email', '') or '').lower()
            if tenant_owner and (user.email or '').lower() == tenant_owner:
                return Response(
                    {'email': 'That address belongs to the boutique owner. '
                              'Use a separate address for this designer.'},
                    status=status.HTTP_400_BAD_REQUEST)
            if getattr(user, 'tailor_profile', None) is not None:
                return Response(
                    {'email': f'That address already belongs to {user.tailor_profile.name} '
                              f'({user.tailor_profile.role}). Use a separate address.'},
                    status=status.HTTP_400_BAD_REQUEST)

        if user is None:
            username = email.split('@')[0].lower()
            original, counter = username, 1
            while User.objects.filter(username=username).exists():
                username = f"{original}{counter}"
                counter += 1
            bootstrap = secrets.token_urlsafe(9)
            user = User.objects.create_user(
                username=username, email=email,
                password=bootstrap,
                first_name=designer.name,
            )

        designer.user = user
        designer.email = email
        designer.save(update_fields=['user', 'email', 'updated_at'])

        data = DesignerSerializer(
            Designer.objects.annotate(design_count=Count('designs')).get(pk=designer.pk)
        ).data
        if bootstrap:
            data['bootstrap_password'] = bootstrap
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'])
    def portfolio(self, request, pk=None):
        designer = self.get_object()
        designs = designer.designs.all().order_by('-created_at')
        totals = designs.aggregate(
            views=Sum('view_count'), orders=Sum('order_count'))
        return Response({
            'designer': DesignerSerializer(
                Designer.objects.annotate(design_count=Count('designs')).get(pk=designer.pk),
                context=self.get_serializer_context(),
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

        from core.permissions import visible_orders
        from crm_api.models import Order
        if resolve_user_role(self.request.user) != OWNER:
            queryset = queryset.filter(
                Q(order__isnull=True)
                | Q(order__in=visible_orders(Order.objects.all(), self.request.user)))
        return visible_boards(queryset, self.request.user)

    def get_serializer_class(self):
        if (getattr(self.request.user, 'tailor_profile', None) is not None
                and resolve_user_role(self.request.user) != OWNER):
            return TailorBriefSerializer
        return DesignBoardSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    @action(detail=True, methods=['POST'], url_path='items')
    def add_item(self, request, pk=None):

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


class DesignAssignmentViewSet(viewsets.ModelViewSet):

    permission_classes = [DesignAssignmentPermission]

    def get_queryset(self):
        queryset = (DesignAssignment.objects
                    .select_related('designer', 'design', 'garment_job',
                                    'garment_job__template', 'garment_job__order',
                                    'garment_job__order__customer'))
        queryset = visible_assignments(queryset, self.request.user)

        if self.request.query_params.get('open') in ('1', 'true', 'True'):
            queryset = queryset.filter(status__in=DesignAssignment.OPEN_STATUSES)
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        designer_id = self.request.query_params.get('designer_id')
        if designer_id:
            queryset = queryset.filter(designer_id=designer_id)
        order_id = self.request.query_params.get('order_id')
        if order_id:
            queryset = queryset.filter(garment_job__order__order_id=order_id)
        return queryset

    def get_serializer_class(self):
        if resolve_user_role(self.request.user) == DESIGNER:
            return DesignerAssignmentSerializer
        return DesignAssignmentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.validated_data['garment_job']
        designer = serializer.validated_data['designer']

        existing = DesignAssignment.objects.filter(garment_job=job).first()
        if existing is not None:
            if existing.status == DesignAssignment.Status.APPROVED:
                return Response(
                    {'detail': "This garment's design is already approved. "
                               "Request changes on it before reassigning."},
                    status=status.HTTP_409_CONFLICT)
            previous = existing.designer
            existing.designer = designer
            existing.brief = serializer.validated_data.get('brief', existing.brief)
            existing.due_date = serializer.validated_data.get('due_date', existing.due_date)
            existing.status = DesignAssignment.Status.ASSIGNED
            existing.design = None
            existing.submission_note = ''
            existing.assigned_by = request.user if request.user.is_authenticated else None
            existing.save()
            _log(request, existing, "DESIGN_REASSIGNED",
                 f"Design work reassigned: {job.template.name}",
                 f"{job.template.name} on {job.order.order_id} moved from "
                 f"{previous.name} to {designer.name}.",
                 {"garment_job": str(job.id), "from": previous.name, "to": designer.name},
                 entity_type="DesignAssignment")
            return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)

        assignment = serializer.save(
            assigned_by=request.user if request.user.is_authenticated else None)
        _log(request, assignment, "DESIGN_ASSIGNED",
             f"Design work assigned: {job.template.name}",
             f"{job.template.name} on {job.order.order_id} assigned to {designer.name}.",
             {"garment_job": str(job.id), "designer": designer.name,
              "due_date": str(assignment.due_date or '')},
             entity_type="DesignAssignment")
        return Response(self.get_serializer(assignment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['POST'])
    def submit(self, request, pk=None):
        assignment = self.get_object()
        role = resolve_user_role(request.user)
        if role == DESIGNER:
            profile = getattr(request.user, 'designer_profile', None)
            if profile is None or assignment.designer_id != profile.id:
                return Response({'detail': 'This assignment is not yours to submit.'},
                                status=status.HTTP_403_FORBIDDEN)
        if assignment.status == DesignAssignment.Status.APPROVED:
            return Response({'detail': 'This design has already been approved.'},
                            status=status.HTTP_409_CONFLICT)

        design_id = request.data.get('design')
        if not design_id:
            return Response({'detail': 'A design is required to submit.'},
                            status=status.HTTP_400_BAD_REQUEST)
        design = DesignAsset.objects.filter(pk=design_id).first()
        if design is None:
            return Response({'detail': 'That design does not exist.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if role == DESIGNER and not (
                design.created_by_id == request.user.id
                or design.designer_ref_id == assignment.designer_id):
            return Response(
                {'detail': 'You can only submit a design you uploaded or are credited on.'},
                status=status.HTTP_403_FORBIDDEN)

        assignment.design = design
        assignment.submission_note = request.data.get('note', '')
        assignment.status = DesignAssignment.Status.SUBMITTED
        assignment.submitted_at = timezone.now()
        assignment.save()
        if design.designer_ref_id is None:
            design.designer_ref_id = assignment.designer_id
            design.save(update_fields=['designer_ref'])

        job = assignment.garment_job
        _log(request, assignment, "DESIGN_SUBMITTED",
             f"Design submitted: {job.template.name}",
             f"{assignment.designer.name} submitted \"{design.title}\" for "
             f"{job.template.name} on {job.order.order_id}.",
             {"garment_job": str(job.id), "design": str(design.id), "title": design.title},
             entity_type="DesignAssignment")
        return Response(self.get_serializer(assignment).data)

    @action(detail=True, methods=['POST'])
    def review(self, request, pk=None):

        assignment = self.get_object()
        if assignment.design_id is None:
            return Response({'detail': 'There is no submitted design to review.'},
                            status=status.HTTP_400_BAD_REQUEST)

        decision = (request.data.get('decision') or '').upper()
        if decision not in ('APPROVE', 'CHANGES'):
            return Response({'detail': "decision must be 'approve' or 'changes'."},
                            status=status.HTTP_400_BAD_REQUEST)

        assignment.status = (DesignAssignment.Status.APPROVED if decision == 'APPROVE'
                             else DesignAssignment.Status.CHANGES_REQUESTED)
        assignment.review_note = request.data.get('note', '')
        assignment.reviewed_by = request.user if request.user.is_authenticated else None
        assignment.reviewed_at = timezone.now()
        assignment.save()

        job = assignment.garment_job
        approved = assignment.status == DesignAssignment.Status.APPROVED
        _log(request, assignment,
             "DESIGN_APPROVED" if approved else "DESIGN_CHANGES_REQUESTED",
             f"Design {'approved' if approved else 'sent back'}: {job.template.name}",
             f"{assignment.design.title} for {job.template.name} on "
             f"{job.order.order_id} was "
             f"{'approved' if approved else 'returned for changes'}.",
             {"garment_job": str(job.id), "design": str(assignment.design_id),
              "note": assignment.review_note},
             entity_type="DesignAssignment")
        return Response(self.get_serializer(assignment).data)
