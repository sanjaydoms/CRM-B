import json
import os
import secrets
import uuid
from decimal import Decimal

from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import viewsets, status, views
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
from domains.orders.services import (
    OrderService, fail_quality_check, refresh_staff_availability, reopen_order_stage,
)

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
            # Normalize on the way in. LoginView lowercases the whole input
            # before matching, and these lookups are case-sensitive, so a
            # Master whose address the owner typed with any capital letter got
            # an account that looked correct in Manage Tailors and could never
            # be signed in to -- the credentials were valid and nothing matched
            # them.
            tailor.email = tailor.email.strip().lower()

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
                if existing.email != tailor.email:
                    existing.email = tailor.email
                    existing.username = self._unique_username(
                        tailor.email.split('@')[0], exclude_pk=existing.pk)
                    existing.save(update_fields=['email', 'username'])
                return

            user = User.objects.filter(email__iexact=tailor.email).first()
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
            # Link to tailor
            if tailor.user != user:
                tailor.user = user
                tailor.save()

    @staticmethod
    def _unique_username(base, exclude_pk=None):
        """A free username derived from `base`, lowercased to match login."""
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
        # Captured before save(), because after it the instance carries the new
        # values and there is nothing left to compare against.
        old_tailor_id = serializer.instance.tailor_id
        old_master_id = serializer.instance.master_id
        old_tailor = serializer.instance.tailor
        old_master = serializer.instance.master

        order = serializer.save()
        self._reconcile_payment(order, serializer.validated_data)

        if old_status != order.order_status:
            create_order_notifications(order, created=False)

        # Reassignment used to change one column and nothing else.
        #
        # This method did only save(), _reconcile_payment and a status
        # notification, so moving an order to a different tailor left three
        # things pointing at the person who no longer has it:
        #
        #   * Tailor.status -- the departing tailor still read Busy with nothing
        #     on their table, the new one still read Available with a dress to
        #     sew. Those two badges are what the owner picks staff by, so the
        #     next order went to the wrong person for the stated reason.
        #   * ProductionTask.assigned_to -- /api/production/tasks/ went on
        #     naming the old tailor for work they no longer had.
        #   * Nobody was told. assign_stage writes a notification when it hands
        #     over a single stage; handing over the whole order wrote none.
        #
        # refresh_staff_availability derives the flag from live orders, which is
        # exactly why its docstring says to call it at every write site.
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
                        # The person's own role, not the literal "Tailor" --
                        # see the banner in domains/orders/notifications.py.
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

    #: Every status this endpoint will accept. Mirrors Order.order_status's own
    #: documented values and the dropdown the UI offers. Without it the endpoint
    #: stored any string it was handed.
    CLIENT_STATUSES = frozenset({
        'Received', 'Confirmed', 'Stylist Review', 'Design & Creation',
        'Quality Check', 'Ready for Dispatch', 'Shipped', 'Delivered',
    })

    @action(detail=True, methods=['PATCH'], url_path='master-verification')
    def master_verification(self, request, pk=None):
        """The Master's production checklist.

        It needs its own route because the checklist is the ONE feature built
        exclusively for a Master -- rendered on both their screens behind
        `currentUser.role === 'Master'` -- and it was saved with a plain PATCH
        of the order. DRF resolves that to `partial_update`, which is in
        neither STAFF_ORDER_ACTIONS nor SUPERVISOR_ORDER_ACTIONS, so every
        checkbox 403'd for the only role allowed to see it.

        Widening `partial_update` for supervisors was the tempting fix and the
        wrong one: it is the same action that carries payment_status,
        amount_paid and advance_paid, so it would have handed a Master the
        money fields to fix a checklist. A narrow action writes exactly the one
        JSON column and nothing else.
        """
        order = self.get_object()
        checks = request.data.get('master_verification')
        if not isinstance(checks, dict):
            return Response({'error': 'master_verification must be an object.'},
                            status=status.HTTP_400_BAD_REQUEST)
        # Merged into what is already stored, not substituted for it.
        #
        # Both screens that render this checklist build their payload by
        # spreading the order out of the dashboard's `ordersList`, which only
        # refreshes on a full fetchDashboardAndConfig. So ticking a second box
        # posts a copy of the object as it was when the list was last loaded --
        # without the first tick. A replacing write then erased it, and the
        # Master watched earlier ticks come undone as they worked. What was
        # stored afterwards was not what anyone had verified, which for a
        # quality checklist is worse than losing it.
        #
        # Fixed here rather than in the two React call sites because this is the
        # single endpoint both post to: one edit, and a third screen added later
        # inherits the correct behaviour. Unticking still works -- the frontend
        # sends the key with False, and False overwrites True.
        merged = dict(order.master_verification or {})
        merged.update({str(k): bool(v) for k, v in checks.items()})
        # Booleans only: this is a checklist, not a free-form store on the order.
        order.master_verification = merged
        order.save(update_fields=['master_verification'])
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)

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

        # An allowlist, because this wrote whatever string it was given. A
        # tailor could PATCH {'status': 'Totally Made Up'} and that became the
        # order's status, on the customer's tracking page, with a customer
        # notification behind it.
        if new_status not in self.CLIENT_STATUSES:
            return Response(
                {'error': f"Unknown order status '{new_status}'.",
                 'allowed': sorted(self.CLIENT_STATUSES)},
                status=status.HTTP_400_BAD_REQUEST)

        stage_key = self.STATUS_TO_STAGE.get(new_status)
        if not stage_key:
            # No stage maps to this status, so there is no workflow rule to
            # enforce -- which is exactly why this branch needs its own role
            # check. update_status is in STAFF_ORDER_ACTIONS so that a tailor
            # can drive their own stages, and every status that maps to a stage
            # is gated by that stage's role list. The ones that map to nothing
            # were gated by nothing at all: a tailor could set 'Shipped' and
            # send the customer the courier-and-tracking message. Moving an
            # order without doing the work is a supervisor's call.
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

        # A client-facing status spans several production stages -- 'Design &
        # Creation' covers cutting, assignment and both stitching stages -- and
        # it maps to the one that says that band is finished. So reaching it
        # means completing everything up to it, not landing on it.
        #
        # Each hop goes through the workflow engine, so the ordering rules, the
        # role checks, the inventory side effects and the audit trail all apply
        # to every stage rather than only to the last one. That keeps the stage
        # history truthful: the owner moving an order to Quality Check really
        # did assert that the stitching is done.
        #
        # The whole walk is one transaction. Without it a hop refused halfway --
        # a tailor who may complete stitching but not the Master's cutting --
        # would leave the order advanced part of the way with an error on the
        # screen, which is precisely the half-applied state the state machine
        # exists to prevent.
        # Crucially, the walk covers only the band this status names -- the
        # stages after the previous status's landing stage. It does NOT complete
        # everything from the beginning.
        #
        # That distinction is the whole guarantee. A walk from wherever the
        # order happens to be would let an owner choose 'Delivered' on a fresh
        # order and have the entire production record completed in one click,
        # quality check included: the original bug again, now with the stages
        # marked done rather than left blank, which is worse because the record
        # then *claims* the garment was inspected. Anything earlier that is
        # still outstanding is refused by the workflow engine, naming it.
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

        # One business action, two truthful transitions.
        #
        # This posted stitching_completed directly, so stitching_in_progress sat
        # at NOT_STARTED forever on every order that used the button -- which is
        # every order. The stage history then could not answer when stitching
        # started, how long it took, or who began it, and the state machine now
        # rejects the jump outright rather than recording a sequence that never
        # happened. Whether the tailor sees one button or two is a UI question;
        # the history underneath has to be true either way.
        # Starting before completing matters even when both happen in the same
        # request: a tailor who pressed "Start In-Progress" earlier already has
        # a real started_at, and re-entering IN_PROGRESS leaves it alone, so
        # the recorded duration stays true. A tailor who never pressed it gets
        # a start stamped now, which is the moment the system actually learned
        # of the work -- honest, if less precise.
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

        serializer = OrderSerializer(OrderRepository.get_by_id(order.pk))
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

        # The stage must be one this order actually has.
        #
        # `stage` was free text written straight into the row -- unlike
        # assign_stage immediately below, which checks. A typo silently created
        # a history entry for a stage that does not exist, invisible on every
        # screen that reads stages by key, and this action is in
        # STAFF_ORDER_ACTIONS so any production account could do it.
        if not order.stages.filter(stage_key=stage).exists():
            return Response({'error': f"This order has no stage '{stage}'."},
                            status=status.HTTP_404_NOT_FOUND)

        # Who did it comes from the signed-in user, not the request body.
        # `completed_by` defaulted to the literal 'Boutique Staff' and was
        # otherwise whatever the caller typed, so the one field recording
        # accountability for a quality review was self-declared.
        performer = (request.user.get_full_name() or request.user.username
                     or 'Boutique Staff')

        # Atomic, because the delete comes first.
        #
        # This replaces the previous review for the stage, and the delete used
        # to commit on its own: if the create then failed -- a rejected upload,
        # a column overflow -- the earlier review's comments and evidence
        # photograph were gone with nothing written in their place. That is the
        # record of what was inspected, on the stage whose whole purpose is
        # inspection.
        with transaction.atomic():
            OrderStageHistory.objects.filter(order=order, stage=stage).delete()
            OrderStageHistory.objects.create(
                order=order,
                stage=stage,
                comments=comments,
                image=image,
                completed_by_name=performer,
            )

        return Response(OrderSerializer(order).data)

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

        # int() first: id is an AutoField, so a non-numeric value reaches the
        # database as a bad cast and surfaces as a 500 rather than the 400 it
        # is. The same guard is already written for message_id further up this
        # file; assign_stage never got it.
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

        # Tell the person, and leave a record. Every other meaningful order
        # event does both -- creation notifies, every transition writes an
        # OrderActivity -- and OrderActivity's own field comment lists
        # 'ASSIGNMENT' as an expected event_type that nothing ever wrote. Being
        # handed work is exactly the event a staff member needs to hear about.
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

        # Keep the production queue naming the right person. transition_stage
        # already moves the matching ProductionTask alongside its stage; an
        # assignment left the task pointing at whoever the order was created
        # with until somebody started the work.
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
            serializer = OrderSerializer(OrderRepository.get_by_id(updated_order.pk))
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['POST'], url_path='reopen-stage')
    def reopen_stage(self, request, pk=None):
        """A supervisor reverses a settled stage, with a reason, on the record.

        In STAFF_ORDER_ACTIONS so the request reaches the service, where the
        real gate lives: workflow.check_reopen refuses everyone but the owner
        and the Master, names the frontier rule, and nothing is written on a
        refusal.
        """
        order = self.get_object()
        try:
            reopen_order_stage(
                order,
                request.data.get('stage_key'),
                user=request.user,
                reason=request.data.get('reason'),
                request=request,
            )
        except PermissionError as pe:
            return Response({'error': str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            OrderSerializer(OrderRepository.get_by_id(order.pk)).data,
            status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='fail-qc')
    def fail_qc(self, request, pk=None):
        """Quality check rejects the garment: reopen the stitching band.

        First-class rework, not a rollback -- see fail_quality_check for the
        rules. The QC Master can invoke it directly; the service checks roles.
        """
        order = self.get_object()
        try:
            fail_quality_check(
                order,
                user=request.user,
                reason=request.data.get('reason'),
                request=request,
            )
        except PermissionError as pe:
            return Response({'error': str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            OrderSerializer(OrderRepository.get_by_id(order.pk)).data,
            status=status.HTTP_200_OK)

class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by('-created_at')
    serializer_class = NotificationSerializer
    # Not the default RolePermission: see OwnNotifications. get_queryset scopes
    # every row to the signed-in user, so there is nothing here a role check
    # would protect -- and the default refused mark-all-read to every
    # non-Owner, which took the whole app down when they opened the bell.
    permission_classes = [OwnNotifications]

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
            # A blank recipient_email means "the whole role", not "nobody".
            # Queue arrivals are addressed that way on purpose -- picking one
            # QC Master in a boutique with two is the manual assignment the
            # queue exists to replace -- and every staff member has an email,
            # so an equality filter alone hid every role-addressed notice from
            # all of them. Personally-addressed ones still reach only their
            # person.
            from django.db.models import Q
            qs = qs.filter(Q(recipient_email=email) | Q(recipient_email='')
                           | Q(recipient_email__isnull=True))
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

        # distinct: the same stages join that scopes a tailor multiplies each
        # order by its fifteen stage rows, so an unqualified Count made every
        # status bucket fifteen times too big on their dashboard.
        status_counts = orders.values('order_status').annotate(count=Count('id', distinct=True))

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


def _board_item_from_draft(order, customer, job, item, position, user):
    """Carry one draft-time shortlist entry onto the confirmed order's board.

    The board is created lazily and once per order -- it stays the single,
    order-level, customer-owned board it has always been. What is new is that
    each item records the garment it was chosen for, so a two-garment order's
    two shortlists cannot merge into one undifferentiated pile.
    """
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
        position=position,
    )


class OrderDraftViewSet(viewsets.ViewSet):
    """Orders being written. Scoped to the person writing them.

    Not a ModelViewSet, and not registered anywhere near OrderViewSet, because
    a draft is not an order: it has no stages, no material plan, no invoice and
    no tracking link, and nothing that reads orders can reach it. See
    domains/orders/drafts.py.
    """

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
            # 409, not 400: the request is well formed, it is simply based on a
            # copy of the order that has since moved on. The interface needs to
            # tell the person in the older tab to reload rather than to correct
            # a field.
            return Response({'error': str(conflict)}, status=status.HTTP_409_CONFLICT)
        if draft is None:
            return Response({'error': 'No such draft.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._serialise(draft))

    def destroy(self, request, pk=None):
        """Abandon it, explicitly. The customer, if any, is left alone."""
        removed = drafts.abandon(request.user, pk)
        if not removed:
            return Response({'error': 'No such draft.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['POST'], url_path='confirm')
    def confirm(self, request, pk=None):
        """Turn this draft into a real order, atomically, once.

        Everything happens inside one transaction: the client, the order, its
        production stages, its garments and their material lines, and the
        deletion of the draft. Either the boutique has an order and no draft, or
        it has its draft back and nothing else changed. There is no state in
        between to clean up.

        Retrying is safe because the draft is the token. A double-click, a
        network retry or a refresh that re-fires the request finds the draft
        already spent and is told so, rather than booking the same garments a
        second time.
        """
        from apps.catalog.models import GarmentTemplate
        from apps.catalog.serializers import GarmentJobSerializer

        def build(draft):
            payload = draft.payload or {}
            customer = drafts.customer_for(draft, payload)

            # Blank boxes are not zeroes. The wizard sends every measurement
            # field it renders, most of them empty, and a DecimalField refuses
            # '' outright -- which took the whole confirmation down with a 500
            # rather than skipping a number nobody typed.
            measurements = {
                key: value for key, value in (payload.get('measurements') or {}).items()
                if value not in (None, '')
            }
            if measurements:
                Measurement.objects.update_or_create(
                    customer=customer, defaults=measurements)

            # The wizard's own shape, mapped here rather than in the browser:
            # the draft stores what the form holds, and this is the one place
            # that knows what an Order needs. Keeping the translation server-side
            # means a stale tab cannot post a differently-shaped order.
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

            # Per-garment pricing, when the wizard sent it. Each garment carries
            # its own components and the ORDER's components become their sums --
            # this is what stops a Blouse + Lehenga order being priced as
            # whichever garment came first. Drafts written before pricing moved
            # per-garment have no `pricing` key on any garment and fall back to
            # the flat `prices` block exactly as before, so an in-flight draft
            # still confirms at the numbers its owner saw.
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

            # The earliest date any dress on this order is due: an order is only
            # as early as its slowest-promised garment is late.
            due = sorted(
                d for d in ((g.get('values') or {}).get('delivery_date')
                            for g in (payload.get('garments') or []))
                if d)

            # taxes/total are NOT passed: the service recomputes them through
            # domains.orders.pricing from these components, and what the client
            # believed the total was has no bearing on what is stored.
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
                # On 'Paid' the service sets advance = the total IT computed;
                # nothing the client sends matters. Only a partial advance is
                # client data, and the service clamps it to the final total.
                'advance_paid': 0 if full_payment else money(payment.get('advance')),
                'custom_requirements': payload.get('special_instructions')
                                       or payload.get('custom_requirements') or '',
                'estimated_delivery': due[0] if due else None,
                'delivery_method': delivery.get('method') or 'Direct Pickup',
                'courier_service': delivery.get('courier'),
                'tracking_number': delivery.get('tracking'),
                'delivery_address': delivery.get('address'),
                # Held back until the garments exist -- see below.
            }, user=request.user, notify=False)

            for index, garment in enumerate(garments):
                template = GarmentTemplate.objects.filter(
                    pk=garment.get('template')).first()
                if template is None:
                    # Skipping used to be silent. Tolerable when a job was only
                    # a spec; not now that it is a line on the bill -- dropping
                    # a PRICED garment would charge the customer for fewer
                    # dresses than the order totals were computed from. A
                    # corrupt draft is refused, not partially billed.
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

                # The garment's shortlist, chosen before this customer existed.
                # It becomes a real board item here, against the real customer,
                # attached to the job it was chosen for -- which is what makes
                # the personalisation survive Confirm on the correct garment.
                design = garment.get('design') or {}
                for position, item in enumerate(design.get('items') or []):
                    _board_item_from_draft(order, customer, job, item, position,
                                           request.user)

            if has_job_pricing:
                # The consistency step, and the precedent: order totals ARE the
                # garment jobs' sums, written by the one pricing path. Numerically
                # a no-op here (the components above came from the same payload),
                # but any future edit to a job's price goes through this same
                # function, so the bill can never drift from the dresses on it.
                # Skipped for flat-priced drafts: their jobs are all-zero, and
                # recomputing would zero a legitimately priced order.
                from domains.orders.pricing import recompute_order_totals
                recompute_order_totals(order)

            # Only now. The confirmation names every garment on the order, so it
            # cannot be sent until every garment is on it. Still inside the same
            # transaction, and send_customer_message defers actual delivery to
            # on_commit -- so the customer hears about an order that exists, is
            # complete, and was not rolled back.
            create_order_notifications(order, created=True)
            return order

        try:
            order = drafts.confirm(request.user, pk, create_order=build)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if order is None:
            # Already confirmed, or never this user's. Either way there is no
            # order to make from it now, and saying so is better than making a
            # second one.
            return Response(
                {'error': 'This draft has already been placed, or no longer exists.'},
                status=status.HTTP_409_CONFLICT)
        return Response(OrderSerializer(OrderRepository.get_by_id(order.pk)).data,
                        status=status.HTTP_201_CREATED)
