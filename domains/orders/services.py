import datetime
import secrets
from django.db import models, transaction
from core.roles import OWNER, resolve_user_role
from crm_api.models import Order, OrderStage, OrderActivity, Tailor, BoutiqueSettings
from core.formatting import format_money
from domains.orders.notifications import create_order_notifications
from domains.orders import workflow


def _generate_order_id():
    """Build a T2B-YYMMDD-NNNN id that is not already taken.

    order_id is unique, and a plain random draw collides often enough at a few
    dozen orders a day to fail the insert (birthday paradox over 9000 slots).
    """
    today = datetime.date.today().strftime('%y%m%d')
    for _ in range(20):
        candidate = f"T2B-{today}-{secrets.randbelow(9000) + 1000}"
        if not Order.objects.filter(order_id=candidate).exists():
            return candidate
    # Fall back to a wider space rather than raising on a very busy day.
    return f"T2B-{today}-{secrets.token_hex(4)}"


# Orders that no longer occupy the person working on them.
_SETTLED_ORDER_STATUSES = ('Shipped', 'Delivered')


def _jsonable(value):
    """Make a material report safe to store in a JSONField.

    Quantities are Decimals all the way through the inventory module, on
    purpose -- floats cannot hold 0.001 of a metre exactly and stock has to
    reconcile. json.dumps refuses them, so they become strings here rather than
    floats, which would reintroduce the very rounding the Decimals avoid.
    """
    from decimal import Decimal
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def refresh_staff_availability(*staff):
    """Recompute Available/Busy from the orders each person is actually on.

    Tailor.status is one global flag with no reference counting, and it used to
    be written by hand at three sites: set Busy when an order was created or
    stitching started, and set Available the moment ONE order's stitching
    completed -- regardless of how many other garments that tailor still had
    open. Finishing one dress advertised them as free for the next while three
    were still on their table, which is how a boutique double-books its best
    person.

    Deriving it from live orders at every write site means the flag cannot
    drift: getting a decrement right in three places requires three correct
    edits, and this requires none.
    """
    for person in staff:
        if person is None:
            continue

        live = Order.objects.exclude(order_status__in=_SETTLED_ORDER_STATUSES)
        # Stitching they have not finished yet. Their part of an order is done
        # once stitching_completed is COMPLETED, which is what the old code
        # meant -- it just applied it to whichever order happened to finish
        # rather than asking across all of them.
        #
        # The subquery is load-bearing. Spelling this as
        # .exclude(stages__stage_key=..., stages__status=...) reads correctly
        # and is wrong: across a multi-valued relation Django does not require
        # the two conditions to hold on the SAME stage row, so it excluded every
        # order that merely has a stitching_completed stage -- which is all of
        # them -- and reported every tailor free.
        finished = OrderStage.objects.filter(
            stage_key='stitching_completed', status='COMPLETED',
        ).values('order_id')
        stitching = live.filter(tailor=person).exclude(pk__in=finished).exists()
        # A master supervises until the garment leaves the building.
        supervising = live.filter(master=person).exists()

        wanted = 'Busy' if (stitching or supervising) else 'Available'
        if person.status != wanted:
            person.status = wanted
            person.save(update_fields=['status'])


def customer_has_measurements(customer):
    """Whether anything has been measured for this customer, anywhere.

    The three columns are the *dress-form* set -- bust, waist, hips -- and they
    are written only by the wizard's CUSTOMER_KEYS map, which translates a
    handful of garment-template keys onto the Customer row. A saree's
    measurement section carries `petticoat_length` and `petticoat_waist` and
    nothing else, so neither key is in that map and all three columns stay NULL
    for a saree-only order.

    The order then stalls at "Cannot assign tailor. Measurements are not
    completed for this customer." -- naming a step the wizard never offered,
    for a garment that has no bust measurement to take. Sarees are ordinary
    work in this business, so this stranded a bread-and-butter flow.

    So the per-garment snapshot counts too: GarmentJob.measurements is what the
    wizard actually captured for the dresses on this order, and a non-empty one
    means somebody did measure something. Kept as one function rather than the
    two copies of the same expression this replaces, which is how the
    definition drifted from what the wizard writes in the first place.
    """
    columns = getattr(customer, 'measurements', None)
    if columns and (columns.bust or columns.waist or columns.hips):
        return True
    # Any dress on any of this customer's orders carrying a real snapshot.
    from apps.catalog.models import GarmentJob
    return GarmentJob.objects.filter(
        order__customer=customer).exclude(measurements={}).exists()


class OrderService:
    @staticmethod
    @transaction.atomic
    def create_order_for_customer(customer, data, user=None, notify=True):
        """Book an order for this customer.

        `notify=False` defers the customer's confirmation message to the caller.
        It exists for one reason: the message names the garments, and the
        garments are rows on the order that some callers create *after* it. The
        draft-confirm path does exactly that, so telling the customer here sent
        them a confirmation for an order that had no garments yet -- and the
        garment helper, correctly finding none, fell back to the customer's
        single garment_type. A two-garment order was announced as one garment.

        The fix is the ordering, not the message: whoever builds the rest of
        the order is the one who knows when it is whole enough to describe.
        """
        # A tailor_id that resolves to nobody used to be dropped in silence and
        # the order booked unstaffed, which surfaces days later as a garment
        # with no one assigned to stitch it. Not supplying one at all is still
        # fine -- staff can be assigned later.
        tailor_id = data.get('tailor_id')
        tailor = Tailor.objects.filter(id=tailor_id).first() if tailor_id else None
        if tailor_id and tailor is None:
            raise ValueError(f'No staff member with id {tailor_id}.')

        master_id = data.get('master_id')
        master = Tailor.objects.filter(id=master_id).first() if master_id else None
        if master_id and master is None:
            raise ValueError(f'No master with id {master_id}.')

        def safe_float(val, default=0.0):
            try:
                return float(val) if val not in (None, '') else default
            except (ValueError, TypeError):
                return default

        base_price = safe_float(data.get('base_price', 0.0))
        fabric_price = safe_float(data.get('fabric_price', 0.0))
        embroidery_price = safe_float(data.get('embroidery_price', 0.0))
        customization_price = safe_float(data.get('customization_price', 0.0))
        tailoring_charges = safe_float(data.get('tailoring_charges', 0.0))
        packaging_handling = safe_float(data.get('packaging_handling', 0.0))

        # This endpoint is the trust boundary for every order-creation path --
        # the wizard, the API, and anything added later -- and nothing checked
        # sign or magnitude before. safe_float turns garbage into 0.0 but passes
        # negatives straight through, so a mistyped base price took the
        # dashboard's revenue below zero, and total_amount is
        # DecimalField(max_digits=10), so anything from 10^8 up died as an
        # unhandled psycopg DataError behind a generic "Failed to submit order".
        discount = safe_float(data.get('discount', 0.0))

        components = {
            'base_price': base_price, 'fabric_price': fabric_price,
            'embroidery_price': embroidery_price,
            'customization_price': customization_price,
            'tailoring_charges': tailoring_charges,
            'packaging_handling': packaging_handling,
            'discount': discount,
        }
        for field, value in components.items():
            if value < 0:
                raise ValueError(f'{field} cannot be negative.')
        del components['discount'], components['packaging_handling']

        # The arithmetic itself -- tax rate, discount ordering, the column
        # ceiling -- lives in domains.orders.pricing and ONLY there. Whatever
        # the client sent for taxes or total_amount is ignored: this recompute
        # is what gets stored, so a manipulated payload can change nothing but
        # its own component inputs, which the caller legitimately owns anyway.
        from . import pricing
        _, taxes_dec, total_dec = pricing.totals_from_amounts(
            {k: pricing.to_money(v) for k, v in components.items()},
            pricing.to_money(packaging_handling),
            pricing.to_money(discount))
        taxes = float(taxes_dec)
        total_amount = float(total_dec)

        order_id = _generate_order_id()
        # The wizard asks for a delivery date per garment, and that date is what
        # the boutique actually promised. It used to be dropped on the floor --
        # every order got today+15 regardless -- and that invented date is the
        # one the customer is shown on the tracking page and told over WhatsApp.
        # A garment quoted for mid-September was being promised three weeks
        # early. today+15 stays as the fallback for callers that supply nothing.
        # Parse here rather than letting Django coerce on save: the order object
        # is handed to create_order_notifications before it is re-read, and that
        # calls .strftime() on this field -- a raw "2026-09-15" from the wizard
        # would crash order creation outright. A malformed date falls back to
        # the estimate instead of taking the order down with it.
        requested_delivery = data.get('estimated_delivery')
        if isinstance(requested_delivery, str):
            try:
                requested_delivery = datetime.date.fromisoformat(requested_delivery)
            except ValueError:
                requested_delivery = None
        est_delivery = requested_delivery or (
            datetime.date.today() + datetime.timedelta(days=15))

        payment_status = data.get('payment_status', 'Paid')
        advance_paid = 0.0
        amount_paid = 0.0
        if payment_status == 'Paid':
            advance_paid = total_amount
            amount_paid = total_amount
        elif payment_status == 'Partially Paid':
            # Clamped to the order. An advance of 150000 against a 31500 order
            # used to be stored verbatim and counted as revenue, while the
            # customer's tracking page read "Balance due Rs0.00" and the
            # delivery message skipped asking for the balance entirely. The
            # wizard's own "Remaining Balance Due" preview clamps with
            # Math.max(0, ...), so it hid the mistake at the moment of entry.
            # Default 0.0, not half the order.
            #
            # `total_amount * 0.5` invented money nobody had received. Combined
            # with the wizard's own `parseFloat(advancePaymentAmount) ||
            # getTotalPrice() / 2` -- where the advance box starts at 0 and
            # clears to 0, so `||` substituted the half -- there was no way to
            # express "nothing paid yet" on a Partially Paid order at all. The
            # boutique's collected-revenue figure counted an advance the
            # customer had not handed over, and the customer's tracking page
            # showed a balance smaller than what they actually owed.
            advance_paid = min(
                max(safe_float(data.get('advance_paid', 0.0)), 0.0),
                total_amount)
            amount_paid = advance_paid

        has_measurements = customer_has_measurements(customer)

        order = Order.objects.create(
            order_id=order_id,
            customer=customer,
            tailor=tailor,
            master=master,
            payment_status=payment_status,
            order_status='Received',
            base_price=base_price,
            fabric_price=fabric_price,
            embroidery_price=embroidery_price,
            customization_price=customization_price,
            tailoring_charges=tailoring_charges,
            packaging_handling=packaging_handling,
            discount=discount,
            taxes=taxes,
            total_amount=total_amount,
            estimated_delivery=est_delivery,
            delivery_method=data.get('delivery_method', 'Direct Pickup'),
            courier_service=data.get('courier_service'),
            tracking_number=data.get('tracking_number'),
            delivery_address=data.get('delivery_address'),
            special_instructions=data.get('custom_requirements') or '',
            advance_paid=advance_paid,
            amount_paid=amount_paid,
            current_stage_key='measurements_completed' if has_measurements else 'created',
            production_status='IN_PROGRESS'
        )

        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        workflow_stages = config.workflow_config
        from django.utils import timezone

        stages_to_create = []
        for index, s_conf in enumerate(workflow_stages):
            s_key = s_conf['key']
            s_name = s_conf['name']
            s_status = 'NOT_STARTED'
            started_at = None
            completed_at = None

            if s_key == 'created':
                s_status = 'COMPLETED'
                started_at = timezone.now()
                completed_at = timezone.now()
            elif s_key == 'measurements_completed' and has_measurements:
                s_status = 'COMPLETED'
                started_at = timezone.now()
                completed_at = timezone.now()

            stages_to_create.append(OrderStage(
                order=order,
                stage_key=s_key,
                stage_name=s_name,
                status=s_status,
                started_at=started_at,
                completed_at=completed_at,
                sequence=index,
                sla_hours=s_conf.get('sla_hours', 24)
            ))

        OrderStage.objects.bulk_create(stages_to_create)

        # Step 5: Task Engine Integration - Create Production Tasks for Order
        from apps.production.models import ProductionTask
        from apps.activities.models import UniversalActivity

        tasks_to_create = [
            ProductionTask(order=order, title="Verify Measurements & Requirements", stage_key="measurements_completed", assigned_to=master or tailor, sequence=1, priority="HIGH"),
            ProductionTask(order=order, title="Fabric & Lining Selection Approval", stage_key="fabric_confirmed", assigned_to=master or tailor, sequence=2, priority="MEDIUM"),
            ProductionTask(order=order, title="Pattern Cutting & Drafting", stage_key="pattern_cutting", assigned_to=master or tailor, sequence=3, priority="HIGH"),
            ProductionTask(order=order, title="Garment Assembly & Stitching", stage_key="stitching_in_progress", assigned_to=tailor, sequence=4, priority="URGENT"),
            ProductionTask(order=order, title="Hemming & Finishing", stage_key="finishing", assigned_to=tailor, sequence=5, priority="MEDIUM"),
            ProductionTask(order=order, title="Pressing", stage_key="pressing", assigned_to=master or tailor, sequence=6, priority="MEDIUM"),
            ProductionTask(order=order, title="Master Quality Control Inspection", stage_key="master_quality_check", assigned_to=master or tailor, sequence=7, priority="HIGH"),
            ProductionTask(order=order, title="Customer Fitting Trial", stage_key="trial_scheduled", assigned_to=master or tailor, sequence=8, priority="MEDIUM"),
            ProductionTask(order=order, title="Final Packaging & Dispatch Preparation", stage_key="ready_for_delivery", assigned_to=master or tailor, sequence=9, priority="MEDIUM"),
        ]
        ProductionTask.objects.bulk_create(tasks_to_create)

        creator_user = user if (user and user.is_authenticated) else None
        OrderActivity.objects.create(
            order=order,
            event_type='ORDER_CREATED',
            user=creator_user,
            metadata={"message": f"Order {order.order_id} created with initial production tasks."}
        )

        UniversalActivity.objects.create(
            user=creator_user,
            user_name_snapshot=creator_user.get_full_name() or creator_user.username if creator_user else "System",
            module="orders",
            entity_type="Order",
            entity_id=order.order_id,
            action="ORDER_CREATED",
            title=f"New Order {order.order_id}",
            description=(f"Order created for client {customer.first_name} "
                         f"{customer.last_name} (Total: {format_money(order.total_amount)})"),
            new_value={"order_id": order.order_id, "total_amount": float(order.total_amount)}
        )

        if notify:
            create_order_notifications(order, created=True)

        refresh_staff_availability(tailor, master)

        return order

    @staticmethod
    @transaction.atomic
    def transition_order_stage(order, stage_key, new_status, comments='', performer_id=None, user=None, files=None, request=None):
        import uuid
        from django.utils import timezone
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        try:
            order_stage = order.stages.get(stage_key=stage_key)
        except OrderStage.DoesNotExist:
            raise ValueError(f'Unknown stage "{stage_key}" for order {order.order_id}')

        # One state machine, asked one question: may this order go here, now,
        # at the hands of this user, with the data it currently holds?
        #
        # This replaced five ad-hoc `if stage_key ==` guards, each added after
        # someone was burned by one particular stage. Everything nobody had
        # been burned by yet was permitted -- which is how an order in pattern
        # cutting could be moved straight to Ready for Dispatch with a 200.
        # See domains/orders/workflow.py for the rules and why each exists.
        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        workflow_stages = config.workflow_config

        user_role = resolve_user_role(user)
        if user_role is None:
            raise ValueError('Sign in to update this order.')

        workflow.check_transition(
            order, order_stage, new_status,
            config=workflow_stages,
            role=user_role,
            owner_role=OWNER,
        )

        # Re-completing a stage that is already COMPLETED is a no-op, not an
        # error: a double-click, a retried POST or a stale browser tab must not
        # consume material twice, write a second activity event or send the
        # customer a second message. Returning before any side effect runs is
        # what makes the transition idempotent under retry.
        if order_stage.status == 'COMPLETED' and new_status == 'COMPLETED':
            return order

        old_status = order_stage.status
        order_stage.status = new_status
        # Only when there is something to write. This assigned unconditionally,
        # and update_status calls through with no comments at all -- so a tailor
        # who submitted a completion note and then touched the status dropdown
        # had that note blanked on the very stage row the Master reads.
        if comments:
            order_stage.comments = comments

        if performer_id:
            try:
                order_stage.performed_by = Tailor.objects.get(id=performer_id)
            except Tailor.DoesNotExist:
                pass
        elif user and user.is_authenticated and getattr(user, 'tailor_profile', None):
            # Test for the profile, not for two role names.
            #
            # `user_role in ['Master', 'Tailor']` excluded all seven specialist
            # roles, so when a Cutting Master or a Pressing Staff advanced their
            # own stage nothing recorded who did it -- and the performer
            # dropdown that would let someone set it by hand is Owner/Master
            # only. The stage history simply had a blank where the person who
            # did the work should be, on exactly the stages the specialists own.
            #
            # It also used to assign None for an Owner acting on the stage,
            # CLEARING a performer a tailor had already earned. Only writing
            # when there is a profile to write leaves that record alone.
            order_stage.performed_by = user.tailor_profile

        if new_status == 'IN_PROGRESS' and old_status != 'IN_PROGRESS':
            order_stage.started_at = timezone.now()
        elif new_status == 'COMPLETED' and old_status != 'COMPLETED':
            if not order_stage.started_at:
                order_stage.started_at = timezone.now()
            order_stage.completed_at = timezone.now()
            delta = order_stage.completed_at - order_stage.started_at
            order_stage.duration_seconds = int(delta.total_seconds())

        if files:
            image_urls = list(order_stage.attachments)
            for f in files:
                path = f"stage_attachments/order_{order.id}/{uuid.uuid4()}_{f.name}"
                saved_path = default_storage.save(path, ContentFile(f.read()))
                if request:
                    image_urls.append(request.build_absolute_uri(default_storage.url(saved_path)))
                else:
                    image_urls.append(default_storage.url(saved_path))
            order_stage.attachments = image_urls

        order_stage.save()

        # Materials follow production. Reserved when the fabric is confirmed,
        # consumed when the garment is stitched, released and reconciled when it
        # goes out. Without this the order form's material choices never reached
        # the stock ledger at all, and a delivered order left the store room's
        # figures exactly as they were before it was taken.
        #
        # Imported here rather than at module level: apps.inventory imports
        # crm_api.models, and this module is reached from there.
        from apps.inventory import order_materials
        material_report = order_materials.sync_order_materials(
            order, stage_key, new_status, user=user)

        order.current_stage_key = stage_key
        # Ask the database, not order.stages.all(). OrderRepository.base_queryset
        # prefetches 'stages', so on an order loaded through the API that .all()
        # returns the prefetch cache -- captured before order_stage.save() above,
        # and never refreshed. The stage just completed still reads NOT_STARTED
        # in it, so the "everything done" test failed on the very transition
        # that made it true and production_status was pinned to IN_PROGRESS for
        # the life of the order, including after delivery. A fresh queryset
        # (.exclude builds one) bypasses the cache and costs one COUNT.
        #
        # SKIPPED counts as settled, not pending: skipping is a deliberate "this
        # garment needs no Maggam work" and the ladder allows delivery over it,
        # so leaving it to block COMPLETED would strand every order that used
        # the Skip Stage button.
        pending = order.stages.exclude(status__in=['COMPLETED', 'SKIPPED']).exists()
        order.production_status = 'IN_PROGRESS' if pending else 'COMPLETED'

        status_map = {
            'created': 'Received',
            'measurements_completed': 'Confirmed',
            'fabric_confirmed': 'Confirmed',
            'pattern_cutting': 'Design & Creation',
            'maggam_work': 'Design & Creation',
            'assigned_to_tailor': 'Design & Creation',
            'stitching_in_progress': 'Design & Creation',
            'stitching_completed': 'Quality Check',
            'finishing': 'Quality Check',
            'pressing': 'Quality Check',
            'master_quality_check': 'Ready for Dispatch' if new_status == 'COMPLETED' else 'Quality Check',
            'trial_scheduled': 'Ready for Dispatch',
            'trial_completed': 'Ready for Dispatch',
            'ready_for_delivery': 'Ready for Dispatch',
            # Mirrors master_quality_check above: only a COMPLETED delivery
            # stage means the garment is with the customer. The bare 'Delivered'
            # this replaces was written for any new_status, so starting or
            # pausing the stage announced a delivery that had not happened --
            # to the customer, on the tracking page, in a message asking for the
            # balance. Leaving the status untouched is right for the other
            # transitions: starting delivery is not a change of order state, it
            # is someone picking the parcel up.
            'delivered': 'Delivered' if new_status == 'COMPLETED' else order.order_status,
        }
        previous_order_status = order.order_status
        if stage_key in status_map:
            order.order_status = status_map[stage_key]
        order.save()

        # Keep the production task in step with its stage. Nine of these are
        # written per order and nothing ever touched them again, so
        # /api/production/tasks/ answered with every task NOT_STARTED on an
        # order that had already been delivered. One lookup inside the atomic
        # block every stage change already passes through is enough to make the
        # rows honest -- and the alternative, deleting them, would throw away
        # two working ViewSets.
        from apps.production.models import ProductionTask
        # ProductionTask has its own vocabulary -- PENDING where a stage says
        # NOT_STARTED, BLOCKED where a stage says PAUSED -- so translate rather
        # than copying the string across and writing a value the field's own
        # choices do not allow.
        task_status = {
            'NOT_STARTED': 'PENDING',
            'IN_PROGRESS': 'IN_PROGRESS',
            'COMPLETED': 'COMPLETED',
            'SKIPPED': 'SKIPPED',
            'PAUSED': 'BLOCKED',
        }.get(new_status)
        task = ProductionTask.objects.filter(order=order, stage_key=stage_key).first()
        if task is not None and task_status:
            task.status = task_status
            fields = ['status']
            performer = order_stage.performed_by
            if performer is not None and task.assigned_to_id != performer.id:
                task.assigned_to = performer
                fields.append('assigned_to')
            task.save(update_fields=fields)

        creator = user if (user and user.is_authenticated) else None
        OrderActivity.objects.create(
            order=order,
            event_type='STAGE_TRANSITION',
            user=creator,
            metadata={
                "stage_key": stage_key,
                "stage_name": order_stage.stage_name,
                "old_status": old_status,
                "new_status": new_status,
                "comments": comments,
                # What this transition did to stock, per garment, recorded with
                # the transition that caused it. "Why did six metres leave?" is
                # answerable from the ledger via StockMovement.garment_job; this
                # is the same fact from the order's side, so the story reads
                # from either end. Omitted when the stage moves no material.
                **({"materials": _jsonable(material_report)} if material_report else {}),
            }
        )

        # Both people, on every stage change that could free either of them.
        # Derived, so completing one garment no longer advertises a tailor as
        # free while their other orders are still open.
        if stage_key in ('stitching_in_progress', 'stitching_completed', 'delivered'):
            refresh_staff_availability(order.tailor, order.master)

        create_order_notifications(
            order,
            created=False,
            status_changed=order.order_status != previous_order_status,
        )
        # Only when this transition actually finished something. Starting or
        # pausing a stage does not move the order on, and announcing a queue
        # arrival on every keystroke is how a notification list stops being read.
        if new_status in ('COMPLETED', 'SKIPPED'):
            from domains.orders.notifications import notify_next_stage_owners
            notify_next_stage_owners(order)
        return order
