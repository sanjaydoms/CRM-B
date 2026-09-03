"""Email to the customer when their order is confirmed.

Separate from notifications.py's Notification rows and from messaging.py's
WhatsApp: those are a dashboard feed and a phone message, and neither reaches
somebody who gave an email address and nothing else. This is the third channel,
and it is composed here -- in the orders domain, where the garment, money and
tracking helpers already live -- rather than inside apps/email_service, which
stays a generic transport and must not learn what an order is.
"""

import logging

from django.conf import settings
from django.db import transaction

from core.formatting import format_money
from domains.orders.garments import garment_label, garment_names
from domains.orders.tracking import tracking_url

logger = logging.getLogger(__name__)


def _boutique_name():
    """The shop's own name, for the subject line and the sign-off."""
    from crm_api.models import BoutiqueSettings
    config, _ = BoutiqueSettings.objects.get_or_create(id=1)
    return (config.name or '').strip() or 'our boutique'


def _content(order):
    customer = order.customer
    boutique = _boutique_name()
    plural = 'Garments' if len(garment_names(order)) > 1 else 'Garment'
    due = (order.estimated_delivery.strftime('%d %b %Y')
           if order.estimated_delivery else 'to be confirmed')
    total = format_money(order.total_amount or 0)
    link = tracking_url(order)

    subject = f"Order Confirmed: {order.order_id} - {boutique}"

    body = (
        f"Dear {customer.first_name},\n\n"
        f"Thank you for your order with {boutique}. We have received it and work is "
        f"about to begin.\n\n"
        f"Order number: {order.order_id}\n"
        f"{plural}: {garment_label(order)}\n"
        f"Expected delivery: {due}\n"
        f"Total: {total}\n\n"
        f"You can follow its progress here:\n{link}\n\n"
        f"We will write again as it moves through our workroom.\n\n"
        f"Warm regards,\n{boutique}"
    )

    # Inline styles and a table-free layout on purpose: every mail client
    # strips <style> blocks, and half of them still disagree about flexbox.
    html = f"""
<div style="font-family:Helvetica,Arial,sans-serif;max-width:520px;margin:0 auto;
            color:#1c1c1c;line-height:1.55">
  <h2 style="font-size:20px;margin:0 0 4px">Your order is confirmed</h2>
  <p style="color:#666;font-size:13px;margin:0 0 20px">{boutique}</p>
  <p style="font-size:14px">Dear {customer.first_name},</p>
  <p style="font-size:14px">
    Thank you for your order. We have received it and work is about to begin.
  </p>
  <div style="border:1px solid #e2e2e2;border-radius:8px;padding:16px;margin:18px 0;
              font-size:14px">
    <div style="margin-bottom:8px"><strong>Order number</strong><br>{order.order_id}</div>
    <div style="margin-bottom:8px"><strong>{plural}</strong><br>{garment_label(order)}</div>
    <div style="margin-bottom:8px"><strong>Expected delivery</strong><br>{due}</div>
    <div><strong>Total</strong><br>{total}</div>
  </div>
  <p style="font-size:14px">
    <a href="{link}" style="background:#0f291e;color:#fff;text-decoration:none;
       padding:10px 18px;border-radius:6px;display:inline-block">Track your order</a>
  </p>
  <p style="font-size:12px;color:#777;margin-top:24px">
    We will write again as your order moves through our workroom.<br>{boutique}
  </p>
</div>
""".strip()

    return subject, body, html


def _deliver(subject, address, body, html):
    """Enqueue, and fall back to sending in-process if the queue is unreachable.

    The job service is the intended path: it writes to Redis and hands the send
    to a background thread, so Confirm does not wait on Gmail. But an order
    confirmation is the one email a customer actually expects, and losing it
    because Redis blipped is worse than the second or two a direct send costs.
    """
    from apps.email_service.services.email_job_service import EmailJobService
    from apps.email_service.services.email_service import EmailService

    try:
        EmailJobService.enqueue_job({
            'subject': subject,
            'recipients': [address],
            'message': body,
            'html_message': html,
            'send_mode': 'to',
        })
        return
    except Exception:
        logger.exception(
            "Could not queue the order confirmation for %s; sending it directly", address)

    EmailService.send_email(
        subject=subject,
        recipient_list=[address],
        body=body,
        html_message=html,
        # The order is already committed. A failed email must not raise into a
        # caller that has nothing left to undo.
        fail_silently=True,
    )


def send_order_confirmation(order):
    """Queue the confirmation email, after the order is safely committed.

    on_commit, not inline: create_order_notifications runs inside the same
    transaction that writes the order, its stages and its garments. Sending
    from in there would email a customer about an order that a later failure
    then rolled back -- and the transaction would be held open across an SMTP
    round trip while it happened.
    """
    address = (getattr(order.customer, 'email_address', '') or '').strip()
    if not address:
        # Plenty of walk-in customers give a phone number and nothing else.
        # They still get the WhatsApp message; there is simply no email to send.
        return

    def _send():
        try:
            subject, body, html = _content(order)
            _deliver(subject, address, body, html)
        except Exception:
            # Never let a mail problem surface as a failed order: by the time
            # this runs the order exists and the customer has been told on
            # screen that it does.
            logger.exception(
                "Order confirmation email failed for order %s", order.order_id)

    transaction.on_commit(_send)
