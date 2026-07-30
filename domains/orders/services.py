import datetime
import secrets
from django.db import transaction
from core.roles import OWNER, resolve_user_role
from crm_api.models import Order, OrderStage, OrderActivity, Tailor, BoutiqueSettings
from domains.orders.notifications import create_order_notifications


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


class OrderService:
    @staticmethod
    @transaction.atomic
    def create_order_for_customer(customer, data, user=None):
        tailor_id = data.get('tailor_id')
        tailor = Tailor.objects.filter(id=tailor_id).first() if tailor_id else None

        master_id = data.get('master_id')
        master = Tailor.objects.filter(id=master_id).first() if master_id else None

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

        subtotal = base_price + fabric_price + embroidery_price + customization_price + tailoring_charges + packaging_handling
        taxes = subtotal * 0.05
        total_amount = subtotal + taxes

        order_id = _generate_order_id()
        est_delivery = datetime.date.today() + datetime.timedelta(days=15)

        payment_status = data.get('payment_status', 'Paid')
        advance_paid = 0.0
        amount_paid = 0.0
        if payment_status == 'Paid':
            advance_paid = total_amount
            amount_paid = total_amount
        elif payment_status == 'Partially Paid':
            advance_paid = safe_float(data.get('advance_paid', total_amount * 0.5))
            amount_paid = advance_paid

        has_measurements = hasattr(customer, 'measurements') and (
            customer.measurements.bust or customer.measurements.waist or customer.measurements.hips
        )

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
            taxes=taxes,
            total_amount=total_amount,
            estimated_delivery=est_delivery,
            delivery_method=data.get('delivery_method', 'Direct Pickup'),
            courier_service=data.get('courier_service'),
            tracking_number=data.get('tracking_number'),
            delivery_address=data.get('delivery_address'),
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
            ProductionTask(order=order, title="Pattern Cutting & Drafting", stage_key="pattern_cutting", assigned_to=master, sequence=3, priority="HIGH"),
            ProductionTask(order=order, title="Garment Assembly & Stitching", stage_key="stitching_in_progress", assigned_to=tailor, sequence=4, priority="URGENT"),
            ProductionTask(order=order, title="Hemming & Finishing", stage_key="finishing", assigned_to=tailor, sequence=5, priority="MEDIUM"),
            ProductionTask(order=order, title="Pressing", stage_key="pressing", assigned_to=master or tailor, sequence=6, priority="MEDIUM"),
            ProductionTask(order=order, title="Master Quality Control Inspection", stage_key="master_quality_check", assigned_to=master, sequence=7, priority="HIGH"),
            ProductionTask(order=order, title="Customer Fitting Trial", stage_key="trial_scheduled", assigned_to=master, sequence=8, priority="MEDIUM"),
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
            description=f"Order created for client {customer.first_name} {customer.last_name} (Total: ₹{order.total_amount:.2f})",
            new_value={"order_id": order.order_id, "total_amount": float(order.total_amount)}
        )

        create_order_notifications(order, created=True)

        if tailor:
            tailor.status = 'Busy'
            tailor.save()
        if master:
            master.status = 'Busy'
            master.save()

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

        valid_statuses = {'NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED'}
        if new_status not in valid_statuses:
            raise ValueError(f'Invalid stage status "{new_status}"')

        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        workflow_stages = config.workflow_config
        stage_conf = next((s for s in workflow_stages if s['key'] == stage_key), {})

        user_role = resolve_user_role(user)
        if user_role is None:
            raise ValueError('Sign in to update this order.')

        # The owner can always act; the role list gates staff.
        allowed_roles = stage_conf.get('roles', [])
        if user_role != OWNER and allowed_roles and user_role not in allowed_roles:
            raise ValueError(f'Role {user_role} is not authorized to update {order_stage.stage_name}')

        if stage_key == 'delivered' and new_status == 'COMPLETED':
            qc_stage = order.stages.filter(stage_key='master_quality_check').first()
            if qc_stage and qc_stage.status != 'COMPLETED':
                raise ValueError('Cannot deliver order before Master Quality Check is completed.')

        if stage_key == 'stitching_in_progress' and new_status == 'IN_PROGRESS':
            if not order.tailor:
                raise ValueError('Cannot start stitching. No tailor is assigned to this order.')

        if stage_key == 'assigned_to_tailor' and new_status == 'COMPLETED':
            meas_stage = order.stages.filter(stage_key='measurements_completed').first()
            if meas_stage and meas_stage.status != 'COMPLETED':
                has_measurements = hasattr(order.customer, 'measurements') and (
                    order.customer.measurements.bust or order.customer.measurements.waist or order.customer.measurements.hips
                )
                if not has_measurements:
                    raise ValueError('Cannot assign tailor. Measurements are not completed for this customer.')

        if stage_key == 'trial_scheduled' and new_status == 'COMPLETED':
            stitch_stage = order.stages.filter(stage_key='stitching_completed').first()
            if stitch_stage and stitch_stage.status != 'COMPLETED':
                raise ValueError('Cannot schedule trial before stitching is completed.')

        old_status = order_stage.status
        order_stage.status = new_status
        order_stage.comments = comments

        if performer_id:
            try:
                order_stage.performed_by = Tailor.objects.get(id=performer_id)
            except Tailor.DoesNotExist:
                pass
        elif user and user.is_authenticated and user_role in ['Master', 'Tailor']:
            order_stage.performed_by = getattr(user, 'tailor_profile', None)

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

        order.current_stage_key = stage_key
        all_stages = list(order.stages.all())
        if all(s.status == 'COMPLETED' for s in all_stages):
            order.production_status = 'COMPLETED'
        else:
            order.production_status = 'IN_PROGRESS'

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
            'delivered': 'Delivered'
        }
        if stage_key in status_map:
            order.order_status = status_map[stage_key]
        order.save()

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
                "comments": comments
            }
        )

        if stage_key == 'stitching_in_progress' and new_status == 'IN_PROGRESS' and order.tailor:
            order.tailor.status = 'Busy'
            order.tailor.save()
        elif stage_key == 'stitching_completed' and new_status == 'COMPLETED' and order.tailor:
            order.tailor.status = 'Available'
            order.tailor.save()

        if stage_key == 'delivered' and new_status == 'COMPLETED' and order.master:
            order.master.status = 'Available'
            order.master.save()

        create_order_notifications(order, created=False)
        return order
