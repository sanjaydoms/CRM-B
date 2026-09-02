"""The public order tracking page.

Deliberately not DRF. This is the one view in the project a stranger reaches
with no token and no tenant header, so it opts out of the whole authenticated
stack rather than trying to carve an exemption in it: a plain Django view
rendering a server-side template needs no CORS entry, no permission class
exception, and no route added to a frontend that has no router.
"""

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

    # The schema in the payload is signed, so it cannot have been edited -- but
    # it can be stale, if the boutique was deleted since the link was sent.
    # Checking it against the tenant table keeps a dead schema out of
    # search_path instead of surfacing as a 500.
    # Fetched, not merely existence-checked: this page renders times for the
    # customer, and the boutique's timezone lives on this row. schema_context
    # binds a FakeTenant carrying only a schema name, so nothing inside the
    # block below can recover the real one -- the timezone has to be carried in
    # from here or every boutique silently renders in the platform default,
    # which is the India-shaped assumption this design exists to avoid.
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

        # Read-only, not get_or_create: this is an unauthenticated GET, and the
        # row it would create carries the shipped placeholder name, address and
        # phone -- which the page would then show the customer as if they were
        # the boutique's. A boutique with no settings row renders blanks, which
        # is at least honest.
        boutique = BoutiqueSettings.objects.filter(id=1).first()

        # Skipped stages are internal bookkeeping (a garment with no maggam
        # work); showing the customer a stage that will never happen only
        # invites the question of why it is stuck.
        #
        # OrderStage.comments is deliberately not passed through to the
        # template. The CRM labels that field "Enter notes, alterations details,
        # or comments" and staff use it for internal notes about mistakes and
        # rework; republishing it to whoever holds the link is not what anyone
        # typed it into. The spec's "status notes (if shared by the boutique)"
        # needs a per-note share flag, which does not exist yet.
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

        # Only once the boutique has said so. Photographs go up one angle at a
        # time, and an unpublished gallery is a half-finished one.
        garment_images = (
            list(order.garment_images.all()) if order.garment_images_published else []
        )

        # Every garment on the order. The page used to print
        # customer.garment_type, so a customer who ordered a blouse and a
        # lehenga was shown one of them and left to wonder about the other.
        garments = garment_names(order)

        context = {
            'boutique': boutique,
            # Read by the boutique_format filters, which cannot find it on the
            # connection here for the reason given above.
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
        # Rendered inside the tenant context: the template touches the logo and
        # the customer, and both are tenant-scoped lazy loads.
        response = render(request, 'crm_api/tracking.html', context)

    # A tracking link is a personal document. Keep it out of shared caches and
    # out of search results even if a customer forwards it somewhere public.
    response['Cache-Control'] = 'private, no-store'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response
