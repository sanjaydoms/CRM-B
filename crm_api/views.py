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

from .models import Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign
from .serializers import (
    CustomerSerializer, MeasurementSerializer, DesignPreferenceSerializer, 
    FabricSelectionSerializer, TailorSerializer, OrderSerializer, BoutiqueFabricSerializer,
    BoutiqueDesignSerializer
)

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by('-created_at')
    serializer_class = CustomerSerializer

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
        fabric_price = float(request.data.get('fabric_price', 0.0))

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
        tailor_id = request.data.get('tailor_id')
        tailor = None
        if tailor_id:
            try:
                tailor = Tailor.objects.get(id=tailor_id)
            except Tailor.DoesNotExist:
                pass

        master_id = request.data.get('master_id')
        master = None
        if master_id:
            try:
                master = Tailor.objects.get(id=master_id)
            except Tailor.DoesNotExist:
                pass

        # Pricing components
        base_price = float(request.data.get('base_price', 0.0))
        fabric_price = float(request.data.get('fabric_price', 0.0))
        embroidery_price = float(request.data.get('embroidery_price', 0.0))
        customization_price = float(request.data.get('customization_price', 0.0))
        tailoring_charges = float(request.data.get('tailoring_charges', 0.0))
        packaging_handling = float(request.data.get('packaging_handling', 0.0))
        
        # Calculate subtotal, taxes (5%), and total
        subtotal = base_price + fabric_price + embroidery_price + customization_price + tailoring_charges + packaging_handling
        taxes = subtotal * 0.05
        total_amount = subtotal + taxes

        # Generate custom order ID: T2B-YYMMDD-XXXX
        today = datetime.date.today().strftime('%y%m%d')
        rand_num = random.randint(1000, 9999)
        order_id = f"T2B-{today}-{rand_num}"

        # Estimated delivery date (default 15 days from now)
        est_delivery = datetime.date.today() + datetime.timedelta(days=15)

        payment_status = request.data.get('payment_status', 'Paid')
        advance_paid = 0.0
        amount_paid = 0.0
        if payment_status == 'Paid':
            advance_paid = total_amount
            amount_paid = total_amount
        elif payment_status == 'Partially Paid':
            advance_paid = float(request.data.get('advance_paid', total_amount * 0.5))
            amount_paid = advance_paid

        order = Order.objects.create(
            order_id=order_id,
            customer=customer,
            tailor=tailor,
            master=master,
            payment_status=payment_status,
            order_status='Received', # Default new order status
            base_price=base_price,
            fabric_price=fabric_price,
            embroidery_price=embroidery_price,
            customization_price=customization_price,
            tailoring_charges=tailoring_charges,
            packaging_handling=packaging_handling,
            taxes=taxes,
            total_amount=total_amount,
            estimated_delivery=est_delivery,
            delivery_method=request.data.get('delivery_method', 'Direct Pickup'),
            courier_service=request.data.get('courier_service'),
            tracking_number=request.data.get('tracking_number'),
            delivery_address=request.data.get('delivery_address'),
            advance_paid=advance_paid,
            amount_paid=amount_paid
        )

        # Update tailor/master status if busy
        if tailor:
            tailor.status = 'Busy'
            tailor.save()
        if master:
            master.status = 'Busy'
            master.save()

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

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().order_by('-order_date')
    serializer_class = OrderSerializer

    def perform_update(self, serializer):
        order = serializer.save()
        if order.payment_status == 'Paid':
            order.amount_paid = order.total_amount
        elif order.payment_status == 'Pending':
            order.amount_paid = 0.00
        order.save()

    @action(detail=True, methods=['PATCH'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        if new_status:
            order.order_status = new_status
            order.save()
            return Response({'status': 'status updated', 'order_status': order.order_status})
        return Response({'error': 'no status provided'}, status=status.HTTP_400_BAD_REQUEST)

class DashboardView(views.APIView):
    def get(self, request):
        total_customers = Customer.objects.count()
        total_orders = Order.objects.count()
        revenue = Order.objects.filter(payment_status='Paid').aggregate(Sum('total_amount'))['total_amount__sum'] or 0.0
        
        status_counts = Order.objects.values('order_status').annotate(count=Count('id'))
        
        # Recent orders with customer and tailor detail
        recent_orders = Order.objects.all().order_by('-order_date')[:5]
        recent_orders_data = OrderSerializer(recent_orders, many=True).data

        # Recent customers
        recent_customers = Customer.objects.all().order_by('-created_at')[:5]
        recent_customers_data = CustomerSerializer(recent_customers, many=True).data

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
