
from decimal import Decimal

from crm_api.models import Notification
from domains.orders.garments import garment_label, garment_names
from domains.orders.emails import send_order_confirmation, send_stage_update_email
from domains.orders.messaging import send_customer_message
from domains.orders.tracking import tracking_url



def create_order_notifications(order, created=False, status_changed=True, stage_name=None, stage_key=None):
    client_name = f"{order.customer.first_name} {order.customer.last_name}"
    client_email = order.customer.email_address
    
    if created:
        Notification.objects.create(
            title=f"New Order Received: {order.reference}",
            message=f"A new custom order has been received for client {client_name}.",
            recipient_role="Owner"
        )
        confirmation = (
            f"Dear {order.customer.first_name}, we have received your order {order.reference}! "
            f"We will update you as it progresses."
        )
        Notification.objects.create(
            title=f"Order Confirmed: {order.reference}",
            message=confirmation,
            recipient_role="Customer",
            recipient_email=client_email
        )
        due = order.estimated_delivery.strftime('%d %b %Y') if order.estimated_delivery else 'to be confirmed'
        send_customer_message(
            order,
            'order_confirmation',
            f"{confirmation}\n"
            f"{'Garments' if len(garment_names(order)) > 1 else 'Garment'}: "
            f"{garment_label(order)}\n"
            f"Expected delivery: {due}\n"
            f"Track your order: {tracking_url(order)}",
        )
        # The third channel. The Notification row above is a dashboard feed the
        # customer never sees, and send_customer_message needs a phone number;
        # a customer who gave only an email had no way of hearing from us at
        # all. Queued on commit -- see domains/orders/emails.py.
        send_order_confirmation(order)
        if order.master:
            Notification.objects.create(
                title=f"New Assignment: {order.reference}",
                message=f"Order {order.reference} for client {client_name} has been assigned to you as Supervising Master.",
                recipient_role=order.master.role,
                recipient_email=order.master.user.email if order.master.user else None
            )
        if order.tailor:
            Notification.objects.create(
                title=f"New Stitching Task: {order.reference}",
                message=f"Order {order.reference} has been assigned to you for stitching.",
                recipient_role=order.tailor.role,
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )
    else:
        # Fifteen production stages map onto six customer-facing statuses, so
        # most transitions leave the status exactly where it was. Announcing it
        # again on every stage gave the owner four identical "Ready for
        # Dispatch" rows, the customer three "Quality Check" ones, and the
        # tailor the same stitching task four times -- measured on one order
        # walked from Received to Delivered. Only a change is news. The
        # per-stage handover is notify_next_stage_owners' job, not this one's.
        status = order.order_status
        display_stage = stage_name or status

        s_key = (stage_key or getattr(order, 'current_stage_key', '') or '').lower()
        s_name = (stage_name or '').lower()
        msg_template = 'stage_update'

        # Step 1: Measurement completed
        if s_key == 'measurements_completed' or s_name == 'measurements completed':
            msg_template = 'measurement_completed'
            cust_msg = f"Your measurements for order {order.reference} have been completed successfully! Our studio is now proceeding with crafting your outfit."
        # Step 2: Product ready (stitching completed / quality check)
        elif s_key in ('stitching_completed', 'master_quality_check') or s_name in ('stitching completed', 'master quality check'):
            msg_template = 'product_ready'
            cust_msg = f"Your outfit for order {order.reference} is ready! Stitching and quality inspection are completed."
        # Step 3: TryOn step (trial scheduled / completed)
        elif s_key in ('trial_scheduled', 'trial_completed') or 'trial' in s_name or 'tryon' in s_name:
            msg_template = 'tryon_step'
            cust_msg = f"Your outfit for order {order.reference} is ready for your Try-On fitting! Please visit our studio for your trial."
        # Step 4: Ready for Delivery section
        elif s_key in ('ready_for_delivery', 'ready_for_dispatch') or s_name == 'ready for delivery' or status == 'Ready for Dispatch':
            msg_template = 'ready_for_delivery'
            passed_qc = order.stages.filter(stage_key='master_quality_check', status='COMPLETED').exists()
            if passed_qc:
                cust_msg = f"Your garment for order {order.reference} has passed quality checks and is Ready for Delivery!"
            else:
                cust_msg = f"Your garment for order {order.reference} is Ready for Delivery! You can collect your outfit or expect delivery shortly."
        elif stage_name and stage_name != status:
            cust_msg = f"Your garment for order {order.reference} is now in the {stage_name} stage ({status})."
            if status == 'Design & Creation':
                cust_msg = f"Your garment for order {order.reference} is now in the {stage_name} stage. Our master tailors are crafting it!"
        else:
            cust_msg = f"Your order {order.reference} status has been updated to: {status}."
            if status == 'Design & Creation':
                cust_msg = f"Your garment for order {order.reference} is now in the Design & Creation phase. Our master tailors are crafting it!"
            elif status == 'Shipped':
                if order.delivery_method == 'Courier':
                    cust_msg = f"Your order {order.reference} has been Shipped via {order.courier_service or 'Courier'}! Tracking Number: {order.tracking_number or 'TBD'}."
                else:
                    cust_msg = f"Your order {order.reference} has been dispatched for direct pickup!"
            elif status == 'Delivered':
                from core.formatting import format_money
                balance = Decimal(str(order.total_amount or 0)) - Decimal(str(order.amount_paid or 0))
                if balance > 0:
                    cust_msg = f"Your order {order.reference} has been successfully Delivered! Please complete your remaining balance of {format_money(balance)}."
                else:
                    cust_msg = f"Your order {order.reference} has been successfully Delivered. We hope you love your bespoke garment!"

        # Fifteen production stages map onto six customer-facing statuses, so
        # most transitions leave the status where it was. Only a change is
        # news -- except the four named steps above, which the customer is
        # told about whether or not the status label moved.
        if not status_changed and msg_template == 'stage_update':
            return

        Notification.objects.create(
            title=f"Order {order.reference} Update: {display_stage}",
            message=f"Order {order.reference} status updated to {display_stage}.",
            recipient_role="Owner"
        )

        Notification.objects.create(
            title=f"Order Update: {display_stage}",
            message=f"Dear {order.customer.first_name}, {cust_msg}",
            recipient_role="Customer",
            recipient_email=client_email
        )
        send_customer_message(
            order,
            msg_template,
            f"Dear {order.customer.first_name}, {cust_msg}\nTrack your order: {tracking_url(order)}",
        )
        send_stage_update_email(
            order,
            stage_name=display_stage,
            custom_message=cust_msg,
        )

        if status == 'Design & Creation' and order.tailor:
            Notification.objects.create(
                title=f"Stitching Ready: {order.reference}",
                message=f"Order {order.reference} is now in Design & Creation phase and ready for stitching.",
                recipient_role=order.tailor.role,
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )

        if status == 'Quality Check':
            Notification.objects.create(
                title=f"Garment Stitching Completed: {order.reference}",
                message=f"Order {order.reference} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is now pending Quality Check.",
                recipient_role="Owner"
            )
            if order.master:
                Notification.objects.create(
                    title=f"Quality Check Required: {order.reference}",
                    message=f"Order {order.reference} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is ready for your Quality Check.",
                    recipient_role=order.master.role,
                    recipient_email=order.master.user.email if order.master.user else None
                )


def notify_next_stage_owners(order):
    from crm_api.models import BoutiqueSettings, Tailor
    from core.permissions import UNSETTLED_STATUSES

    config, _ = BoutiqueSettings.objects.get_or_create(id=1)
    settled = dict(order.stages.values_list('stage_key', 'status'))

    live = next(
        (s for s in (config.workflow_config or [])
         if s.get('key') and settled.get(s['key'], 'NOT_STARTED') in UNSETTLED_STATUSES),
        None)
    if live is None:
        return

    roles = [r for r in (live.get('roles') or []) if r not in ('Owner', 'Master')]
    if not roles:
        return

    for role in roles:
        if not Tailor.objects.filter(role=role).exists():
            continue
        Notification.objects.create(
            title=f"Ready for {live.get('name', live['key'])}: {order.reference}",
            message=(f"Order {order.reference} has reached "
                     f"{live.get('name', live['key'])} and is waiting in your queue."),
            recipient_role=role,
        )


def notify_verification(order, stage, *, submitted):
    """Submitted: tell the owner and Master there is work to verify.
    Sent back: tell the worker who did it, with the supervisor's note."""
    if submitted:
        who = stage.performed_by.name if stage.performed_by else 'A worker'
        for role in ('Owner', 'Master'):
            Notification.objects.create(
                title=f"Verify {stage.stage_name}: {order.reference}",
                message=(f"{who} has submitted {stage.stage_name} on order "
                         f"{order.reference} for verification."),
                recipient_role=role,
            )
        return
    worker = stage.performed_by
    if worker is None:
        return
    Notification.objects.create(
        title=f"Sent back: {stage.stage_name} on {order.reference}",
        message=f"Needs rework: {stage.verification_note}",
        recipient_role=worker.role,
        recipient_email=worker.user.email if worker.user else None,
    )
