
from decimal import Decimal

from django.db import connection
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from core.modules import is_enabled
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

    # The two gates TenantHeaderMiddleware applies to every other request.
    #
    # This view resolves its own tenant from the signed token and enters the
    # schema itself, so the middleware's control check never ran for it: a
    # boutique suspended by the platform console, or one whose order_tracking
    # module had been switched off, went on serving customer-facing order pages
    # -- name, garments, stage history and payment status -- to anyone holding
    # a previously issued link. Opting out of the authenticated stack was
    # deliberate; opting out of the boutique's own on/off switches was not.
    #
    # Read from the registry row fetched above rather than re-implemented:
    # is_enabled is the same helper the middleware calls, so the two cannot
    # drift about what "absent means enabled" means.
    if not tenant.is_active:
        raise Http404
    if not is_enabled(getattr(tenant, 'enabled_modules', None), 'order_tracking'):
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
