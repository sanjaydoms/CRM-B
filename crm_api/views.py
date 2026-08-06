import json
import os
import uuid
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q, Sum, Count

from .models import (
    Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order,
    BoutiqueFabric, BoutiqueDesign, Notification, OrderStageHistory,
    BoutiqueSettings, MeasurementHistory, OrderStage, OrderActivity
)
from .serializers import (
    CustomerSerializer, MeasurementSerializer, DesignPreferenceSerializer, 
    FabricSelectionSerializer, TailorSerializer, OrderSerializer, BoutiqueFabricSerializer,
    BoutiqueDesignSerializer, NotificationSerializer, OrderStageHistorySerializer, BoutiqueSettingsSerializer,
    MeasurementHistorySerializer, CustomerSummarySerializer, OrderSummarySerializer,
    OrderStageSerializer
)
from apps.design_studio.models import DesignAsset
from domains.customers.repositories import CustomerRepository
from domains.orders.notifications import create_order_notifications
from domains.orders.repositories import OrderRepository
from domains.orders.services import OrderService

class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer

    def get_serializer_class(self):
        # The directory list gets flat rows; nesting every client's full order
        # tree there made the payload ~119KB for 25 clients. Opening a client
        # hits retrieve, which still returns orders and history in full.
        if self.action == 'list':
            return CustomerSummarySerializer
        return CustomerSerializer

    def get_queryset(self):
        if self.action == 'list':
            return CustomerRepository.summary_queryset()
        return CustomerRepository.get_all()

    @action(detail=True, methods=['GET'], url_path='measurement-history')
    def measurement_history(self, request, pk=None):
        customer = self.get_object()
        history = customer.measurement_history.all().order_by('-changed_at')
        serializer = MeasurementHistorySerializer(history, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='design-preferences')
    def save_design_preferences(self, request, pk=None):
        customer = self.get_object()
        notes = request.data.get('notes', '')
        
        # Handle existing selected URLs
        selected_urls = request.data.get('selected_urls', '[]')
        try:
            image_urls = json.loads(selected_urls)
        except Exception:
            image_urls = []
            
        # Handle reference image uploads
        files = request.FILES.getlist('images')
        for f in files:
            path = f"design_references/cust_{customer.id}/{uuid.uuid4()}_{f.name}"
            saved_path = default_storage.save(path, ContentFile(f.read()))
            image_urls.append(request.build_absolute_uri(default_storage.url(saved_path)))
            
        # Where the design came from, and any external inspiration links.
        source = request.data.get('source') or 'BOUTIQUE_CATALOG'
        valid_sources = {c[0] for c in DesignPreference.SOURCE_CHOICES}
        if source not in valid_sources:
            return Response(
                {'error': f"Unknown design source '{source}'.",
                 'allowed': sorted(valid_sources)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            reference_links = json.loads(request.data.get('reference_links', '[]'))
        except Exception:
            reference_links = []
        if not isinstance(reference_links, list):
            reference_links = []

        # Create DesignPreference
        pref = DesignPreference.objects.create(
            customer=customer,
            notes=notes,
            reference_images=image_urls,
            source=source,
            reference_links=reference_links,
        )
        serializer = DesignPreferenceSerializer(pref)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['POST'], url_path='design-preferences/(?P<pref_id>[^/.]+)/approve')
    def approve_design(self, request, pk=None, pref_id=None):
        """Sign off one design for production.

        Only one design per client may be approved at a time -- approving a new one
        supersedes the last, so the production checklist has a single answer.
        """
        customer = self.get_object()
        pref = customer.design_preferences.filter(id=pref_id).first()
        if not pref:
            return Response({'error': 'Design preference not found for this customer.'},
                            status=status.HTTP_404_NOT_FOUND)

        approved_image = request.data.get('approved_image')
        if approved_image and approved_image not in (pref.reference_images or []):
            return Response(
                {'error': 'approved_image must be one of this design\'s reference images.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer.design_preferences.exclude(id=pref.id).filter(is_approved=True).update(
            is_approved=False, approved_at=None
        )
        pref.is_approved = True
        pref.approved_at = timezone.now()
        if approved_image:
            pref.approved_image = approved_image
        elif not pref.approved_image and pref.reference_images:
            pref.approved_image = pref.reference_images[0]
        pref.save()

        return Response(DesignPreferenceSerializer(pref).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'], url_path='ai-suggestions')
    def ai_suggestions(self, request, pk=None):
        customer = self.get_object()
        # Filter templates that are AI suggestion templates (is_boutique=False)
        # matching the customer's garment_type
        templates = DesignAsset.objects.filter(
            source=DesignAsset.SOURCE_SUGGESTION, garment_type__iexact=customer.garment_type)
        if not templates.exists():
            # If no matches, fallback to any AI suggestions
            templates = DesignAsset.objects.filter(source=DesignAsset.SOURCE_SUGGESTION)
        
        serializer = BoutiqueDesignSerializer(templates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'], url_path='boutique-designs')
    def boutique_designs(self, request, pk=None):
        customer = self.get_object()
        # Filter designs that are boutique catalog designs (is_boutique=True)
        # matching the customer's garment_type
        designs = DesignAsset.objects.filter(
            source=DesignAsset.SOURCE_CATALOGUE, garment_type__iexact=customer.garment_type)
        
        serializer = BoutiqueDesignSerializer(designs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='fabric-selections')
    def save_fabric_selection(self, request, pk=None):
        customer = self.get_object()
        is_boutique_fabric = request.data.get('is_boutique_fabric', 'true').lower() == 'true'
        fabric_name = request.data.get('fabric_name', '')
        try:
            fabric_price = float(request.data.get('fabric_price', 0.0))
        except (ValueError, TypeError):
            fabric_price = 0.0

        # Handle fabric image uploads
        image_urls = []
        files = request.FILES.getlist('images')
        for f in files:
            path = f"fabrics/cust_{customer.id}/{uuid.uuid4()}_{f.name}"
            saved_path = default_storage.save(path, ContentFile(f.read()))
            image_urls.append(request.build_absolute_uri(default_storage.url(saved_path)))

        # Create FabricSelection
        selection = FabricSelection.objects.create(
            customer=customer,
            is_boutique_fabric=is_boutique_fabric,
            fabric_name=fabric_name,
            fabric_price=fabric_price,
            uploaded_fabric_images=image_urls
        )
        serializer = FabricSelectionSerializer(selection)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['POST'], url_path='create-order')
    def create_order(self, request, pk=None):
        customer = self.get_object()
        order = OrderService.create_order_for_customer(customer, request.data, user=request.user)
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class TailorViewSet(viewsets.ModelViewSet):
    queryset = Tailor.objects.all().order_by('-rating')
    serializer_class = TailorSerializer

    def perform_create(self, serializer):
        tailor = serializer.save()
        self._ensure_user_account(tailor)

    def perform_update(self, serializer):
        tailor = serializer.save()
        self._ensure_user_account(tailor)

    def _ensure_user_account(self, tailor):
        if tailor.email:
            # Check if user already exists
            user = User.objects.filter(email=tailor.email).first()
            if not user:
                # Create user
                username = tailor.email.split('@')[0]
                # Ensure username is unique
                original_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{original_username}{counter}"
                    counter += 1
                
                # Shared bootstrap password for staff accounts. Override with
                # TAILOR_DEFAULT_PASSWORD; every tailor otherwise shares one
                # credential that is visible in this repository.
                user = User.objects.create_user(
                    username=username,
                    email=tailor.email,
                    password=os.environ.get('TAILOR_DEFAULT_PASSWORD', 'TailorSecure2026!'),
                    first_name=tailor.name
                )
            # Link to tailor
            if tailor.user != user:
                tailor.user = user
                tailor.save()

class BoutiqueFabricViewSet(viewsets.ModelViewSet):
    queryset = BoutiqueFabric.objects.all()
    serializer_class = BoutiqueFabricSerializer

class BoutiqueDesignViewSet(viewsets.ModelViewSet):
    # The catalogue lives in the design library now; the URL and the wire format
    # are unchanged, so the Manage Designs screen did not have to move with it.
    queryset = DesignAsset.objects.filter(
        source__in=[DesignAsset.SOURCE_CATALOGUE, DesignAsset.SOURCE_SUGGESTION])
    serializer_class = BoutiqueDesignSerializer

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        return OrderRepository.get_all()

    def perform_update(self, serializer):
        old_status = serializer.instance.order_status
        order = serializer.save()
        if order.payment_status == 'Paid':
            order.amount_paid = order.total_amount
            order.save(update_fields=['amount_paid'])
        elif order.payment_status == 'Pending':
            order.amount_paid = 0.00
            order.save(update_fields=['amount_paid'])

        if old_status != order.order_status:
            create_order_notifications(order, created=False)

    # A client-facing status corresponds to completing a specific stage. Statuses
    # absent here (e.g. Stylist Review) carry no stage meaning.
    STATUS_TO_STAGE = {
        'Received': 'created',
        'Confirmed': 'fabric_confirmed',
        'Design & Creation': 'assigned_to_tailor',
        'Quality Check': 'stitching_completed',
        'Ready for Dispatch': 'ready_for_delivery',
        'Shipped': 'ready_for_delivery',
        'Delivered': 'delivered',
    }

    @action(detail=True, methods=['PATCH'], url_path='update-status')
    def update_status(self, request, pk=None):
        """Advance an order by naming its client-facing status.

        This used to write order_status directly, with no role check and no
        sequencing guard, which let anyone mark a garment Delivered while the
        quality check had never been started -- the client was told the piece
        had shipped while the production record showed nothing done. It now goes
        through the same workflow engine as the stage tracker, so both routes
        enforce one set of rules and the stage rows stay in step.
        """
        order = self.get_object()
        new_status = request.data.get('status')
        if not new_status:
            return Response({'error': 'no status provided'}, status=status.HTTP_400_BAD_REQUEST)

        stage_key = self.STATUS_TO_STAGE.get(new_status)
        if not stage_key:
            # No stage maps to this status; record it without touching the workflow.
            if order.order_status != new_status:
                order.order_status = new_status
                order.save(update_fields=['order_status'])
                create_order_notifications(order, created=False)
            return Response({'status': 'status updated', 'order_status': order.order_status})

        try:
            updated = OrderService.transition_order_stage(
                order=order,
                stage_key=stage_key,
                new_status='COMPLETED',
                user=request.user,
            )
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': 'status updated', 'order_status': updated.order_status})

    @action(detail=True, methods=['PATCH'], url_path='submit-completion')
    def submit_completion(self, request, pk=None):
        order = self.get_object()
        comments = request.data.get('tailor_comments')
        image = request.FILES.get('completed_garment_image')
        
        if comments is not None:
            order.tailor_comments = comments
        if image is not None:
            order.completed_garment_image = image
        order.save()

        # Completing stitching goes through the workflow engine rather than
        # writing the stage row by hand, so the role check, the timing fields
        # and the derived order status all behave as they do everywhere else.
        try:
            OrderService.transition_order_stage(
                order=order,
                stage_key='stitching_completed',
                new_status='COMPLETED',
                comments=comments or '',
                user=request.user,
            )
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = OrderSerializer(OrderRepository.get_by_id(order.pk))
        return Response(serializer.data)

    @action(detail=True, methods=['POST'], url_path='submit-stage-review')
    def submit_stage_review(self, request, pk=None):
        order = self.get_object()
        stage = request.data.get('stage')
        comments = request.data.get('comments')
        image = request.FILES.get('image')
        completed_by = request.data.get('completed_by', 'Boutique Staff')
        
        if not stage:
            return Response({'error': 'stage is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Delete duplicate history for same stage if any exists
        OrderStageHistory.objects.filter(order=order, stage=stage).delete()
        
        history = OrderStageHistory.objects.create(
            order=order,
            stage=stage,
            comments=comments,
            image=image,
            completed_by_name=completed_by
        )
        
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['POST'], url_path='assign-stage')
    def assign_stage(self, request, pk=None):
        """Nominate who should perform a stage, ahead of the work starting.

        Distinct from performed_by, which records who actually did it. Refuses a
        staff member whose role the stage does not permit, so the assignment cannot
        contradict the transition rules.
        """
        order = self.get_object()
        stage_key = request.data.get('stage_key')
        tailor_id = request.data.get('tailor_id')

        if not stage_key:
            return Response({'error': 'stage_key is required'}, status=status.HTTP_400_BAD_REQUEST)

        stage = order.stages.filter(stage_key=stage_key).first()
        if not stage:
            return Response({'error': f"Unknown stage '{stage_key}' for this order."},
                            status=status.HTTP_404_NOT_FOUND)

        # Passing no tailor_id clears the assignment.
        if tailor_id in (None, '', 'null'):
            stage.assigned_to = None
            stage.save(update_fields=['assigned_to'])
            return Response(OrderStageSerializer(stage).data, status=status.HTTP_200_OK)

        tailor = Tailor.objects.filter(id=tailor_id).first()
        if not tailor:
            return Response({'error': 'Staff member not found.'}, status=status.HTTP_404_NOT_FOUND)

        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        stage_conf = next((s for s in config.workflow_config if s['key'] == stage_key), {})
        allowed_roles = stage_conf.get('roles', [])
        if allowed_roles and tailor.role not in allowed_roles:
            return Response(
                {'error': f"{tailor.name} is a {tailor.role} and cannot be assigned to {stage.stage_name}.",
                 'allowed_roles': allowed_roles},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stage.assigned_to = tailor
        stage.save(update_fields=['assigned_to'])
        return Response(OrderStageSerializer(stage).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='transition')
    def transition_stage(self, request, pk=None):
        order = self.get_object()
        stage_key = request.data.get('stage_key')
        new_status = request.data.get('status')
        comments = request.data.get('comments', '')
        performer_id = request.data.get('performed_by_id')

        if not stage_key or not new_status:
            return Response({'error': 'stage_key and status are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_order = OrderService.transition_order_stage(
                order=order,
                stage_key=stage_key,
                new_status=new_status,
                comments=comments,
                performer_id=performer_id,
                user=request.user,
                files=request.FILES.getlist('images'),
                request=request
            )
            # Re-read: `order` was loaded with its stages prefetched, so the
            # cache still holds the pre-transition rows and would serialise the
            # stage as unchanged even though the write succeeded.
            serializer = OrderSerializer(OrderRepository.get_by_id(updated_order.pk))
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by('-created_at')
    serializer_class = NotificationSerializer

    def get_queryset(self):
        role = self.request.query_params.get('role', 'Owner')
        email = self.request.query_params.get('email', None)
        qs = Notification.objects.all()
        if role == 'Owner':
            return qs.filter(recipient_role='Owner').order_by('-created_at')
        elif role in ['Master', 'Tailor']:
            if email:
                return qs.filter(recipient_role=role, recipient_email=email).order_by('-created_at')
            return qs.filter(recipient_role=role).order_by('-created_at')
        return qs.order_by('-created_at')

    @action(detail=False, methods=['POST'], url_path='mark-all-read')
    def mark_all_read(self, request):
        role = request.query_params.get('role', 'Owner')
        email = request.query_params.get('email', None)
        qs = Notification.objects.filter(is_read=False)
        if role == 'Owner':
            qs.filter(recipient_role='Owner').update(is_read=True)
        elif role in ['Master', 'Tailor']:
            if email:
                qs.filter(recipient_role=role, recipient_email=email).update(is_read=True)
            else:
                qs.filter(recipient_role=role).update(is_read=True)
        return Response({'status': 'marked as read'})

class DashboardView(views.APIView):
    def get(self, request):
        total_customers = Customer.objects.count()

        # The order count and both revenue figures used to be three separate
        # queries that each scanned the same table, and the dashboard is the
        # first thing every session loads. Conditional aggregation asks for all
        # three in one pass, which matters far more than the scan itself when
        # the database is a network hop away: three round trips become one.
        order_totals = Order.objects.aggregate(
            total=Count('id'),
            paid=Sum('total_amount', filter=Q(payment_status='Paid')),
            partial=Sum('advance_paid', filter=Q(payment_status='Partially Paid')),
        )
        total_orders = order_totals['total']
        revenue = float(order_totals['paid'] or 0.0) + float(order_totals['partial'] or 0.0)

        status_counts = Order.objects.values('order_status').annotate(count=Count('id'))

        # Recent orders. The dashboard renders the stage tracker but never the
        # activity log or stage histories, so those stay out of the payload.
        recent_orders = OrderRepository.summary_queryset()[:5]
        recent_orders_data = OrderSummarySerializer(recent_orders, many=True, context={'request': request}).data

        # Recent customers, as flat summary rows -- the dashboard shows name, type
        # and spend, not each client's full order history.
        recent_customers = CustomerRepository.summary_queryset()[:5]
        recent_customers_data = CustomerSummarySerializer(recent_customers, many=True, context={'request': request}).data

        return Response({
            'stats': {
                'total_customers': total_customers,
                'total_orders': total_orders,
                'revenue': revenue,
                'status_distribution': {item['order_status']: item['count'] for item in status_counts}
            },
            'recent_orders': recent_orders_data,
            'recent_customers': recent_customers_data
        })

class BoutiqueSettingsViewSet(viewsets.ViewSet):
    def list(self, request):
        config, created = BoutiqueSettings.objects.get_or_create(id=1)
        serializer = BoutiqueSettingsSerializer(config, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        config, created = BoutiqueSettings.objects.get_or_create(id=1)
        name = request.data.get('name')
        address = request.data.get('address')
        phone = request.data.get('phone')
        email = request.data.get('email')
        logo = request.FILES.get('logo')

        if name is not None:
            config.name = name
        if address is not None:
            config.address = address
        if phone is not None:
            config.phone = phone
        if email is not None:
            config.email = email
        if logo is not None:
            config.logo = logo
        if 'design_approval_required' in request.data:
            config.design_approval_required = str(
                request.data.get('design_approval_required')).lower() in ('true', '1')

        config.save()
        serializer = BoutiqueSettingsSerializer(config, context={'request': request})
        return Response(serializer.data)
