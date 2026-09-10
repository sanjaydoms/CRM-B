
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

MAX_PER_IP = 5
RATE_WINDOW = timedelta(hours=1)

HONEYPOT_FIELD = 'note_ref'


class DemoRequestForm(ModelForm):

    class Meta:
        model = DemoRequest
        fields = ['name', 'boutique', 'email', 'phone',
                  'makes', 'orders_per_month', 'people', 'problem']

    def __init__(self, data=None, **kwargs):
        if data is not None:
            data = data.copy()
            for key in data:
                data[key] = data[key].replace('\r\n', '\n')
        super().__init__(data, **kwargs)


def _client_ip(request):
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
