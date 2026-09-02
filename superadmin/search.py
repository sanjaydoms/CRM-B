
from django.contrib.auth.models import User
from django.db.models import Q
from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context

from .schemas import MissingSchema, tenant_scope
from .users import clamped_int

import logging

logger = logging.getLogger(__name__)

from crm_api.models import Customer, Order
from tenants.models import BoutiqueTenant

from .models import AuditLog, ErrorEvent

MIN_TERM = 2
DEFAULT_PER_TYPE = 10
MAX_PER_TYPE = 25
MAX_RESULTS = 100

TYPES = ('boutique', 'user', 'customer', 'order', 'error', 'audit')

TENANT_TYPES = ('user', 'customer', 'order')


def _hit(kind, ident, label, sublabel, schema='', boutique_name=''):
    return {
        'type': kind,
        'id': str(ident),
        'label': label,
        'sublabel': sublabel,
        'boutique': schema,
        'boutique_name': boutique_name,
        'key': f'{kind}:{schema}:{ident}',
    }


def _boutique_hits(term, limit):
    public = get_public_schema_name()
    return [
        _hit('boutique', t.schema_name, t.name or t.schema_name,
             f'{t.owner_email} - {"active" if t.is_active else "suspended"}',
             t.schema_name, t.name)
        for t in BoutiqueTenant.objects.exclude(schema_name=public).filter(
            Q(name__icontains=term) | Q(schema_name__icontains=term)
            | Q(owner_email__icontains=term)).order_by('name')[:limit]
    ]


def _error_hits(term, limit, names):
    return [
        _hit('error', e.id, e.exception_type,
             f'{e.path} - seen {e.count}x - {e.get_status_display()}',
             e.boutique, names.get(e.boutique, ''))
        for e in ErrorEvent.objects.filter(
            Q(exception_type__icontains=term) | Q(message__icontains=term)
            | Q(path__icontains=term) | Q(username__icontains=term))[:limit]
    ]


def _audit_hits(term, limit, names):
    return [
        _hit('audit', a.id, f'{a.actor} - {a.get_action_display()}',
             f'{a.target or "-"} - {a.created_at:%Y-%m-%d %H:%M}',
             a.boutique, names.get(a.boutique, ''))
        for a in AuditLog.objects.filter(
            Q(actor__icontains=term) | Q(target__icontains=term)
            | Q(action__icontains=term) | Q(reason__icontains=term))[:limit]
    ]


def _user_hits(tenant, term, limit):
    return [
        _hit('user', u.username, u.get_full_name() or u.username,
             f'{u.email or "no email"} - '
             f'{"active" if u.is_active else "deactivated"}',
             tenant.schema_name, tenant.name)
        for u in User.objects.filter(
            Q(username__icontains=term) | Q(email__icontains=term)
            | Q(first_name__icontains=term) | Q(last_name__icontains=term)
        ).order_by('username')[:limit]
    ]


def _customer_hits(tenant, term, limit):
    return [
        _hit('customer', c.id, f'{c.first_name} {c.last_name}'.strip(),
             c.mobile_number or c.email_address or '',
             tenant.schema_name, tenant.name)
        for c in Customer.objects.filter(
            Q(first_name__icontains=term) | Q(last_name__icontains=term)
            | Q(mobile_number__icontains=term)
            | Q(email_address__icontains=term)
        ).order_by('first_name', 'id')[:limit]
    ]


def _order_hits(tenant, term, limit):
    return [
        _hit('order', o.order_id, o.order_id,
             f'{o.customer.first_name} {o.customer.last_name} - '
             f'{o.order_status}',
             tenant.schema_name, tenant.name)
        for o in Order.objects.select_related('customer').filter(
            Q(order_id__icontains=term) | Q(tracking_number__icontains=term)
            | Q(customer__first_name__icontains=term)
            | Q(customer__last_name__icontains=term)
            | Q(customer__mobile_number__icontains=term)
        ).order_by('-order_date', 'order_id')[:limit]
    ]


def search(term, tenants, limit_per_type=DEFAULT_PER_TYPE):
    term = (term or '').strip()
    if len(term) < MIN_TERM:
        return []
    cap = clamped_int(limit_per_type, DEFAULT_PER_TYPE, 1, MAX_PER_TYPE)

    public = get_public_schema_name()
    boutiques = [t for t in tenants if t.schema_name != public]
    names = {t.schema_name: t.name for t in boutiques}

    found = {name: [] for name in TYPES}

    with schema_context(public):
        found['boutique'] = _boutique_hits(term, cap)
        found['error'] = _error_hits(term, cap, names)
        found['audit'] = _audit_hits(term, cap, names)

    finders = {'user': _user_hits, 'customer': _customer_hits,
               'order': _order_hits}
    for tenant in boutiques:
        if all(len(found[name]) >= cap for name in TENANT_TYPES):
            break
        try:
            with transaction.atomic():
                with tenant_scope(tenant):
                    gathered = {
                        name: finders[name](tenant, term, cap - len(found[name]))
                        for name in TENANT_TYPES if cap > len(found[name])
                    }
        except MissingSchema as exc:
            logger.warning('%s', exc)
            continue
        except Exception as exc:
            logger.warning('Search skipped boutique %s: %s', tenant.schema_name, exc)
            continue
        for name, hits in gathered.items():
            found[name].extend(hits)

    results = []
    for name in TYPES:
        results.extend(found[name])
    return results[:MAX_RESULTS]
