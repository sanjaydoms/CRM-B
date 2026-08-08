"""Public demo-request intake for the marketing site.

Deliberately not DRF, for the same reason crm_api/tracking_views.py is not: a
stranger reaches this with no token and no tenant header. Opting out of the
authenticated stack entirely is smaller and safer than carving three exemptions
into it -- DEFAULT_PERMISSION_CLASSES is RolePermission, which denies
AnonymousUser, and DEFAULT_AUTHENTICATION_CLASSES includes SessionAuthentication,
which would enforce CSRF for any staff member who happens to hold a session
cookie in the same browser.

DemoRequest lives in SHARED_APPS, so its table exists only in the public schema
and search_path resolves it there whatever X-Tenant-ID the caller sent. No
schema_context() wrapper is needed, and request.tenant is never touched: on
Render there is no BoutiqueTenant row for the public schema, so the middleware
takes the branch that never sets it.
"""

import ipaddress
import logging
from datetime import timedelta

from django.forms import ModelForm
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import DemoRequest

logger = logging.getLogger(__name__)

# Per IP, per window. Generous for a human filling in a form once, tight enough
# that a bot needs a new address every five submissions.
MAX_PER_IP = 5
RATE_WINDOW = timedelta(hours=1)

# The decoy field on the form. Two constraints on the name, both learned the
# hard way, and both the reason this lives here rather than in a comment on the
# page -- the page is served to whoever asks for it.
#
# It must contain no token a browser autofills on: the first version was
# `company_url`, and Chrome's address-profile autofill matches the COMPANY token
# and ignores autocomplete="off", so a real visitor with a saved profile would
# have had their lead binned as spam. It must also not announce what it is,
# because a name like `honeypot` or `hp_field` is the first thing a bot skips.
HONEYPOT_FIELD = 'note_ref'


class DemoRequestForm(ModelForm):
    """Validation is the model's field definitions -- lengths, email format and
    which fields are required all come from there rather than being restated."""

    class Meta:
        model = DemoRequest
        fields = ['name', 'boutique', 'email', 'phone',
                  'makes', 'orders_per_month', 'people', 'problem']

    def __init__(self, data=None, **kwargs):
        # A textarea counts its length in bare newlines, but form encoding sends
        # each one as CRLF. Someone who types exactly 2000 characters therefore
        # puts 2000 + one-per-line-break on the wire and gets "at most 2000
        # characters (it has 2043)" -- an error about text they cannot see and
        # cannot shorten to fix. Normalising before validation makes the limit
        # mean what the person typing it thinks it means.
        if data is not None:
            data = data.copy()
            for key in data:
                data[key] = data[key].replace('\r\n', '\n')
        super().__init__(data, **kwargs)


def _client_ip(request):
    """The caller's address, as far as it can be trusted.

    X-Forwarded-For is client-supplied and trivially spoofed, so this is a
    speed bump rather than an identity. Render appends the real peer to
    whatever the client sent, which makes the last entry the honest one; the
    leftmost -- the usual choice -- is the one an attacker controls.

    Each candidate is parsed before it is returned. The column is a Postgres
    inet, and Django hands an unparseable value straight to the driver, so a
    header of `X-Forwarded-For: notanip` used to fail the rate-limit query with
    a DataError -- a 500 on a public endpoint, from one header, no auth needed.
    Falling through to REMOTE_ADDR rather than giving up keeps the rate limit
    applied: returning None for a junk header would have made junk the way past
    it.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    candidates = [forwarded.split(',')[-1], request.META.get('REMOTE_ADDR', '')]
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate.strip()))
        except ValueError:
            continue
    return None


@csrf_exempt  # cookie-less cross-origin POST from the Vercel marketing site
@require_POST
def demo_request(request):
    ip = _client_ip(request)

    # Bots fill in every field they can see. A human never sees this one, so
    # anything in it is automated -- answered with the same 201 a real
    # submission gets, because a distinguishable rejection teaches the bot the
    # field name.
    #
    # Logged because the failure mode is silent and expensive: if a browser ever
    # does autofill this field, a real prospect is shown "thank you, that
    # reached us" while their lead is discarded, and without this line there is
    # nothing anywhere to tell that apart from a quiet week.
    if request.POST.get(HONEYPOT_FIELD):
        logger.warning(
            'demo-request discarded by honeypot: email=%r boutique=%r ip=%s',
            request.POST.get('email'), request.POST.get('boutique'), ip,
        )
        return JsonResponse({'ok': True}, status=201)

    if ip:
        recent = DemoRequest.objects.filter(
            ip=ip, created_at__gte=timezone.now() - RATE_WINDOW
        ).count()
        if recent >= MAX_PER_IP:
            return JsonResponse(
                {'ok': False, 'error': 'Too many requests. Please try again later.'},
                status=429,
            )

    form = DemoRequestForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

    lead = form.save(commit=False)
    lead.ip = ip
    lead.save()
    return JsonResponse({'ok': True}, status=201)
