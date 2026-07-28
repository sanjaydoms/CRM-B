import os
import uuid
from django.contrib.auth.models import User
from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Sum, Count

from .models import (
    Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order,
    BoutiqueFabric, BoutiqueDesign, Notification, OrderStageHistory,
    BoutiqueSettings, MeasurementHistory, OrderStage, OrderActivity
)
from .serializers import (
    CustomerSerializer, MeasurementSerializer, DesignPreferenceSerializer, 
    FabricSelectionSerializer, TailorSerializer, OrderSerializer, BoutiqueFabricSerializer,
    BoutiqueDesignSerializer, NotificationSerializer, OrderStageHistorySerializer, BoutiqueSettingsSerializer,
    MeasurementHistorySerializer, CustomerSummarySerializer, OrderSummarySerializer
)
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
        import json
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
            
        # Create DesignPreference
        pref = DesignPreference.objects.create(
            customer=customer,
            notes=notes,
            reference_images=image_urls
        )
        serializer = DesignPreferenceSerializer(pref)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['GET'], url_path='ai-suggestions')
    def ai_suggestions(self, request, pk=None):
        customer = self.get_object()
        # Filter templates that are AI suggestion templates (is_boutique=False)
        # matching the customer's garment_type
        templates = BoutiqueDesign.objects.filter(is_boutique=False, garment_type__iexact=customer.garment_type)
        if not templates.exists():
            # If no matches, fallback to any AI suggestions
            templates = BoutiqueDesign.objects.filter(is_boutique=False)
        
        serializer = BoutiqueDesignSerializer(templates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'], url_path='boutique-designs')
    def boutique_designs(self, request, pk=None):
        customer = self.get_object()
        # Filter designs that are boutique catalog designs (is_boutique=True)
        # matching the customer's garment_type
        designs = BoutiqueDesign.objects.filter(is_boutique=True, garment_type__iexact=customer.garment_type)
        
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
    queryset = BoutiqueDesign.objects.all()
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

    @action(detail=True, methods=['PATCH'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        old_status = order.order_status
        new_status = request.data.get('status')
        if new_status:
            order.order_status = new_status
            # Sync current_stage_key based on status
            reverse_status_map = {
                'Received': 'created',
                'Confirmed': 'fabric_confirmed',
                'Design & Creation': 'assigned_to_tailor',
                'Quality Check': 'stitching_completed',
                'Ready for Dispatch': 'ready_for_delivery',
                'Shipped': 'ready_for_delivery',
                'Delivered': 'delivered'
            }
            if new_status in reverse_status_map:
                order.current_stage_key = reverse_status_map[new_status]
            order.save()
            if old_status != new_status:
                create_order_notifications(order, created=False)
            return Response({'status': 'status updated', 'order_status': order.order_status})
        return Response({'error': 'no status provided'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['PATCH'], url_path='submit-completion')
    def submit_completion(self, request, pk=None):
        order = self.get_object()
        comments = request.data.get('tailor_comments')
        image = request.FILES.get('completed_garment_image')
        
        if comments is not None:
            order.tailor_comments = comments
        if image is not None:
            order.completed_garment_image = image
            
        order.order_status = 'Quality Check'
        order.current_stage_key = 'stitching_completed'
        # Also update stage status
        stitching_stage = order.stages.filter(stage_key='stitching_completed').first()
        if stitching_stage:
            from django.utils import timezone as tz
            stitching_stage.status = 'COMPLETED'
            stitching_stage.completed_at = tz.now()
            stitching_stage.save()
        order.save()
        
        create_order_notifications(order, created=False)

        # Re-read so the updated stitching stage is reflected -- see transition.
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
        total_orders = Order.objects.count()
        paid_revenue = Order.objects.filter(payment_status='Paid').aggregate(Sum('total_amount'))['total_amount__sum'] or 0.0
        partial_revenue = Order.objects.filter(payment_status='Partially Paid').aggregate(Sum('advance_paid'))['advance_paid__sum'] or 0.0
        revenue = float(paid_revenue) + float(partial_revenue)
        
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

        config.save()
        serializer = BoutiqueSettingsSerializer(config, context={'request': request})
        return Response(serializer.data)
