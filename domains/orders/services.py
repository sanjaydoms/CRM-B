import datetime
import random
from crm_api.models import Order, OrderStage, OrderActivity, Tailor, BoutiqueSettings
from crm_api.views import create_order_notifications

class OrderService:
    @staticmethod
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

        today = datetime.date.today().strftime('%y%m%d')
        rand_num = random.randint(1000, 9999)
        order_id = f"T2B-{today}-{rand_num}"
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

        creator_user = user if (user and user.is_authenticated) else None
        OrderActivity.objects.create(
            order=order,
            event_type='ORDER_CREATED',
            user=creator_user,
            metadata={"message": f"Order {order.order_id} created."}
        )

        create_order_notifications(order, created=True)

        if tailor:
            tailor.status = 'Busy'
            tailor.save()
        if master:
            master.status = 'Busy'
            master.save()

        return order
