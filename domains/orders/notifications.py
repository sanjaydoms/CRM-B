"""Notification fan-out for order lifecycle events.

Lives in the orders domain rather than in crm_api.views so that services can
import it without pulling the whole view layer in (which created an import cycle).
"""

from crm_api.models import Notification
from domains.orders.messaging import send_customer_message
from domains.orders.tracking import tracking_url


def create_order_notifications(order, created=False, status_changed=True):
    """Fan out notifications for an order event.

    ``status_changed`` gates only what goes *out* to the customer. Several
    workflow stages map to a single customer-facing order_status (five of them
    mean "Design & Creation"), so advancing production normally would otherwise
    send the customer the same sentence five times. Staff notifications still
    fire on every stage, because to staff each stage is a distinct event.
    OrderViewSet.perform_update already gates its own call the same way.
    """
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
            f"Garment: {order.customer.garment_type}\n"
            f"Expected delivery: {due}\n"
            f"Track your order: {tracking_url(order)}",
        )
        if order.master:
            Notification.objects.create(
                title=f"New Assignment: {order.order_id}",
                message=f"Order {order.order_id} for client {client_name} has been assigned to you as Supervising Master.",
                recipient_role="Master",
                recipient_email=order.master.user.email if order.master.user else None
            )
        if order.tailor:
            Notification.objects.create(
                title=f"New Stitching Task: {order.order_id}",
                message=f"Order {order.order_id} has been assigned to you for stitching.",
                recipient_role="Tailor",
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )
    else:
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
            cust_msg = f"Dear {order.customer.first_name}, your garment for order {order.order_id} has passed quality checks and is Ready for Dispatch!"
        elif status == 'Shipped':
            if order.delivery_method == 'Courier':
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been Shipped via {order.courier_service or 'Courier'}! Tracking Number: {order.tracking_number or 'TBD'}."
            else:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been dispatched for direct pickup!"
        elif status == 'Delivered':
            balance = float(order.total_amount) - float(order.amount_paid or 0)
            if balance > 0:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered! Please complete your remaining balance of ₹{balance:.2f}."
            else:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered. We hope you love your bespoke garment!"

        Notification.objects.create(
            title=f"Order Update: {status}",
            message=cust_msg,
            recipient_role="Customer",
            recipient_email=client_email
        )
        if status_changed:
            send_customer_message(
                order,
                'stage_update',
                f"{cust_msg}\nTrack your order: {tracking_url(order)}",
            )

        if status == 'Design & Creation' and order.tailor:
            Notification.objects.create(
                title=f"Stitching Ready: {order.order_id}",
                message=f"Order {order.order_id} is now in Design & Creation phase and ready for stitching.",
                recipient_role="Tailor",
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )

        if status == 'Quality Check':
            # Notify Owner
            Notification.objects.create(
                title=f"Garment Stitching Completed: {order.order_id}",
                message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is now pending Quality Check.",
                recipient_role="Owner"
            )
            # Notify Master
            if order.master:
                Notification.objects.create(
                    title=f"Quality Check Required: {order.order_id}",
                    message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is ready for your Quality Check.",
                    recipient_role="Master",
                    recipient_email=order.master.user.email if order.master.user else None
                )
