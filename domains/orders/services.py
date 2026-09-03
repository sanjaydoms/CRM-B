import datetime
import secrets
from django.db import models, transaction
from core.permissions import SUPERVISOR_ROLES
from core.roles import OWNER, resolve_user_role
from crm_api.models import Order, OrderStage, OrderActivity, Tailor, BoutiqueSettings
from core.formatting import format_money
from domains.orders.notifications import create_order_notifications
from domains.orders import workflow


def _generate_order_id():
    today = datetime.date.today().strftime('%y%m%d')
    for _ in range(20):
        candidate = f"T2B-{today}-{secrets.randbelow(9000) + 1000}"
        if not Order.objects.filter(order_id=candidate).exists():
            return candidate
    return f"T2B-{today}-{secrets.token_hex(4)}"


_SETTLED_ORDER_STATUSES = ('Shipped', 'Delivered')


def _jsonable(value):
    from decimal import Decimal
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def refresh_staff_availability(*staff):
    for person in staff:
        if person is None:
            continue

        live = Order.objects.exclude(order_status__in=_SETTLED_ORDER_STATUSES)
        finished = OrderStage.objects.filter(
            stage_key='stitching_completed', status='COMPLETED',
        ).values('order_id')
        stitching = live.filter(tailor=person).exclude(pk__in=finished).exists()
        supervising = live.filter(master=person).exists()

        wanted = 'Busy' if (stitching or supervising) else 'Available'
        if person.status != wanted:
            person.status = wanted
            person.save(update_fields=['status'])


def order_needs_measurements(order):
    """Whether any dress on this order actually asks for a measurement.

    A saree is draped, not fitted. Its whole measurements section is two
    petticoat fields, both hidden unless a petticoat was ordered -- so a
    saree-only order has nowhere to record a measurement, and demanding one
    before a tailor could be assigned deadlocked it permanently: the form never
    asked, so the answer could never be given.

    Asked of the TEMPLATE rather than hardcoding 'saree', and through the same
    visible_when rules the order form renders with. A garment whose measurement
    fields are all conditional is not a special case to be listed here; it is
    simply a garment that, for this spec, asks nothing.
    """
    from core.templates import is_visible

    for job in order.garment_jobs.select_related('template').all():
        section = job.template.sections.filter(key='measurements').first()
        if section is None:
            continue
        spec = job.spec or {}
        if any(is_visible(field, spec) for field in section.fields.all()):
            return True
    return False


def settle_measurement_stage(order):
    """Mark Measurements Completed as SKIPPED when nothing asks for one.

    Called once the garment jobs exist -- the stages are seeded with the order,
    which happens before the dresses are attached, so at seed time there is
    nothing yet to ask. SKIPPED rather than COMPLETED because no measurement was
    taken and the record should not claim one was; prerequisites() treats both
    as settled, so the order moves on either way.

    Only ever touches a stage still sitting at NOT_STARTED, so a boutique that
    has already worked the stage keeps whatever it recorded.
    """
    from django.utils import timezone

    if order_needs_measurements(order):
        return False
    updated = order.stages.filter(
        stage_key='measurements_completed', status='NOT_STARTED',
    ).update(status='SKIPPED', completed_at=timezone.now())
    return bool(updated)


def customer_has_measurements(customer):
    columns = getattr(customer, 'measurements', None)
    if columns and (columns.bust or columns.waist or columns.hips):
        return True
    from apps.catalog.models import GarmentJob
    return GarmentJob.objects.filter(
        order__customer=customer).exclude(measurements={}).exists()


class OrderService:
    @staticmethod
    @transaction.atomic
    def create_order_for_customer(customer, data, user=None, notify=True):
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

        from . import pricing
        _, taxes_dec, total_dec = pricing.totals_from_amounts(
            {k: pricing.to_money(v) for k, v in components.items()},
            pricing.to_money(packaging_handling),
            pricing.to_money(discount))
        taxes = float(taxes_dec)
        total_amount = float(total_dec)

        order_id = _generate_order_id()
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

        if order_stage.status == 'COMPLETED' and new_status == 'COMPLETED':
            return order

        old_status = order_stage.status
        order_stage.status = new_status
        if comments:
            order_stage.comments = comments

        # Naming SOMEBODY ELSE as the performer is a supervisor's call.
        #
        # The dropdown that sets this is Owner/Master only in the interface, and
        # the API took the field from anyone: a tailor who could see the order
        # could post performed_by_id and sign a colleague's name to the work
        # they had just done, or to work they had not. Ignored rather than
        # refused, so the ordinary staff path -- which falls through to the
        # branch below and records the caller -- is unaffected.
        #
        # int() first: only DoesNotExist was caught, so a non-numeric id raised
        # out of IntegerField and surfaced as a 500 carrying the raw exception
        # text back to the caller.
        if performer_id and (user_role == OWNER or user_role in SUPERVISOR_ROLES):
            try:
                order_stage.performed_by = Tailor.objects.get(id=int(performer_id))
            except (Tailor.DoesNotExist, TypeError, ValueError):
                pass
        elif user and user.is_authenticated and getattr(user, 'tailor_profile', None):
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

        from apps.inventory import order_materials
        material_report = order_materials.sync_order_materials(
            order, stage_key, new_status, user=user)

        order.current_stage_key = stage_key
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
            'delivered': 'Delivered' if new_status == 'COMPLETED' else order.order_status,
        }
        previous_order_status = order.order_status
        if stage_key in status_map:
            order.order_status = status_map[stage_key]
        order.save()

        from apps.production.models import ProductionTask
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
                **({"materials": _jsonable(material_report)} if material_report else {}),
            }
        )

        if stage_key in ('stitching_in_progress', 'stitching_completed', 'delivered'):
            refresh_staff_availability(order.tailor, order.master)

        create_order_notifications(
            order,
            created=False,
            status_changed=order.order_status != previous_order_status,
        )
        if new_status in ('COMPLETED', 'SKIPPED'):
            from domains.orders.notifications import notify_next_stage_owners
            notify_next_stage_owners(order)
        return order
