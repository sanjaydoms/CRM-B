import json
import os
import secrets
import uuid
from decimal import Decimal

from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import viewsets, status, views
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import (
    OwnerOnly, OwnNotifications, SUPERVISOR_ROLES, visible_customers, visible_orders,
)
from core.roles import OWNER, resolve_user_role
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import transaction
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
from domains.orders import drafts
from domains.orders.messaging import send_customer_message
from domains.orders.notifications import create_order_notifications
from domains.orders.tracking import tracking_url
from domains.orders.repositories import OrderRepository
from domains.orders.services import OrderService, refresh_staff_availability

class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer

    def get_serializer_class(self):
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
        
        selected_urls = request.data.get('selected_urls', '[]')
        try:
            image_urls = json.loads(selected_urls)
        except Exception:
            image_urls = []
            
        files = request.FILES.getlist('images')
        for f in files:
            path = f"design_references/cust_{customer.id}/{uuid.uuid4()}_{f.name}"
            saved_path = default_storage.save(path, ContentFile(f.read()))
            image_urls.append(request.build_absolute_uri(default_storage.url(saved_path)))
            
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
        templates = DesignAsset.objects.filter(
            source=DesignAsset.SOURCE_SUGGESTION, garment_type__iexact=customer.garment_type)
        if not templates.exists():
            templates = DesignAsset.objects.filter(source=DesignAsset.SOURCE_SUGGESTION)
        
        serializer = BoutiqueDesignSerializer(templates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'], url_path='boutique-designs')
    def boutique_designs(self, request, pk=None):
        customer = self.get_object()
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

        image_urls = []
        files = request.FILES.getlist('images')
        for f in files:
            path = f"fabrics/cust_{customer.id}/{uuid.uuid4()}_{f.name}"
            saved_path = default_storage.save(path, ContentFile(f.read()))
            image_urls.append(request.build_absolute_uri(default_storage.url(saved_path)))

        selection = customer.fabric_selections.order_by('-id').first()
        created = selection is None
        if created:
            selection = FabricSelection(customer=customer)

        selection.is_boutique_fabric = is_boutique_fabric
        selection.fabric_name = fabric_name
        selection.fabric_price = fabric_price
        if image_urls or created:
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
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        serializer = OrderSerializer(order, context={'request': request})
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

    def perform_destroy(self, instance):
        """Removing someone from the roster must not leave a live login behind.

        Tailor.user is SET_NULL, so deleting the row detached the account and
        left it with no profile of any kind. Before Phase 8 that resolved to
        OWNER, which made dismissing a staff member the act that promoted them:
        their token still authenticated, and payroll, deposits, advances and
        payouts all opened to it. core.roles now answers None for an unclaimed
        account, so the escalation is closed at the root -- but a dismissed
        person's token should stop working, not merely stop being privileged.

        Deactivating rather than deleting the User, the same choice
        DesignerViewSet.perform_destroy makes: DRF's TokenAuthentication
        refuses an inactive user, so this revokes the token immediately, while
        the row survives to keep the audit trail and the payroll, ledger,
        payout and review history that points at it.
        """
        user = instance.user
        super().perform_destroy(instance)
        if user is None:
            return
        # One account, two jobs. A person can hold a Design Studio login AND a
        # place on the production roster, and deactivating on the strength of
        # one profile cuts off the role they still hold. Only an account that
        # nothing claims any more is closed.
        if getattr(user, 'designer_profile', None) is not None:
            return
        if user.is_active:
            user.is_active = False
            user.save(update_fields=['is_active'])
        # Deactivation already makes DRF refuse the token, but the row is
        # deleted rather than left inert: reinstating the person later
        # reactivates the account, and a token minted before the dismissal must
        # not come back to life with it.
        Token.objects.filter(user=user).delete()

    def _ensure_user_account(self, tailor):
        if tailor.email:
            tailor.email = tailor.email.strip().lower()

            # Never point a staff account at the boutique owner's address.
            # core.roles identifies the owner by comparing User.email to the
            # tenant's owner_email, and Django's User.email is not unique, so
            # putting the owner's address on a staff row -- which the block
            # below then copies onto that row's OWN User -- made that staff
            # login resolve as the owner. DesignerViewSet.create_login has
            # refused the owner's address for this reason since designers got
            # accounts; the roster never did.
            #
            # Left as a silent no-op on the account rather than an error: the
            # roster row keeps whatever the owner typed, and the only thing
            # refused is granting a login under it.
            from django.db import connection as _conn
            tenant_owner = (getattr(_conn.tenant, 'owner_email', '') or '').lower()
            if tenant_owner and tailor.email == tenant_owner:
                return

            # Repoint the account this staff member ALREADY has, rather than
            # hunting for one under the new address. Looking up by email meant
            # that changing a Master's email created a second User and left the
            # first -- their real login, with a live token and unchanged
            # password -- attached to no Tailor profile at all. resolve_user_role
            # then falls through to OWNER for a profile-less account, so that
            # session silently became the boutique owner: the OwnerOnly wall
            # opened and their notifications switched to the owner's feed.
            if tailor.user_id:
                existing = tailor.user
                # Never move the OWNER's account off the owner address. On a
                # boutique that ran before Phase 8 the owner's own User can
                # already be linked to a roster row (core/roles.py's docstring
                # records how), and renaming it here breaks the only positive
                # test for ownership -- permanently, because every screen that
                # could undo it is then refused to them. The guard above stops
                # a row being moved TO the owner's address; this stops the
                # owner's account being moved away from it.
                if (existing.email or '').lower() == tenant_owner:
                    return
                if existing.email != tailor.email:
                    existing.email = tailor.email
                    existing.username = self._unique_username(
                        tailor.email.split('@')[0], exclude_pk=existing.pk)
                    existing.save(update_fields=['email', 'username'])
                return

            user = User.objects.filter(email__iexact=tailor.email).first()

            # An account already spoken for by ANOTHER roster row. Tailor.user
            # is a OneToOne, so linking it raised IntegrityError -- after
            # perform_create had already committed the Tailor row, leaving a
            # 500 and an orphan. Refused the same way the owner's address is,
            # and for the same reason: the row keeps what was typed, only the
            # login is withheld.
            if user is not None:
                claimed = getattr(user, 'tailor_profile', None)
                if claimed is not None and claimed.pk != tailor.pk:
                    return

            # A previously DELETED staff member, being taken back on.
            #
            # perform_destroy deactivates the login it detaches, so this User is
            # inactive with a password nobody holds. Linking it as-is produced a
            # roster row that looks healthy and an account that can never be
            # signed into: authenticate() refuses an inactive user, and the
            # password-reset endpoint answers the same generic 200 it gives an
            # unknown address without sending anything. The owner had no way to
            # see it and no way in the product to fix it.
            #
            # Re-hiring is therefore a re-issue: the account comes back with a
            # NEW credential, printed once like any other. The old password and
            # any token minted before the dismissal stay dead, which is the
            # point -- coming back must not silently restore the credential the
            # person left with.
            if user is not None and not user.is_active:
                bootstrap = secrets.token_urlsafe(9)
                user.is_active = True
                user.set_password(bootstrap)
                user.save(update_fields=['is_active', 'password'])
                Token.objects.filter(user=user).delete()
                tailor._bootstrap_password = bootstrap

            if not user:
                # One password, generated here, for this account only.
                #
                # This used to be os.environ.get('TAILOR_DEFAULT_PASSWORD',
                # 'TailorSecure2026!'), and the fallback is the whole problem:
                # it is written in this repository AND shipped in the JavaScript
                # bundle, the username is the email's local part, and
                # find_tenant_for_account searches every boutique's schema for a
                # matching username. So one unauthenticated POST to
                # /api/auth/login/ with a first-name-shaped guess landed inside
                # whichever boutique had such an account -- any boutique, not
                # only the one the guesser belonged to. Staff who left kept a
                # working credential everywhere.
                #
                # The same constant had an opposite failure too: an operator who
                # took the comment's advice and set TAILOR_DEFAULT_PASSWORD
                # broke onboarding, because the "share credentials" modal went
                # on printing the literal. Generating the value and returning it
                # is what makes the screen and the database agree.
                #
                # Stashed on the instance rather than returned: the caller here
                # is perform_create/perform_update, which cannot alter the
                # response. TailorSerializer.to_representation picks it up and
                # emits it exactly once, on the response to the request that
                # created the account -- it is never stored and never readable
                # again, which is the same contract every other product uses for
                # a generated credential.
                bootstrap = secrets.token_urlsafe(9)
                user = User.objects.create_user(
                    username=self._unique_username(tailor.email.split('@')[0]),
                    email=tailor.email,
                    password=bootstrap,
                    first_name=tailor.name
                )
                tailor._bootstrap_password = bootstrap
            if tailor.user != user:
                tailor.user = user
                tailor.save()

    @staticmethod
    def _unique_username(base, exclude_pk=None):

        base = (base or 'staff').strip().lower() or 'staff'
        candidate, counter = base, 1
        taken = User.objects.exclude(pk=exclude_pk) if exclude_pk else User.objects.all()
        while taken.filter(username=candidate).exists():
            candidate = f"{base}{counter}"
            counter += 1
        return candidate

class BoutiqueFabricViewSet(viewsets.ModelViewSet):
    queryset = BoutiqueFabric.objects.all()
    serializer_class = BoutiqueFabricSerializer

class BoutiqueDesignViewSet(viewsets.ModelViewSet):
    queryset = DesignAsset.objects.filter(
        source__in=[DesignAsset.SOURCE_CATALOGUE, DesignAsset.SOURCE_SUGGESTION])
    serializer_class = BoutiqueDesignSerializer

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        return visible_orders(OrderRepository.get_all(), self.request.user)

    def perform_update(self, serializer):
        old_status = serializer.instance.order_status
        old_tailor_id = serializer.instance.tailor_id
        old_master_id = serializer.instance.master_id
        old_tailor = serializer.instance.tailor
        old_master = serializer.instance.master

        order = serializer.save()
        self._reconcile_payment(order, serializer.validated_data)

        if old_status != order.order_status:
            create_order_notifications(order, created=False)

        if old_tailor_id != order.tailor_id or old_master_id != order.master_id:
            refresh_staff_availability(old_tailor, old_master,
                                       order.tailor, order.master)

            if old_tailor_id != order.tailor_id:
                from apps.production.models import ProductionTask
                ProductionTask.objects.filter(
                    order=order, assigned_to_id=old_tailor_id,
                ).update(assigned_to=order.tailor)

                if order.tailor:
                    Notification.objects.create(
                        title=f"New Stitching Task: {order.order_id}",
                        message=(f"Order {order.order_id} has been reassigned to "
                                 f"you for stitching."),
                        recipient_role=order.tailor.role,
                        recipient_email=(order.tailor.user.email
                                         if order.tailor.user else None),
                    )

            if old_master_id != order.master_id and order.master:
                Notification.objects.create(
                    title=f"New Assignment: {order.order_id}",
                    message=(f"Order {order.order_id} has been reassigned to you "
                             f"as Supervising Master."),
                    recipient_role=order.master.role,
                    recipient_email=(order.master.user.email
                                     if order.master.user else None),
                )

    @staticmethod
    def _reconcile_payment(order, changed):
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
        order.advance_paid = min(order.advance_paid or Decimal('0'), paid)
        order.payment_status = label
        order.save(update_fields=['amount_paid', 'advance_paid', 'payment_status'])

    STATUS_TO_STAGE = {
        'Received': 'created',
        'Confirmed': 'fabric_confirmed',
        'Design & Creation': 'stitching_completed',
        'Quality Check': 'master_quality_check',
        'Ready for Dispatch': 'ready_for_delivery',
        'Delivered': 'delivered',
    }

    CLIENT_STATUSES = frozenset({
        'Received', 'Confirmed', 'Stylist Review', 'Design & Creation',
        'Quality Check', 'Ready for Dispatch', 'Shipped', 'Delivered',
    })

    @action(detail=True, methods=['PATCH'], url_path='master-verification')
    def master_verification(self, request, pk=None):
        order = self.get_object()
        checks = request.data.get('master_verification')
        if not isinstance(checks, dict):
            return Response({'error': 'master_verification must be an object.'},
                            status=status.HTTP_400_BAD_REQUEST)
        merged = dict(order.master_verification or {})
        merged.update({str(k): bool(v) for k, v in checks.items()})
        order.master_verification = merged
        order.save(update_fields=['master_verification'])
        return Response(OrderSerializer(order, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['PATCH'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        if not new_status:
            return Response({'error': 'no status provided'}, status=status.HTTP_400_BAD_REQUEST)

        if new_status not in self.CLIENT_STATUSES:
            return Response(
                {'error': f"Unknown order status '{new_status}'.",
                 'allowed': sorted(self.CLIENT_STATUSES)},
                status=status.HTTP_400_BAD_REQUEST)

        stage_key = self.STATUS_TO_STAGE.get(new_status)
        if not stage_key:
            role = resolve_user_role(request.user)
            if role != OWNER and role not in SUPERVISOR_ROLES:
                return Response(
                    {'error': f"Role {role} is not authorized to set the order to "
                              f"{new_status}."},
                    status=status.HTTP_403_FORBIDDEN)
            if order.order_status != new_status:
                order.order_status = new_status
                order.save(update_fields=['order_status'])
                create_order_notifications(order, created=False)
            return Response({'status': 'status updated', 'order_status': order.order_status})

        config = BoutiqueSettings.objects.get_or_create(id=1)[0].workflow_config
        keys = [s['key'] for s in config]
        target_index = keys.index(stage_key)
        previous_landing = -1
        for other_status, other_key in self.STATUS_TO_STAGE.items():
            other_index = keys.index(other_key) if other_key in keys else -1
            if other_index < target_index:
                previous_landing = max(previous_landing, other_index)

        try:
            with transaction.atomic():
                updated = order
                for key in keys[previous_landing + 1:target_index + 1]:
                    stage = order.stages.filter(stage_key=key).first()
                    if stage is None or stage.status in ('COMPLETED', 'SKIPPED'):
                        continue
                    optional = next(
                        (s.get('optional') for s in config if s['key'] == key), False)
                    updated = OrderService.transition_order_stage(
                        order=order,
                        stage_key=key,
                        new_status='SKIPPED' if optional else 'COMPLETED',
                        user=request.user,
                    )
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        return Response({'status': 'status updated', 'order_status': order.order_status})

    @action(detail=True, methods=['POST'], url_path='garment-images')
    def upload_garment_image(self, request, pk=None):
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

        already = order.customer_messages.filter(template_key='garment_ready').exists()
        order.garment_images_published = publish
        order.save(update_fields=['garment_images_published'])

        if publish and not already:
            send_customer_message(
                order,
                'garment_ready',
                f"Dear {order.customer.first_name}, your outfit for order "
                f"{order.order_id} is ready! You can see photographs of the "
                f"finished garment here: {tracking_url(order)}",
            )

        return Response(OrderSerializer(order, context={'request': request}).data)

    @action(detail=False, methods=['GET'], url_path='customer-messages',
            permission_classes=[OwnerOnly])
    def customer_messages(self, request):
        messages = (
            CustomerMessage.objects
            .filter(status='QUEUED', order__in=self.get_queryset())
            .select_related('sent_by')
        )
        return Response(CustomerMessageSerializer(messages, many=True).data)

    @action(detail=True, methods=['POST'], url_path='mark-message-sent',
            permission_classes=[OwnerOnly])
    def mark_message_sent(self, request, pk=None):
        order = self.get_object()
        try:
            message_id = int(request.data.get('message_id'))
        except (TypeError, ValueError):
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

        try:
            for stage_key, stage_status in (
                ('stitching_in_progress', 'IN_PROGRESS'),
                ('stitching_in_progress', 'COMPLETED'),
                ('stitching_completed', 'COMPLETED'),
            ):
                OrderService.transition_order_stage(
                    order=order,
                    stage_key=stage_key,
                    new_status=stage_status,
                    comments=comments or '',
                    user=request.user,
                )
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = OrderSerializer(OrderRepository.get_by_id(order.pk), context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['POST'], url_path='submit-stage-review')
    def submit_stage_review(self, request, pk=None):
        order = self.get_object()
        stage = request.data.get('stage')
        comments = request.data.get('comments')
        image = request.FILES.get('image')

        if not stage:
            return Response({'error': 'stage is required'},
                            status=status.HTTP_400_BAD_REQUEST)

        if not order.stages.filter(stage_key=stage).exists():
            return Response({'error': f"This order has no stage '{stage}'."},
                            status=status.HTTP_404_NOT_FOUND)

        performer = (request.user.get_full_name() or request.user.username
                     or 'Boutique Staff')

        with transaction.atomic():
            OrderStageHistory.objects.filter(order=order, stage=stage).delete()
            OrderStageHistory.objects.create(
                order=order,
                stage=stage,
                comments=comments,
                image=image,
                completed_by_name=performer,
            )

        return Response(OrderSerializer(order, context={'request': request}).data)

    @action(detail=True, methods=['POST'], url_path='assign-stage')
    def assign_stage(self, request, pk=None):
        order = self.get_object()
        stage_key = request.data.get('stage_key')
        tailor_id = request.data.get('tailor_id')

        if not stage_key:
            return Response({'error': 'stage_key is required'}, status=status.HTTP_400_BAD_REQUEST)

        stage = order.stages.filter(stage_key=stage_key).first()
        if not stage:
            return Response({'error': f"Unknown stage '{stage_key}' for this order."},
                            status=status.HTTP_404_NOT_FOUND)

        if tailor_id in (None, '', 'null'):
            stage.assigned_to = None
            stage.save(update_fields=['assigned_to'])
            return Response(OrderStageSerializer(stage).data, status=status.HTTP_200_OK)

        try:
            tailor_id = int(tailor_id)
        except (TypeError, ValueError):
            return Response({'error': 'tailor_id must be a number.'},
                            status=status.HTTP_400_BAD_REQUEST)

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

        Notification.objects.create(
            recipient_role=tailor.role,
            recipient_email=tailor.email or (tailor.user.email if tailor.user_id else ''),
            title=f"New assignment on {order.order_id}",
            message=f"You have been assigned {stage.stage_name} on order {order.order_id}.",
        )
        OrderActivity.objects.create(
            order=order,
            event_type='ASSIGNMENT',
            user=request.user if request.user.is_authenticated else None,
            metadata={'stage_key': stage_key, 'stage_name': stage.stage_name,
                      'assigned_to': tailor.name, 'assigned_to_id': tailor.id},
        )

        from apps.production.models import ProductionTask
        ProductionTask.objects.filter(order=order, stage_key=stage_key).update(assigned_to=tailor)

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
            serializer = OrderSerializer(OrderRepository.get_by_id(updated_order.pk), context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by('-created_at')
    serializer_class = NotificationSerializer
    permission_classes = [OwnNotifications]

    def _audience(self):
        role = resolve_user_role(self.request.user)
        if role == OWNER:
            return 'Owner', None
        profile = getattr(self.request.user, 'tailor_profile', None)
        if profile is not None:
            return profile.role, (profile.email or self.request.user.email)
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
            from django.db.models import Q
            qs = qs.filter(Q(recipient_email=email) | Q(recipient_email='')
                           | Q(recipient_email__isnull=True))
        return qs.order_by('-created_at')

    @action(detail=False, methods=['POST'], url_path='mark-all-read')
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'status': 'marked as read'})

class DashboardView(views.APIView):

    def get(self, request):
        orders = visible_orders(Order.objects.all(), request.user)
        customers = visible_customers(Customer.objects.all(), request.user)

        total_customers = customers.count()

        order_totals = orders.aggregate(
            total=Count('id'),
            paid=Sum('total_amount', filter=Q(payment_status='Paid')),
            partial=Sum('advance_paid', filter=Q(payment_status='Partially Paid')),
        )
        total_orders = order_totals['total']
        revenue = float(order_totals['paid'] or 0.0) + float(order_totals['partial'] or 0.0)

        status_counts = orders.values('order_status').annotate(count=Count('id', distinct=True))

        recent_orders = visible_orders(OrderRepository.summary_queryset(), request.user)[:5]
        recent_orders_data = OrderSummarySerializer(recent_orders, many=True, context={'request': request}).data

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


def _board_item_from_draft(order, customer, job, item, position, user):
    from apps.design_studio.models import DesignBoard, DesignBoardItem

    board, _ = DesignBoard.objects.get_or_create(
        order=order,
        defaults={'customer': customer, 'created_by': user if user.is_authenticated else None,
                  'status': DesignBoard.STATUS_SHORTLISTED},
    )
    DesignBoardItem.objects.create(
        board=board,
        garment_job=job,
        source=item.get('source') or 'upload',
        source_ref=item.get('source_ref') or '',
        title=item.get('title') or '',
        image_url=item.get('image_url') or '',
        source_url=item.get('source_url') or '',
        attributes=item.get('attributes') or {},
        colour_palette=item.get('colour_palette') or [],
        match_score=item.get('match_score') or 0,
        match_reasons=item.get('match_reasons') or [],
        is_selected=bool(item.get('is_selected')),
        part=item.get('part') or 'overall',
        position=position,
    )


def _part_items_from_draft(design):
    """The wizard's per-part choices, as board items.

    The order wizard used to shortlist whole designs, and wrote them to the
    draft as `design.items`. It now chooses one photograph per PART of the
    garment -- this pallu, that border -- and writes `design.parts` as
    {part_key: image}. Confirm read only the old key, so every part a customer
    picked was saved on the draft and then silently dropped at the moment the
    order was created: the order reached the workroom with no design on it and
    nothing said so.

    Translated here rather than at the call site so both shapes converge on one
    board-item writer. A draft written before the change still carries `items`
    and still confirms exactly as it did.
    """
    items = []
    for part, image in (design.get('parts') or {}).items():
        if not image:
            continue
        items.append({
            'source': 'library',
            # The DesignAsset the photograph belongs to, so the workroom can
            # reach the whole design from the part that was chosen.
            'source_ref': str(image.get('design_id') or ''),
            'title': image.get('part_label') or part.replace('_', ' '),
            'image_url': image.get('image_url') or '',
            'part': part,
            # Every part chosen IS the choice for that part -- there is no
            # shortlist-then-pick step in the part flow, so each one is
            # selected on arrival. The per-part uniqueness constraint added in
            # design_studio 0017 is what keeps that to one per part.
            'is_selected': True,
        })
    return items


class OrderDraftViewSet(viewsets.ViewSet):

    def _serialise(self, draft):
        return {
            'id': str(draft.id),
            'customer': str(draft.customer_id) if draft.customer_id else None,
            'customer_name': (f"{draft.customer.first_name} {draft.customer.last_name}"
                              if draft.customer_id else
                              (draft.payload.get('first_name') or '').strip() or None),
            'payload': draft.payload,
            'current_step': draft.current_step,
            'version': draft.version,
            'updated_at': draft.updated_at,
        }

    def list(self, request):
        return Response([self._serialise(d) for d in drafts.open_drafts(request.user)])

    def retrieve(self, request, pk=None):
        draft = drafts.open_drafts(request.user).filter(pk=pk).first()
        if draft is None:
            return Response({'error': 'No such draft.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._serialise(draft))

    def create(self, request):
        customer = None
        if customer_id := request.data.get('customer'):
            customer = Customer.objects.filter(pk=customer_id).first()
        draft = drafts.save_draft(
            request.user, request.data.get('payload') or {},
            customer=customer,
            current_step=int(request.data.get('current_step') or 1))
        return Response(self._serialise(draft), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        customer = None
        if customer_id := request.data.get('customer'):
            customer = Customer.objects.filter(pk=customer_id).first()
        try:
            draft = drafts.save_draft(
                request.user, request.data.get('payload'),
                draft_id=pk, customer=customer,
                current_step=int(request.data.get('current_step') or 0),
                version=request.data.get('version'))
        except drafts.DraftConflict as conflict:
            return Response({'error': str(conflict)}, status=status.HTTP_409_CONFLICT)
        if draft is None:
            return Response({'error': 'No such draft.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._serialise(draft))

    def destroy(self, request, pk=None):

        removed = drafts.abandon(request.user, pk)
        if not removed:
            return Response({'error': 'No such draft.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['POST'], url_path='confirm')
    def confirm(self, request, pk=None):
        from apps.catalog.models import GarmentTemplate
        from apps.catalog.serializers import GarmentJobSerializer

        def build(draft):
            payload = draft.payload or {}
            customer = drafts.customer_for(draft, payload)

            measurements = {
                key: value for key, value in (payload.get('measurements') or {}).items()
                if value not in (None, '')
            }
            if measurements:
                Measurement.objects.update_or_create(
                    customer=customer, defaults=measurements)

            prices = payload.get('prices') or {}
            staff = payload.get('staff') or {}
            delivery = payload.get('delivery') or {}
            payment = payload.get('payment') or {}
            garments = payload.get('garments') or []

            def money(value):
                try:
                    return float(value or 0)
                except (TypeError, ValueError):
                    return 0.0

            per_garment = [g.get('pricing') or {} for g in garments]
            has_job_pricing = any(any(money(v) for v in p.values()) for p in per_garment)
            component_keys = ('base', 'fabric', 'embroidery', 'customization', 'tailoring')
            if has_job_pricing:
                component_totals = {
                    key: sum(money(p.get(key)) for p in per_garment)
                    for key in component_keys
                }
            else:
                component_totals = {key: money(prices.get(key)) for key in component_keys}
            full_payment = payment.get('option') == 'full'

            due = sorted(
                d for d in ((g.get('values') or {}).get('delivery_date')
                            for g in (payload.get('garments') or []))
                if d)

            order = OrderService.create_order_for_customer(customer, {
                'tailor_id': staff.get('tailor_id'),
                'master_id': staff.get('master_id'),
                'base_price': component_totals['base'],
                'fabric_price': component_totals['fabric'],
                'embroidery_price': component_totals['embroidery'],
                'customization_price': component_totals['customization'],
                'tailoring_charges': component_totals['tailoring'],
                'packaging_handling': money(prices.get('packaging')),
                'discount': money(prices.get('discount')),
                'payment_status': 'Paid' if full_payment else 'Partially Paid',
                'advance_paid': 0 if full_payment else money(payment.get('advance')),
                'custom_requirements': payload.get('special_instructions')
                                       or payload.get('custom_requirements') or '',
                'estimated_delivery': due[0] if due else None,
                'delivery_method': delivery.get('method') or 'Direct Pickup',
                'courier_service': delivery.get('courier'),
                'tracking_number': delivery.get('tracking'),
                'delivery_address': delivery.get('address'),
            }, user=request.user, notify=False)

            for index, garment in enumerate(garments):
                template = GarmentTemplate.objects.filter(
                    pk=garment.get('template')).first()
                if template is None:
                    if any(money(v) for v in (garment.get('pricing') or {}).values()):
                        raise ValueError(
                            'This draft references a garment that no longer '
                            'exists in the catalogue. Re-open the draft and '
                            'review its garments before confirming.')
                    continue
                job_pricing = garment.get('pricing') or {}
                serializer = GarmentJobSerializer(data={
                    'order': order.id,
                    'template': str(template.id),
                    'spec': garment.get('spec') or {},
                    'measurements': garment.get('measurements') or {},
                    'materials': garment.get('materials') or [],
                    'base_price': money(job_pricing.get('base')),
                    'fabric_price': money(job_pricing.get('fabric')),
                    'embroidery_price': money(job_pricing.get('embroidery')),
                    'customization_price': money(job_pricing.get('customization')),
                    'tailoring_charges': money(job_pricing.get('tailoring')),
                })
                serializer.is_valid(raise_exception=True)
                job = serializer.save()

                design = garment.get('design') or {}
                # `items` is the old whole-design shortlist; `parts` is what the
                # part picker writes. Both, so an in-flight draft written under
                # either shape confirms with its designs intact.
                draft_items = list(design.get('items') or []) + _part_items_from_draft(design)
                for position, item in enumerate(draft_items):
                    _board_item_from_draft(order, customer, job, item, position,
                                           request.user)

            if has_job_pricing:
                from domains.orders.pricing import recompute_order_totals
                recompute_order_totals(order)

            # Now that the dresses are attached, the workflow can tell whether
            # any of them asks for a measurement. A saree with no petticoat
            # asks for none, and its Measurements stage is skipped rather than
            # left blocking the order forever.
            from domains.orders.services import settle_measurement_stage
            settle_measurement_stage(order)

            create_order_notifications(order, created=True)
            return order

        try:
            order = drafts.confirm(request.user, pk, create_order=build)
        except (ValueError, Exception) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if order is None:
            return Response(
                {'error': 'This draft has already been placed, or no longer exists.'},
                status=status.HTTP_409_CONFLICT)
        return Response(OrderSerializer(OrderRepository.get_by_id(order.pk), context={'request': request}).data,
                        status=status.HTTP_201_CREATED)
