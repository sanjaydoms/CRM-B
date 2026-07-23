import uuid
import datetime
import random
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
    MeasurementHistorySerializer
)

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.prefetch_related(
        'orders', 'orders__stages', 'orders__activities', 'orders__tailor', 'orders__master',
        'measurement_history', 'design_preferences', 'fabric_selections'
    ).all().order_by('-created_at')
    serializer_class = CustomerSerializer

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
        from domains.orders.services import OrderService
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
                
                user = User.objects.create_user(
                    username=username,
                    email=tailor.email,
                    password="TailorSecure2026!",
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

def create_order_notifications(order, created=False):
    client_name = f"{order.customer.first_name} {order.customer.last_name}"
    client_email = order.customer.email_address
    
    if created:
        Notification.objects.create(
            title=f"New Order Received: {order.order_id}",
            message=f"A new custom order has been received for client {client_name}.",
            recipient_role="Owner"
        )
        Notification.objects.create(
            title=f"Order Confirmed: {order.order_id}",
            message=f"Dear {order.customer.first_name}, we have received your order {order.order_id}! We will update you as it progresses.",
            recipient_role="Customer",
            recipient_email=client_email
        )
        if order.master:
            Notification.objects.create(
                title=f"New Assignment: {order.order_id}",
                message=f"Order {order.order_id} for client {client_name} has been assigned to you as Supervising Master.",
                recipient_role="Master",
                recipient_email=order.master.user.email if order.master.user else None
            )
        if order.tailor:
            Notification.objects.create(
                title=f"New Stitching Task: {order.order_id}",
                message=f"Order {order.order_id} has been assigned to you for stitching.",
                recipient_role="Tailor",
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )
    else:
        status = order.order_status
        Notification.objects.create(
            title=f"Order {order.order_id} Update: {status}",
            message=f"Order {order.order_id} status updated to {status}.",
            recipient_role="Owner"
        )
        
        cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} status has been updated to: {status}."
        if status == 'Design & Creation':
            cust_msg = f"Dear {order.customer.first_name}, your garment for order {order.order_id} is now in the Design & Creation phase. Our master tailors are crafting it!"
        elif status == 'Ready for Dispatch':
            cust_msg = f"Dear {order.customer.first_name}, your garment for order {order.order_id} has passed quality checks and is Ready for Dispatch!"
        elif status == 'Shipped':
            if order.delivery_method == 'Courier':
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been Shipped via {order.courier_service or 'Courier'}! Tracking Number: {order.tracking_number or 'TBD'}."
            else:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been dispatched for direct pickup!"
        elif status == 'Delivered':
            balance = float(order.total_amount) - float(order.amount_paid or 0)
            if balance > 0:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered! Please complete your remaining balance of ₹{balance:.2f}."
            else:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered. We hope you love your bespoke garment!"

        Notification.objects.create(
            title=f"Order Update: {status}",
            message=cust_msg,
            recipient_role="Customer",
            recipient_email=client_email
        )

        if status == 'Design & Creation' and order.tailor:
            Notification.objects.create(
                title=f"Stitching Ready: {order.order_id}",
                message=f"Order {order.order_id} is now in Design & Creation phase and ready for stitching.",
                recipient_role="Tailor",
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )

        if status == 'Quality Check':
            # Notify Owner
            Notification.objects.create(
                title=f"Garment Stitching Completed: {order.order_id}",
                message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is now pending Quality Check.",
                recipient_role="Owner"
            )
            # Notify Master
            if order.master:
                Notification.objects.create(
                    title=f"Quality Check Required: {order.order_id}",
                    message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is ready for your Quality Check.",
                    recipient_role="Master",
                    recipient_email=order.master.user.email if order.master.user else None
                )

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related(
        'customer', 'tailor', 'master', 'customer__measurements'
    ).prefetch_related(
        'stages', 'stages__performed_by', 'activities', 'activities__user'
    ).all().order_by('-order_date')
    serializer_class = OrderSerializer

    def perform_update(self, serializer):
        old_status = self.get_object().order_status
        order = serializer.save()
        if order.payment_status == 'Paid':
            order.amount_paid = order.total_amount
        elif order.payment_status == 'Pending':
            order.amount_paid = 0.00
        order.save()

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
        
        serializer = OrderSerializer(order)
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
        new_status = request.data.get('status') # NOT_STARTED, IN_PROGRESS, COMPLETED, PAUSED, SKIPPED
        comments = request.data.get('comments', '')
        performer_id = request.data.get('performed_by_id')
        
        if not stage_key or not new_status:
            return Response({'error': 'stage_key and status are required'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Get matching OrderStage
        try:
            order_stage = order.stages.get(stage_key=stage_key)
        except OrderStage.DoesNotExist:
            return Response({'error': f'Stage {stage_key} does not exist for this order'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Fetch configurations (e.g. roles)
        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        workflow_stages = config.workflow_config
        stage_conf = next((s for s in workflow_stages if s['key'] == stage_key), {})
        
        # 1. Permission checks
        user = request.user
        user_role = 'Owner' # Default fallback
        if user.is_authenticated and not user.is_superuser:
            # Check Tailor profile role
            tailor_profile = getattr(user, 'tailor_profile', None)
            if tailor_profile:
                user_role = tailor_profile.role # 'Master' or 'Tailor'
            else:
                user_role = 'Staff'
        elif not user.is_authenticated:
            user_role = 'Staff'
                
        allowed_roles = stage_conf.get('roles', [])
        if allowed_roles and user_role not in allowed_roles and not user.is_superuser and user_role != 'Owner':
            return Response({'error': f'Role {user_role} is not authorized to update {order_stage.stage_name}'}, status=status.HTTP_403_FORBIDDEN)
            
        # 2. Validation & Blocking Rules
        # Rule A: Cannot Deliver (delivered) before quality check (master_quality_check is completed)
        if stage_key == 'delivered' and new_status == 'COMPLETED':
            qc_stage = order.stages.filter(stage_key='master_quality_check').first()
            if qc_stage and qc_stage.status != 'COMPLETED':
                return Response({'error': 'Cannot deliver order before Master Quality Check is completed.'}, status=status.HTTP_400_BAD_REQUEST)
                
        # Rule B: Cannot start stitching (stitching_in_progress) before Tailor is assigned
        if stage_key == 'stitching_in_progress' and new_status == 'IN_PROGRESS':
            if not order.tailor:
                return Response({'error': 'Cannot start stitching. No tailor is assigned to this order.'}, status=status.HTTP_400_BAD_REQUEST)
                
        # Rule C: Cannot assign tailor (assigned_to_tailor) without measurements
        if stage_key == 'assigned_to_tailor' and new_status == 'COMPLETED':
            meas_stage = order.stages.filter(stage_key='measurements_completed').first()
            if meas_stage and meas_stage.status != 'COMPLETED':
                # Double check customer model directly
                has_measurements = hasattr(order.customer, 'measurements') and (
                    order.customer.measurements.bust or order.customer.measurements.waist or order.customer.measurements.hips
                )
                if not has_measurements:
                    return Response({'error': 'Cannot assign tailor. Measurements are not completed for this customer.'}, status=status.HTTP_400_BAD_REQUEST)
                    
        # Rule D: Cannot schedule trial (trial_scheduled) before stitching is completed
        if stage_key == 'trial_scheduled' and new_status == 'COMPLETED':
            stitch_stage = order.stages.filter(stage_key='stitching_completed').first()
            if stitch_stage and stitch_stage.status != 'COMPLETED':
                return Response({'error': 'Cannot schedule trial before stitching is completed.'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Apply state transitions
        from django.utils import timezone
        old_status = order_stage.status
        order_stage.status = new_status
        order_stage.comments = comments
        
        if performer_id:
            try:
                order_stage.performed_by = Tailor.objects.get(id=performer_id)
            except Tailor.DoesNotExist:
                pass
        elif user.is_authenticated and user_role in ['Master', 'Tailor']:
            # Auto-assign if the logged-in user has a tailor profile
            order_stage.performed_by = getattr(user, 'tailor_profile', None)
            
        # Time and duration tracking
        if new_status == 'IN_PROGRESS' and old_status != 'IN_PROGRESS':
            order_stage.started_at = timezone.now()
        elif new_status == 'COMPLETED' and old_status != 'COMPLETED':
            if not order_stage.started_at:
                order_stage.started_at = timezone.now()
            order_stage.completed_at = timezone.now()
            # Calculate duration in seconds
            delta = order_stage.completed_at - order_stage.started_at
            order_stage.duration_seconds = int(delta.total_seconds())
            
        # Handle images upload for the stage
        files = request.FILES.getlist('images')
        image_urls = list(order_stage.attachments)
        for f in files:
            path = f"stage_attachments/order_{order.id}/{uuid.uuid4()}_{f.name}"
            saved_path = default_storage.save(path, ContentFile(f.read()))
            image_urls.append(request.build_absolute_uri(default_storage.url(saved_path)))
        order_stage.attachments = image_urls
        
        order_stage.save()
        
        # Update order current stage and status
        order.current_stage_key = stage_key
        # Compute overall production status from all stages
        all_stages = list(order.stages.all())
        if all(s.status == 'COMPLETED' for s in all_stages):
            order.production_status = 'COMPLETED'
        elif any(s.status == 'IN_PROGRESS' for s in all_stages):
            order.production_status = 'IN_PROGRESS'
        else:
            order.production_status = 'IN_PROGRESS'  # Default to in progress when any stage is being worked on
        
        # Map back to order.order_status for legacy compatibility
        status_map = {
            'created': 'Received',
            'measurements_completed': 'Confirmed',
            'fabric_confirmed': 'Confirmed',
            'pattern_cutting': 'Design & Creation',
            'assigned_to_tailor': 'Design & Creation',
            'stitching_in_progress': 'Design & Creation',
            'stitching_completed': 'Quality Check',
            'master_quality_check': 'Ready for Dispatch' if new_status == 'COMPLETED' else 'Quality Check',
            'trial_scheduled': 'Ready for Dispatch',
            'trial_completed': 'Ready for Dispatch',
            'ready_for_delivery': 'Ready for Dispatch',
            'delivered': 'Delivered'
        }
        if stage_key in status_map:
            order.order_status = status_map[stage_key]
        order.save()
        
        # Log to OrderActivity
        creator = user if user.is_authenticated else None
        OrderActivity.objects.create(
            order=order,
            event_type='STAGE_TRANSITION',
            user=creator,
            metadata={
                "stage_key": stage_key,
                "stage_name": order_stage.stage_name,
                "old_status": old_status,
                "new_status": new_status,
                "comments": comments
            }
        )
        
        # Sync tailor statuses
        if stage_key == 'stitching_in_progress' and new_status == 'IN_PROGRESS' and order.tailor:
            order.tailor.status = 'Busy'
            order.tailor.save()
        elif stage_key == 'stitching_completed' and new_status == 'COMPLETED' and order.tailor:
            order.tailor.status = 'Available'
            order.tailor.save()
            
        if stage_key == 'delivered' and new_status == 'COMPLETED' and order.master:
            order.master.status = 'Available'
            order.master.save()
            
        # Trigger notifications
        create_order_notifications(order, created=False)
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
        
        # Recent orders with customer and tailor detail
        recent_orders = Order.objects.select_related(
            'customer', 'tailor', 'master', 'customer__measurements'
        ).prefetch_related(
            'stages', 'stages__performed_by', 'activities', 'activities__user'
        ).all().order_by('-order_date')[:5]
        recent_orders_data = OrderSerializer(recent_orders, many=True, context={'request': request}).data

        # Recent customers
        recent_customers = Customer.objects.prefetch_related(
            'orders', 'orders__stages', 'orders__activities', 'orders__tailor', 'orders__master'
        ).all().order_by('-created_at')[:5]
        recent_customers_data = CustomerSerializer(recent_customers, many=True, context={'request': request}).data

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
