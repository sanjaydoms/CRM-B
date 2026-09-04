
from decimal import Decimal

from crm_api.models import Notification
from domains.orders.garments import garment_label, garment_names
from domains.orders.emails import send_order_confirmation
from domains.orders.messaging import send_customer_message
from domains.orders.tracking import tracking_url



def create_order_notifications(order, created=False, status_changed=True):
    client_name = f"{order.customer.first_name} {order.customer.last_name}"
    client_email = order.customer.email_address
    
    if created:
        Notification.objects.create(
            title=f"New Order Received: {order.order_id}",
            message=f"A new custom order has been received for client {client_name}.",
            recipient_role="Owner"
        )
        confirmation = (
            f"Dear {order.customer.first_name}, we have received your order {order.order_id}! "
            f"We will update you as it progresses."
        )
        Notification.objects.create(
            title=f"Order Confirmed: {order.order_id}",
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
                title=f"New Assignment: {order.order_id}",
                message=f"Order {order.order_id} for client {client_name} has been assigned to you as Supervising Master.",
                recipient_role=order.master.role,
                recipient_email=order.master.user.email if order.master.user else None
            )
        if order.tailor:
            Notification.objects.create(
                title=f"New Stitching Task: {order.order_id}",
                message=f"Order {order.order_id} has been assigned to you for stitching.",
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
        if not status_changed:
            return

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
            passed_qc = order.stages.filter(
                stage_key='master_quality_check', status='COMPLETED').exists()
            if passed_qc:
                cust_msg = f"Dear {order.customer.first_name}, your garment for order {order.order_id} has passed quality checks and is Ready for Dispatch!"
            else:
                cust_msg = f"Dear {order.customer.first_name}, your garment for order {order.order_id} is Ready for Dispatch!"
        elif status == 'Shipped':
            if order.delivery_method == 'Courier':
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been Shipped via {order.courier_service or 'Courier'}! Tracking Number: {order.tracking_number or 'TBD'}."
            else:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been dispatched for direct pickup!"
        elif status == 'Delivered':
            from core.formatting import format_money
            balance = Decimal(str(order.total_amount or 0)) - Decimal(str(order.amount_paid or 0))
            if balance > 0:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered! Please complete your remaining balance of {format_money(balance)}."
            else:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered. We hope you love your bespoke garment!"

        Notification.objects.create(
            title=f"Order Update: {status}",
            message=cust_msg,
            recipient_role="Customer",
            recipient_email=client_email
        )
        send_customer_message(
            order,
            'stage_update',
            f"{cust_msg}\nTrack your order: {tracking_url(order)}",
        )

        if status == 'Design & Creation' and order.tailor:
            Notification.objects.create(
                title=f"Stitching Ready: {order.order_id}",
                message=f"Order {order.order_id} is now in Design & Creation phase and ready for stitching.",
                recipient_role=order.tailor.role,
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )

        if status == 'Quality Check':
            Notification.objects.create(
                title=f"Garment Stitching Completed: {order.order_id}",
                message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is now pending Quality Check.",
                recipient_role="Owner"
            )
            if order.master:
                Notification.objects.create(
                    title=f"Quality Check Required: {order.order_id}",
                    message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is ready for your Quality Check.",
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
            title=f"Ready for {live.get('name', live['key'])}: {order.order_id}",
            message=(f"Order {order.order_id} has reached "
                     f"{live.get('name', live['key'])} and is waiting in your queue."),
            recipient_role=role,
        )
