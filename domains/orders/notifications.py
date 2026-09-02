"""Notification fan-out for order lifecycle events.

Lives in the orders domain rather than in crm_api.views so that services can
import it without pulling the whole view layer in (which created an import cycle).
"""

from decimal import Decimal

from crm_api.models import Notification
from domains.orders.garments import garment_label, garment_names
from domains.orders.messaging import send_customer_message
from domains.orders.tracking import tracking_url


# Notification.recipient_role must be the person's OWN role, not the job they
# are doing on this order.
#
# NotificationViewSet._audience filters the feed on the signed-in staff member's
# profile.role, and Tailor.ROLE_CHOICES has nine values -- Master, Tailor and
# seven specialists (Measurement, Pattern, Cutting, Maggam, Finishing, Pressing,
# QC). Writing the literal "Tailor" or "Master" here meant that a Cutting Master
# supervising an order, or a Finishing Master given the stitching, was sent a
# notification addressed to a role they do not hold -- so it never appeared in
# their bell and they were never told about work assigned to them. assign_stage
# already gets this right with recipient_role=tailor.role; these four sites did
# not.

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
            order=order,
            title=f"New Order Received: {order.order_id}",
            message=f"A new custom order has been received for client {client_name}.",
            recipient_role="Owner"
        )
        confirmation = (
            f"Dear {order.customer.first_name}, we have received your order {order.order_id}! "
            f"We will update you as it progresses."
        )
        Notification.objects.create(
            order=order,
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
            # Every garment on the order, not the customer's single garment_type
            # field -- which named one dress out of however many she ordered.
            f"{'Garments' if len(garment_names(order)) > 1 else 'Garment'}: "
            f"{garment_label(order)}\n"
            f"Expected delivery: {due}\n"
            f"Track your order: {tracking_url(order)}",
        )
        if order.master:
            Notification.objects.create(
                order=order,
                title=f"New Assignment: {order.order_id}",
                message=f"Order {order.order_id} for client {client_name} has been assigned to you as Supervising Master.",
                recipient_role=order.master.role,
                recipient_email=order.master.user.email if order.master.user else None
            )
        if order.tailor:
            Notification.objects.create(
                order=order,
                title=f"New Stitching Task: {order.order_id}",
                message=f"Order {order.order_id} has been assigned to you for stitching.",
                recipient_role=order.tailor.role,
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )
    else:
        status = order.order_status
        Notification.objects.create(
            order=order,
            title=f"Order {order.order_id} Update: {status}",
            message=f"Order {order.order_id} status updated to {status}.",
            recipient_role="Owner"
        )
        
        cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} status has been updated to: {status}."
        if status == 'Design & Creation':
            cust_msg = f"Dear {order.customer.first_name}, your garment for order {order.order_id} is now in the Design & Creation phase. Our master tailors are crafting it!"
        elif status == 'Ready for Dispatch':
            # Only claim the quality check when it actually ran. This status is
            # reached from ready_for_delivery, trial_scheduled AND
            # trial_completed, none of which require master_quality_check, so
            # the boutique was telling customers their garment had passed an
            # inspection that had never happened.
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
            # Same formatter the tracking page and the invoice use. This said
            # "Rs35675.00" while the invoice for the same order said
            # "Rs35,675" -- one debt, written two ways, in the two places a
            # customer is most likely to compare.
            from core.formatting import format_money
            balance = Decimal(str(order.total_amount or 0)) - Decimal(str(order.amount_paid or 0))
            if balance > 0:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered! Please complete your remaining balance of {format_money(balance)}."
            else:
                cust_msg = f"Dear {order.customer.first_name}, your order {order.order_id} has been successfully Delivered. We hope you love your bespoke garment!"

        Notification.objects.create(
            order=order,
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
                order=order,
                title=f"Stitching Ready: {order.order_id}",
                message=f"Order {order.order_id} is now in Design & Creation phase and ready for stitching.",
                recipient_role=order.tailor.role,
                recipient_email=order.tailor.user.email if order.tailor.user else None
            )

        if status == 'Quality Check':
            # Notify Owner
            Notification.objects.create(
                order=order,
                title=f"Garment Stitching Completed: {order.order_id}",
                message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is now pending Quality Check.",
                recipient_role="Owner"
            )
            # Notify Master
            if order.master:
                Notification.objects.create(
                    order=order,
                    title=f"Quality Check Required: {order.order_id}",
                    message=f"Order {order.order_id} stitching has been completed by {order.tailor.name if order.tailor else 'the tailor'} and is ready for your Quality Check.",
                    recipient_role=order.master.role,
                    recipient_email=order.master.user.email if order.master.user else None
                )


def notify_next_stage_owners(order):
    """Tell whoever performs the stage this order has just arrived at.

    Staff notifications go to the Owner, order.master and order.tailor -- the
    three people an order is personally attached to. A specialist is none of
    them: a QC Master is not the stitcher and not the supervising Master, so
    nothing in the system ever told them a garment was waiting for inspection.
    Combined with a queue they also could not see, quality check was a stage
    that only got done when somebody else noticed it.

    Addressed by ROLE rather than to a named person, deliberately. Picking one
    QC Master means picking wrong in a boutique with two, and re-inventing the
    manual assignment this exists to replace. NotificationViewSet already
    filters by the reader's own role, so every holder of the role sees it and
    whoever gets there first does the work. Nothing is assigned; the stage's
    assigned_to stays free for a Master who does want to name a person.

    Silent for Owner and Master, who are notified through the existing paths and
    would otherwise get a second message for every stage of every order.
    """
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

    # One row per role, not per person: the queue is role-addressed, and a
    # boutique with three finishing staff should not get three copies each.
    for role in roles:
        if not Tailor.objects.filter(role=role).exists():
            # Nobody holds this role here. A notification addressed to a role
            # with no holder is unreadable by anyone -- the Owner already hears
            # about every transition through the path above.
            continue
        Notification.objects.create(
            order=order,
            title=f"Ready for {live.get('name', live['key'])}: {order.order_id}",
            message=(f"Order {order.order_id} has reached "
                     f"{live.get('name', live['key'])} and is waiting in your queue."),
            recipient_role=role,
        )
