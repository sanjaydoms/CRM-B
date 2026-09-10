"""Telling people about an alteration, over the channels this product already has.

Three of them, all reused verbatim from the order flow:

  * Notification rows      -- the in-app bell, addressed by role
  * send_customer_message  -- WhatsApp, queued on commit, backend-pluggable
  * send_stage_update_email -- email, queued on commit

No new transport is introduced. `send_customer_message` and the email helper
both take an Order because that is what CustomerMessage is keyed on, so the
alteration's `original_order` is passed through: it attaches the message to the
conversation the customer already has about that order, and writes nothing to
the order itself.

Every send is best-effort. A boutique with messaging switched off, a customer
with no phone number, or a transport that is down must never be able to abort
the transaction that moved the garment along.
"""

import logging

from core.formatting import format_money
from crm_api.models import Notification

logger = logging.getLogger(__name__)


def _customer_name(alteration):
    customer = alteration.customer
    return f"{customer.first_name} {customer.last_name}".strip()


def _garment(alteration):
    template = getattr(alteration.garment_job, 'template', None)
    return getattr(template, 'name', None) or 'your garment'


def _notify_staff(alteration, *, title, message, role, email=None):
    Notification.objects.create(
        title=title, message=message, recipient_role=role, recipient_email=email,
    )


def _notify_customer(alteration, *, title, body, template_key):
    """Bell row for the customer, plus WhatsApp and email where possible."""
    customer = alteration.customer
    Notification.objects.create(
        title=title,
        message=f"Dear {customer.first_name}, {body}",
        recipient_role='Customer',
        recipient_email=customer.email_address,
    )

    order = alteration.original_order
    try:
        from domains.orders.messaging import send_customer_message
        send_customer_message(
            order, template_key,
            f"Dear {customer.first_name}, {body}",
        )
    except Exception:  # noqa: BLE001 - a transport must not fail a transition
        logger.exception('alteration whatsapp notification failed for %s',
                         alteration.alteration_number)

    try:
        from domains.orders.emails import send_stage_update_email
        send_stage_update_email(
            order,
            stage_name=f"Alteration {alteration.alteration_number} - "
                       f"{alteration.get_status_display()}",
            custom_message=body,
        )
    except Exception:  # noqa: BLE001
        logger.exception('alteration email notification failed for %s',
                         alteration.alteration_number)


def alteration_received(alteration):
    _notify_staff(
        alteration,
        title=f"Alteration Received: {alteration.alteration_number}",
        message=(f"{_garment(alteration)} from order "
                 f"{alteration.original_order.order_id} has been taken in for "
                 f"alteration for {_customer_name(alteration)}."),
        role='Owner',
    )
    _notify_customer(
        alteration,
        title=f"Alteration Received: {alteration.alteration_number}",
        body=(f"we have received {_garment(alteration)} from order "
              f"{alteration.original_order.order_id} for alteration "
              f"({alteration.alteration_number}). We will update you shortly."),
        template_key='alteration_received',
    )


def estimate_ready(alteration):
    """The charge has been set and is waiting to be approved."""
    if alteration.charge_amount <= 0:
        return
    _notify_customer(
        alteration,
        title=f"Alteration Estimate: {alteration.alteration_number}",
        body=(f"the estimate for alteration {alteration.alteration_number} is "
              f"{format_money(alteration.charge_amount)}. We will begin once it "
              f"is approved."),
        template_key='alteration_estimate',
    )


def alteration_approved(alteration):
    _notify_customer(
        alteration,
        title=f"Alteration Approved: {alteration.alteration_number}",
        body=(f"alteration {alteration.alteration_number} has been approved and "
              f"is going into our workroom."),
        template_key='alteration_approved',
    )


def alteration_assigned(alteration, tailor):
    if tailor is None:
        return
    _notify_staff(
        alteration,
        title=f"New Alteration Assigned: {alteration.alteration_number}",
        message=(f"Alteration {alteration.alteration_number} for "
                 f"{_customer_name(alteration)} has been assigned to you."),
        role=tailor.role,
        email=tailor.user.email if tailor.user else None,
    )


def work_started(alteration):
    _notify_customer(
        alteration,
        title=f"Alteration Started: {alteration.alteration_number}",
        body=(f"work has started on alteration {alteration.alteration_number}."),
        template_key='alteration_started',
    )


def sent_to_qc(alteration):
    _notify_staff(
        alteration,
        title=f"Alteration Quality Check: {alteration.alteration_number}",
        message=(f"Alteration {alteration.alteration_number} for "
                 f"{_customer_name(alteration)} is waiting for a quality check."),
        role='QC Master',
    )
    _notify_staff(
        alteration,
        title=f"Alteration Quality Check: {alteration.alteration_number}",
        message=(f"Alteration {alteration.alteration_number} is waiting for a "
                 f"quality check."),
        role='Master',
    )


def ready_for_pickup(alteration):
    outstanding = alteration.charge_amount - alteration.amount_paid
    money = ''
    if outstanding > 0:
        money = f" A balance of {format_money(outstanding)} is due on collection."
    _notify_customer(
        alteration,
        title=f"Alteration Ready: {alteration.alteration_number}",
        body=(f"{_garment(alteration)} is ready for collection "
              f"(alteration {alteration.alteration_number}).{money}"),
        template_key='alteration_ready',
    )


def alteration_completed(alteration):
    _notify_staff(
        alteration,
        title=f"Alteration Completed: {alteration.alteration_number}",
        message=(f"Alteration {alteration.alteration_number} for "
                 f"{_customer_name(alteration)} has been completed and handed back."),
        role='Owner',
    )
    _notify_customer(
        alteration,
        title=f"Alteration Completed: {alteration.alteration_number}",
        body=(f"alteration {alteration.alteration_number} is complete and "
              f"{_garment(alteration)} has been handed back. We hope the fit is "
              f"now exactly right."),
        template_key='alteration_completed',
    )


def alteration_cancelled(alteration, reason):
    _notify_staff(
        alteration,
        title=f"Alteration Cancelled: {alteration.alteration_number}",
        message=(f"Alteration {alteration.alteration_number} for "
                 f"{_customer_name(alteration)} was cancelled: {reason}"),
        role='Owner',
    )
