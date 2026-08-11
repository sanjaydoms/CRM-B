import json
import os
import uuid
from decimal import Decimal

from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import OwnerOnly, SUPERVISOR_ROLES, visible_customers, visible_orders
from core.roles import OWNER, resolve_user_role
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q, Sum, Count

from .models import (
    Customer, CustomerMessage, GarmentImage, Measurement, DesignPreference,
    FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign,
    Notification, OrderStageHistory, BoutiqueSettings, MeasurementHistory,
    OrderStage, OrderActivity
)
from .serializers import (
    CustomerSerializer, MeasurementSerializer, DesignPreferenceSerializer,
    FabricSelectionSerializer, TailorSerializer, OrderSerializer, BoutiqueFabricSerializer,
    BoutiqueDesignSerializer, NotificationSerializer, OrderStageHistorySerializer, BoutiqueSettingsSerializer,
    MeasurementHistorySerializer, CustomerSummarySerializer, OrderSummarySerializer,
    OrderStageSerializer, CustomerMessageSerializer, GarmentImageSerializer
)
from apps.design_studio.models import DesignAsset
from domains.customers.repositories import CustomerRepository
from domains.orders.messaging import send_customer_message
from domains.orders.notifications import create_order_notifications
from domains.orders.tracking import tracking_url
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
        base = (CustomerRepository.summary_queryset() if self.action == 'list'
                else CustomerRepository.get_all())
        return visible_customers(base, self.request.user)

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

        # Update the customer's current pick rather than appending another one.
        # 'Save as Draft' and 'Next' both call this, and Back/Next through step
        # 4 calls it again, so a customer who changed their mind twice ended up
        # with three FabricSelection rows and no way to delete any of them --
        # and the design studio's context builder reads whatever rows exist.
        # Re-selecting is the normal case here; a genuinely new selection is
        # what a new order is for.
        selection = customer.fabric_selections.order_by('-id').first()
        created = selection is None
        if created:
            selection = FabricSelection(customer=customer)

        selection.is_boutique_fabric = is_boutique_fabric
        selection.fabric_name = fabric_name
        selection.fabric_price = fabric_price
        if image_urls or created:
            # Keep photographs already attached when this pass uploaded none.
            selection.uploaded_fabric_images = image_urls
        selection.save()

        serializer = FabricSelectionSerializer(selection)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='create-order')
    def create_order(self, request, pk=None):
        customer = self.get_object()
        try:
            order = OrderService.create_order_for_customer(
                customer, request.data, user=request.user)
        except ValueError as ve:
            # Money validation lives in the service, which is the one choke
            # point every order-creation path routes through. Surface its
            # reason as a 400 the wizard can print, not a 500.
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
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
        return visible_orders(OrderRepository.get_all(), self.request.user)

    def perform_update(self, serializer):
        old_status = serializer.instance.order_status
        order = serializer.save()
        self._reconcile_payment(order, serializer.validated_data)

        if old_status != order.order_status:
            create_order_notifications(order, created=False)

    @staticmethod
    def _reconcile_payment(order, changed):
        """Keep the money and the payment label in step, money first.

        This used to run the other way: payment_status was authoritative and
        rewrote amount_paid -- to the full total on 'Paid', to zero on
        'Pending' -- while never touching advance_paid and having no branch at
        all for 'Partially Paid'. Three consequences, all seen:

          * Setting 'Partially Paid' did nothing whatsoever, so the row read
            "Balance Rs0" beside the words Partially Paid.
          * Setting 'Pending' zeroed amount_paid but left advance_paid, so the
            invoice printed "Advance Paid Rs10,000 / Balance Due Rs0" next to a
            table saying Balance Rs31,500.
          * The dashboard sums advance_paid for Partially Paid rows, so money
            zeroed here reappeared there.

        Deriving the label from the amount makes recording a part-payment
        possible at all -- the serializer already accepts amount_paid, so the
        Invoices row only needs to PATCH a number.
        """
        total = order.total_amount or Decimal('0')

        if 'amount_paid' in changed or 'advance_paid' in changed:
            paid = order.amount_paid if 'amount_paid' in changed else order.advance_paid
        elif order.payment_status == 'Paid':
            paid = total
        elif order.payment_status == 'Pending':
            paid = Decimal('0')
        else:
            paid = order.amount_paid or Decimal('0')

        paid = min(max(Decimal(paid or 0), Decimal('0')), total)

        if paid <= 0:
            label = 'Pending'
        elif paid >= total:
            label = 'Paid'
        else:
            label = 'Partially Paid'

        order.amount_paid = paid
        # The advance is what was taken up front; it can never exceed what has
        # actually been paid, which is where the stale-advance contradiction
        # came from.
        order.advance_paid = min(order.advance_paid or Decimal('0'), paid)
        order.payment_status = label
        order.save(update_fields=['amount_paid', 'advance_paid', 'payment_status'])

    # A client-facing status corresponds to completing a specific stage. Statuses
    # absent here (e.g. Stylist Review, Shipped) carry no stage meaning and are
    # recorded directly by the no-stage branch in update_status below.
    #
    # 'Shipped' used to alias 'ready_for_delivery', whose own status_map entry
    # maps back to 'Ready for Dispatch' -- so picking Shipped answered 200 and
    # stored something else. order_status could never hold 'Shipped' through any
    # UI path, which made the Shipped branch of create_order_notifications, the
    # only message carrying courier_service and tracking_number, unreachable.
    # Dropping the alias lets it fall through to the no-stage branch, which
    # writes the status and fires the notification.
    #
    # 'Quality Check' used to map to 'stitching_completed', while delivery is
    # gated on 'master_quality_check'. The dropdown therefore walked the owner
    # to the last rung, claimed QC had happened when it had not, and then
    # refused delivery naming a step it had never offered. stitching_completed
    # is still reached by 'Design & Creation' advancing through the ladder.
    STATUS_TO_STAGE = {
        'Received': 'created',
        'Confirmed': 'fabric_confirmed',
        # 'Design & Creation' means the garment is being made, and the status
        # after it is Quality Check -- so the stage it must land on is the one
        # that says the making is finished. It used to map to
        # assigned_to_tailor, which meant NO dropdown value touched either
        # stitching stage: an order could walk Received -> ... -> Delivered
        # through this control with both of them still NOT_STARTED, i.e.
        # delivered with the garment recorded as never sewn. Mapping it here
        # also makes the quality-check guard satisfiable from the dropdown,
        # and correctly refuses a Master, since stitching is the tailor's own
        # work.
        'Design & Creation': 'stitching_completed',
        'Quality Check': 'master_quality_check',
        'Ready for Dispatch': 'ready_for_delivery',
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

    @action(detail=True, methods=['POST'], url_path='garment-images')
    def upload_garment_image(self, request, pk=None):
        """Add or replace one angle of the finished garment.

        One image per view, so uploading FRONT twice replaces it rather than
        stacking -- which is what "replace the image if a better one is taken"
        means in practice, and bounds an order's gallery at the nine views
        without needing a separate cap.
        """
        order = self.get_object()
        view = request.data.get('view', 'FRONT')
        if view not in dict(GarmentImage.VIEW_CHOICES):
            return Response(
                {'error': f"Unknown view '{view}'.",
                 'allowed': [v for v, _ in GarmentImage.VIEW_CHOICES]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if 'image' not in request.FILES:
            return Response({'error': 'No image was uploaded.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Through the serializer rather than assigned directly: its ImageField
        # runs the file through Pillow, so a renamed .exe is rejected here
        # instead of becoming a broken <img> on a customer's tracking page.
        serializer = GarmentImageSerializer(
            data={'view': view, 'image': request.FILES['image']}
        )
        serializer.is_valid(raise_exception=True)

        for existing in order.garment_images.filter(view=view):
            existing.image.delete(save=False)  # the file, not just the row
            existing.delete()

        image = serializer.save(
            order=order,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        return Response(GarmentImageSerializer(image).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['DELETE'], url_path='garment-images/(?P<image_id>[0-9]+)')
    def delete_garment_image(self, request, pk=None, image_id=None):
        order = self.get_object()
        image = order.garment_images.filter(id=image_id).first()
        if image is None:
            return Response({'error': 'No such image on this order.'},
                            status=status.HTTP_404_NOT_FOUND)
        image.image.delete(save=False)
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['POST'], url_path='publish-garment-images')
    def publish_garment_images(self, request, pk=None):
        """Show the finished-garment photographs to the customer, or stop.

        Publishing is what queues the "your outfit is ready" message, so it is
        the moment the customer learns anything -- which is why it is a separate
        deliberate step and why front and back must both be there first. The
        specification requires those two; the rest are optional angles.
        """
        order = self.get_object()
        publish = request.data.get('published', True)
        if isinstance(publish, str):
            publish = publish.lower() not in ('false', '0', '')

        if publish:
            present = set(order.garment_images.values_list('view', flat=True))
            missing = [v for v in ('FRONT', 'BACK') if v not in present]
            if missing:
                return Response(
                    {'error': 'Front and back photographs are both required '
                              'before the customer sees the gallery.',
                     'missing': missing},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Ask whether the message was already queued, not whether the gallery is
        # currently published. garment_images_published is cleared by this same
        # endpoint on unpublish, so it was never the one-way latch the comment
        # below intends: hiding the gallery and re-sharing it messaged the
        # customer "your outfit is ready" a second time.
        already = order.customer_messages.filter(template_key='garment_ready').exists()
        order.garment_images_published = publish
        order.save(update_fields=['garment_images_published'])

        # Only on the transition, so re-publishing an already-published gallery
        # after swapping one photograph does not tell the customer twice.
        if publish and not already:
            send_customer_message(
                order,
                'garment_ready',
                f"Dear {order.customer.first_name}, your outfit for order "
                f"{order.order_id} is ready! You can see photographs of the "
                f"finished garment here: {tracking_url(order)}",
            )

        return Response(OrderSerializer(order).data)

    @action(detail=False, methods=['GET'], url_path='customer-messages',
            permission_classes=[OwnerOnly])
    def customer_messages(self, request):
        """Every message still waiting to be sent, across the boutique's orders.

        One request for the whole screen rather than one per order card: the
        orders registry is unpaginated, so a per-order fetch meant a request per
        order in the boutique every time it opened.

        Owner-only, and not because sending is their job -- because each body
        contains the order's tracking link, which is an unauthenticated bearer
        credential for a page showing the order's totals and balance. A tailor
        can see their own orders, but the role matrix deliberately keeps the
        money from them, and handing over the link would route around that.

        Queued only. This is a to-do list, not the archive; what has already
        been sent is history and does not belong in a payload fetched on every
        dashboard refresh.
        """
        messages = (
            CustomerMessage.objects
            .filter(status='QUEUED', order__in=self.get_queryset())
            .select_related('sent_by')
        )
        return Response(CustomerMessageSerializer(messages, many=True).data)

    @action(detail=True, methods=['POST'], url_path='mark-message-sent',
            permission_classes=[OwnerOnly])
    def mark_message_sent(self, request, pk=None):
        """Record that the owner sent a queued message from their own WhatsApp.

        Nothing here can observe a send that happened in another app, so this is
        the owner's word for it and is stored as such -- sent_by is who said so.
        It deliberately stops at SENT: DELIVERED and READ are provider facts,
        and there is no provider.

        Owner-only for the same reason the list is, and because it is the
        owner's phone the message goes from. Stated explicitly rather than
        relying on RolePermission's default for unlisted actions, so that adding
        the name to a staff list later cannot quietly open it up.
        """
        order = self.get_object()
        try:
            message_id = int(request.data.get('message_id'))
        except (TypeError, ValueError):
            # id is a BigAutoField; a non-numeric value reaches the database as
            # a bad cast and surfaces as a 500 rather than the 400 it is.
            return Response(
                {'error': 'message_id must be a number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = order.customer_messages.filter(id=message_id).first()
        if message is None:
            return Response(
                {'error': 'No such message on this order.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        message.status = 'SENT'
        message.sent_by = request.user
        message.save(update_fields=['status', 'sent_by'])
        return Response(CustomerMessageSerializer(message).data)

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

    def _audience(self):
        """(role, email) this caller may read, derived from who signed in.

        This used to be read straight off ?role=, with an unfiltered
        `return qs` for anything unrecognised -- so ?role=Customer handed any
        signed-in staff member every customer notification in the boutique,
        balances and contact details included, and ?role=Owner handed over the
        owner's own. 'Owner' was also api.getNotifications' default argument,
        so the client was asking for it by accident on every load.

        Keyed on the Tailor profile rather than a role allowlist: a boutique
        that has split the floor has Cutting Masters and QC Masters too (see
        Tailor.ROLE_CHOICES), and naming only 'Master' and 'Tailor' would cut
        every specialist off from their own notifications.
        """
        role = resolve_user_role(self.request.user)
        if role == OWNER:
            return 'Owner', None
        profile = getattr(self.request.user, 'tailor_profile', None)
        if profile is not None:
            return profile.role, (profile.email or self.request.user.email)
        # Designers and anyone else get nothing rather than everything.
        return None, None

    def get_queryset(self):
        role, email = self._audience()
        qs = Notification.objects.all()
        if role is None:
            return qs.none()
        if role == 'Owner':
            return qs.filter(recipient_role='Owner').order_by('-created_at')
        qs = qs.filter(recipient_role=role)
        if email:
            qs = qs.filter(recipient_email=email)
        return qs.order_by('-created_at')

    @action(detail=False, methods=['POST'], url_path='mark-all-read')
    def mark_all_read(self, request):
        # Same derivation as the read path -- otherwise a tailor could mark the
        # owner's notifications read by asking for ?role=Owner.
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'status': 'marked as read'})

class DashboardView(views.APIView):
    """The landing numbers, scoped to what the caller is allowed to see.

    Every queryset here goes through visible_orders/visible_customers, the same
    helpers OrderViewSet.get_queryset uses one class above. They were missing:
    the dashboard read Customer.objects and Order.objects directly, so a tailor
    who correctly got a 404 asking for an order they were not on could load
    this endpoint and receive the boutique's turnover, its order count, and the
    full summary row -- mobile number, measurements, total spend -- for every
    client in the building, including the ones they had never been assigned.
    """

    def get(self, request):
        orders = visible_orders(Order.objects.all(), request.user)
        customers = visible_customers(Customer.objects.all(), request.user)

        total_customers = customers.count()

        # The order count and both revenue figures used to be three separate
        # queries that each scanned the same table, and the dashboard is the
        # first thing every session loads. Conditional aggregation asks for all
        # three in one pass, which matters far more than the scan itself when
        # the database is a network hop away: three round trips become one.
        order_totals = orders.aggregate(
            total=Count('id'),
            paid=Sum('total_amount', filter=Q(payment_status='Paid')),
            partial=Sum('advance_paid', filter=Q(payment_status='Partially Paid')),
        )
        total_orders = order_totals['total']
        revenue = float(order_totals['paid'] or 0.0) + float(order_totals['partial'] or 0.0)

        status_counts = orders.values('order_status').annotate(count=Count('id'))

        # Recent orders. The dashboard renders the stage tracker but never the
        # activity log or stage histories, so those stay out of the payload.
        recent_orders = visible_orders(OrderRepository.summary_queryset(), request.user)[:5]
        recent_orders_data = OrderSummarySerializer(recent_orders, many=True, context={'request': request}).data

        # Recent customers, as flat summary rows -- the dashboard shows name, type
        # and spend, not each client's full order history.
        recent_customers = visible_customers(CustomerRepository.summary_queryset(), request.user)[:5]
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
