
from decimal import Decimal

from django.db import connection
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from crm_api.models import BoutiqueSettings, Order
from domains.orders.garments import garment_names
from domains.orders.tracking import read_token


def _payment_status(total, paid):
    if paid >= total:
        return 'Paid'
    if paid > 0:
        return 'Partially Paid'
    return 'Payment Pending'


@require_GET
def order_tracking(request, token):
    schema_name, order_id = read_token(token)
    if not schema_name or schema_name == get_public_schema_name():
        raise Http404

    tenant = get_tenant_model().objects.filter(schema_name=schema_name).first()
    if tenant is None:
        raise Http404

    with schema_context(schema_name):
        order = (
            Order.objects
            .select_related('customer')
            .prefetch_related('stages', 'garment_jobs', 'garment_jobs__template')
            .filter(order_id=order_id)
            .first()
        )
        if order is None:
            raise Http404

        boutique = BoutiqueSettings.objects.filter(id=1).first()

        stages = [s for s in order.stages.all() if s.status != 'SKIPPED']

        trial = (
            order.appointments
            .filter(appointment_type='TRIAL')
            .exclude(status='CANCELLED')
            .order_by('-scheduled_time')
            .first()
        )

        total = order.total_amount or Decimal('0')
        paid = order.amount_paid or Decimal('0')

        garment_images = (
            list(order.garment_images.all()) if order.garment_images_published else []
        )

        garments = garment_names(order)

        context = {
            'boutique': boutique,
            'tenant': tenant,
            'order': order,
            'customer': order.customer,
            'garments': garments,
            'garment_heading': 'Garments' if len(garments) > 1 else 'Garment',
            'stages': stages,
            'garment_images': garment_images,
            'trial': trial,
            'total': total,
            'paid': paid,
            'balance': max(total - paid, Decimal('0')),
            'payment_status': _payment_status(total, paid),
        }
        response = render(request, 'crm_api/tracking.html', context)

    response['Cache-Control'] = 'private, no-store'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response
