"""The console endpoints added for the Super Admin Control Center.

Split from views.py rather than appended to it because that file is the original
console -- sign-in, overview, boutiques, leads, the data browser -- and this is
everything built on top: users, onboarding, modules, flags, configuration,
health, errors, the audit trail, the orders monitor and search. Two files of
three hundred lines each beat one of six hundred, and the split follows the
seam that already exists.

Three rules hold across every view here, and each has a failure behind it:

**Every class names permission_classes = [IsPlatformAdmin].**
settings.DEFAULT_PERMISSION_CLASSES is core.permissions.RolePermission, which
resolves a *boutique* role -- and resolve_user_role answers OWNER for any
superuser. A console endpoint that forgets the class does not fail closed; it
opens to anything holding a superuser token in any schema.

**Every mutation writes an audit row.**
The console's whole purpose is doing things no boutique can undo. Before this,
`BoutiqueTenant.objects.filter(pk=...).update(is_active=False)` fired no signal
and wrote no record, so "who suspended this boutique" had no answer anywhere.

**Query parameters are parsed, never trusted.**
They arrive as strings from a URL anyone can edit. `int(request.query_params
['page'])` on `?page=abc` is a 500 and -- now that errors are captured -- an
ErrorEvent row, for a malformed URL.
"""

from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core import modules as module_registry
from tenants.middleware import clear_platform_cache, clear_tenant_cache
from tenants.models import BoutiqueTenant

from . import audit, health, onboarding, search as search_module, users as users_module
from .metrics import operational_metrics, tenant_metrics
from .models import AuditLog, ErrorEvent, FeatureFlag, PlatformSetting
from .permissions import IsPlatformAdmin
from .schemas import public_scope
from .views import _boutiques


def _int(value, default, low=1, high=None):
    """A query parameter as a bounded integer, never an exception.

    Anything unparseable becomes the default rather than a 500: these come from
    a URL bar, and a typo in one is not a server fault.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    parsed = max(low, parsed)
    return min(parsed, high) if high is not None else parsed


def _tenant_or_404(schema_name):
    return _boutiques().filter(schema_name=schema_name).first()


class ConsoleView(APIView):
    """Base class, so a new endpoint cannot be written without the permission.

    Subclassing rather than remembering: the one rule that must hold on every
    view in this file is the one most easily left off a new one.
    """

    permission_classes = [IsPlatformAdmin]


# --------------------------------------------------------------- users

class UsersView(ConsoleView):
    """Every account on the platform, merged across boutiques."""

    def get(self, request):
        params = request.query_params
        return Response(users_module.list_users(
            list(_boutiques()),
            search=params.get('q', ''),
            boutique=params.get('boutique') or None,
            role=params.get('role') or None,
            status=params.get('status') or None,
            page=_int(params.get('page'), 1),
            page_size=_int(params.get('page_size'), users_module.DEFAULT_PAGE_SIZE,
                           high=users_module.MAX_PAGE_SIZE),
        ))


class UserActionView(ConsoleView):
    """Deactivate, reactivate, revoke sessions, or trigger a password reset.

    One endpoint with an `action` in the URL rather than four, because all four
    share the same shape: resolve the boutique, act, audit, report. The set is
    closed -- an unknown action is a 400, not a 404, because the boutique and
    user in the path may both be perfectly real.

    Every one of these is audited *with the reason the administrator typed*.
    Resetting someone's password is not a neutral act and the trail should say
    why it happened.
    """

    ACTIONS = {
        'deactivate': ('user.deactivate', lambda s, u: users_module.set_user_active(s, u, False)),
        'activate': ('user.activate', lambda s, u: users_module.set_user_active(s, u, True)),
        'revoke': ('user.revoke_token', users_module.revoke_sessions),
        'reset-password': ('user.password_reset', users_module.trigger_password_reset),
    }

    def post(self, request, schema_name=None, username=None, action=None):
        entry = self.ACTIONS.get(action)
        if entry is None:
            return Response(
                {'error': f"Unknown action '{action}'.",
                 'allowed': sorted(self.ACTIONS)},
                status=status.HTTP_400_BAD_REQUEST)

        if _tenant_or_404(schema_name) is None:
            return Response({'error': 'No such boutique.'}, status=status.HTTP_404_NOT_FOUND)

        audit_action, run = entry
        ok, message = run(schema_name, username)

        # Recorded whether it succeeded or not. A refused deactivation of a
        # boutique owner is exactly the kind of attempt worth having a record of.
        audit.record(request, audit_action, target=username, boutique=schema_name,
                     after={'ok': ok, 'result': message},
                     reason=(request.data.get('reason') or '').strip())

        return Response({'ok': ok, 'message': message},
                        status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------- onboarding

class OnboardingView(ConsoleView):
    """Onboarding progress for every boutique, or the full checklist for one.

    The list form deliberately returns the summary rather than every step: it is
    a table of fifty boutiques, and the checklist is what the detail view is for.
    """

    def get(self, request, schema_name=None):
        if schema_name:
            tenant = _tenant_or_404(schema_name)
            if tenant is None:
                return Response({'error': 'No such boutique.'}, status=status.HTTP_404_NOT_FOUND)
            return Response(dict(onboarding.progress(tenant),
                                 schema_name=tenant.schema_name, name=tenant.name))

        rows = []
        for tenant in _boutiques():
            summary = onboarding.progress(tenant)
            rows.append({
                'schema_name': tenant.schema_name,
                'name': tenant.name,
                'owner_email': tenant.owner_email,
                'is_active': tenant.is_active,
                'created_on': tenant.created_on,
                'readable': summary.get('readable', False),
                'percent': summary.get('percent', 0),
                'status': summary.get('status'),
                'blocked_on': summary.get('blocked_on'),
                'detail': summary.get('detail', ''),
            })
        return Response({'boutiques': rows})


# ------------------------------------------------------------- modules

class ModulesView(ConsoleView):
    """The feature surface, and which boutiques have had it changed.

    GET returns the registry itself -- including the structural and client-only
    entries, so the console can explain why Orders and Invoices have no switch
    rather than leaving a hole where someone expected one.
    """

    def get(self, request):
        return Response({
            **module_registry.catalogue(),
            'boutiques': [
                {'schema_name': t.schema_name, 'name': t.name, 'is_active': t.is_active,
                 'enabled_modules': t.enabled_modules or {}}
                for t in _boutiques()
            ],
        })


class BoutiqueModulesView(ConsoleView):
    """Switch one boutique's modules on or off.

    PATCH with {"modules": {"inventory": false}, "reason": "..."} -- a partial
    map, merged over what is stored, so the caller sends only what changed and
    two administrators editing different modules cannot clobber each other.

    Only keys the registry knows are accepted. An unknown key would be stored
    forever, matched by nothing, and would show up in the audit trail as a
    change that did something.
    """

    def patch(self, request, schema_name=None):
        tenant = _tenant_or_404(schema_name)
        if tenant is None:
            return Response({'error': 'No such boutique.'}, status=status.HTTP_404_NOT_FOUND)

        requested = request.data.get('modules')
        if not isinstance(requested, dict) or not requested:
            return Response(
                {'error': 'Send {"modules": {"<key>": true|false, ...}}.'},
                status=status.HTTP_400_BAD_REQUEST)

        unknown = sorted(set(requested) - set(module_registry.MODULES))
        if unknown:
            return Response(
                {'error': f"Not switchable modules: {', '.join(unknown)}.",
                 'switchable': sorted(module_registry.MODULES)},
                status=status.HTTP_400_BAD_REQUEST)

        before = dict(tenant.enabled_modules or {})
        after = dict(before)
        for key, value in requested.items():
            after[key] = bool(value)

        with transaction.atomic():
            # .update() rather than .save(): BoutiqueTenant is a TenantMixin and
            # its save() is what creates and migrates Postgres schemas. Toggling
            # a switch must not be able to trigger any of that.
            BoutiqueTenant.objects.filter(pk=tenant.pk).update(enabled_modules=after)

        # The middleware caches tenants for 300s, and it is the middleware that
        # enforces these switches -- so without this the change lands in the
        # database and does nothing for five minutes in this worker.
        clear_tenant_cache()

        audit.record(request, 'boutique.modules', target=schema_name,
                     boutique=schema_name, before=before, after=after,
                     reason=(request.data.get('reason') or '').strip())

        return Response({
            'schema_name': schema_name,
            'enabled_modules': after,
            # Said out loud because it is the difference between "it worked" and
            # "it worked here". gunicorn runs more than one worker and each
            # holds its own tenant cache.
            'note': 'Other server workers apply this within 5 minutes.',
        })


# --------------------------------------------------------- feature flags

class FlagsView(ConsoleView):
    def get(self, request):
        with public_scope():
            return Response({'flags': [
                {'key': f.key, 'description': f.description, 'enabled': f.enabled,
                 'enabled_for': f.enabled_for or [], 'rollout_percent': f.rollout_percent,
                 'created_by': f.created_by, 'modified_by': f.modified_by,
                 'created_at': f.created_at, 'updated_at': f.updated_at}
                for f in FeatureFlag.objects.all()
            ]})

    def post(self, request):
        key = (request.data.get('key') or '').strip()
        if not key:
            return Response({'error': 'A flag needs a key.'},
                            status=status.HTTP_400_BAD_REQUEST)
        with public_scope():
            if FeatureFlag.objects.filter(key=key).exists():
                return Response({'error': f"A flag called '{key}' already exists."},
                                status=status.HTTP_400_BAD_REQUEST)
            flag = FeatureFlag.objects.create(
                key=key,
                description=(request.data.get('description') or '').strip(),
                enabled=bool(request.data.get('enabled')),
                created_by=request.user.username,
                modified_by=request.user.username,
            )
        audit.record(request, 'flag.change', target=key,
                     after={'created': True, 'enabled': flag.enabled})
        return Response({'key': flag.key, 'enabled': flag.enabled},
                        status=status.HTTP_201_CREATED)


class FlagDetailView(ConsoleView):
    """Change or remove one flag.

    `rollout_percent` is clamped rather than validated into an error: a console
    slider cannot send 150, and a hand-written 150 clearly means "everyone".
    """

    def patch(self, request, key=None):
        with public_scope():
            flag = FeatureFlag.objects.filter(key=key).first()
            if flag is None:
                return Response({'error': 'No such flag.'}, status=status.HTTP_404_NOT_FOUND)

            before = {'enabled': flag.enabled, 'enabled_for': list(flag.enabled_for or []),
                      'rollout_percent': flag.rollout_percent}

            if 'enabled' in request.data:
                flag.enabled = bool(request.data['enabled'])
            if 'description' in request.data:
                flag.description = (request.data['description'] or '').strip()
            if 'rollout_percent' in request.data:
                flag.rollout_percent = _int(request.data['rollout_percent'], 0, low=0, high=100)
            if 'enabled_for' in request.data:
                wanted = request.data['enabled_for']
                if not isinstance(wanted, list):
                    return Response({'error': 'enabled_for must be a list of schema names.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                known = set(_boutiques().values_list('schema_name', flat=True))
                # Silently keeping an unknown schema here would make a flag look
                # targeted at a boutique that does not exist.
                unknown = sorted(set(wanted) - known)
                if unknown:
                    return Response({'error': f"Unknown boutiques: {', '.join(unknown)}."},
                                    status=status.HTTP_400_BAD_REQUEST)
                flag.enabled_for = wanted

            flag.modified_by = request.user.username
            flag.save()
            after = {'enabled': flag.enabled, 'enabled_for': list(flag.enabled_for or []),
                     'rollout_percent': flag.rollout_percent}

        audit.record(request, 'flag.change', target=key, before=before, after=after,
                     reason=(request.data.get('reason') or '').strip())
        return Response(after)

    def delete(self, request, key=None):
        with public_scope():
            flag = FeatureFlag.objects.filter(key=key).first()
            if flag is None:
                return Response({'error': 'No such flag.'}, status=status.HTTP_404_NOT_FOUND)
            before = {'enabled': flag.enabled, 'description': flag.description}
            flag.delete()
        audit.record(request, 'flag.change', target=key, before=before,
                     after={'deleted': True},
                     reason=(request.data.get('reason') or '').strip())
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------- configuration

class ConfigView(ConsoleView):
    """Platform settings, as rows.

    Reads back the settings.py values that matter operationally alongside the
    editable rows -- but only whether a credential is *present*, never its
    value. An operations console that prints an API key is a credential store
    with a login page in front of it.
    """

    def get(self, request):
        from django.conf import settings as django_settings

        with public_scope():
            rows = [{'key': s.key, 'value': s.value, 'description': s.description,
                     'updated_by': s.updated_by, 'updated_at': s.updated_at}
                    for s in PlatformSetting.objects.all()]

        return Response({
            'settings': rows,
            'environment': {
                'debug': django_settings.DEBUG,
                'allowed_hosts': django_settings.ALLOWED_HOSTS,
                'time_zone': django_settings.TIME_ZONE,
                'tracking_base_url': django_settings.TRACKING_BASE_URL,
                'whatsapp_country_code': django_settings.WHATSAPP_COUNTRY_CODE,
            },
            # Presence, never values.
            'credentials': {
                'email_host': bool(getattr(django_settings, 'EMAIL_HOST', '')),
                'supabase': bool(django_settings.SUPABASE_URL and django_settings.SUPABASE_KEY),
                'customer_message_backend': bool(django_settings.CUSTOMER_MESSAGE_BACKEND),
                'design_studio_pinterest': bool(django_settings.DESIGN_STUDIO_PINTEREST_TOKEN),
                'design_studio_google': bool(django_settings.DESIGN_STUDIO_GOOGLE_API_KEY),
            },
        })

    def put(self, request):
        key = (request.data.get('key') or '').strip()
        if not key:
            return Response({'error': 'A setting needs a key.'},
                            status=status.HTTP_400_BAD_REQUEST)

        with public_scope():
            setting, _created = PlatformSetting.objects.get_or_create(key=key)
            before = setting.value
            setting.value = request.data.get('value')
            if 'description' in request.data:
                setting.description = (request.data['description'] or '').strip()
            setting.updated_by = request.user.username
            setting.save()
            after = setting.value

        # maintenance_mode is read by the middleware from a per-worker cache, so
        # a write that does not clear it takes effect at the TTL rather than at
        # the click. Cleared for every key rather than only that one: the next
        # cached setting will be added by someone who does not read this.
        clear_platform_cache()

        audit.record(request, 'setting.change', target=key, before=before, after=after,
                     reason=(request.data.get('reason') or '').strip())
        return Response({'key': key, 'value': after,
                         'note': 'Other server workers apply this within 5 minutes.'})


# -------------------------------------------------------------- health

class HealthView(ConsoleView):
    def get(self, request):
        results = health.checks()
        # The worst individual status becomes the headline, so a green banner
        # can never sit above a red row.
        rank = ['critical', 'offline', 'degraded', 'warning', 'not_configured', 'healthy']
        worst = next((s for s in rank if any(r['status'] == s for r in results)), 'healthy')
        return Response({'overall': worst, 'checks': results})


# -------------------------------------------------------------- errors

class ErrorsView(ConsoleView):
    """The error feed, grouped by fingerprint.

    Ordered by last seen rather than by count: an error that stopped happening a
    week ago is less urgent than one happening now, whatever its total.
    """

    def get(self, request):
        params = request.query_params
        page = _int(params.get('page'), 1)
        page_size = _int(params.get('page_size'), 50, high=200)

        with public_scope():
            queryset = ErrorEvent.objects.all()
            if params.get('status'):
                queryset = queryset.filter(status=params['status'])
            if params.get('severity'):
                queryset = queryset.filter(severity=params['severity'])
            if params.get('boutique'):
                queryset = queryset.filter(boutique=params['boutique'])
            if params.get('q'):
                term = params['q']
                queryset = queryset.filter(
                    Q(exception_type__icontains=term) | Q(message__icontains=term)
                    | Q(path__icontains=term))

            total = queryset.count()
            start = (page - 1) * page_size
            rows = [{
                'id': e.id, 'fingerprint': e.fingerprint,
                'exception_type': e.exception_type, 'message': e.message,
                'traceback': e.traceback, 'path': e.path, 'method': e.method,
                'status_code': e.status_code, 'boutique': e.boutique,
                # `boutique` is the most recent occurrence only. Without this
                # the console can name the fortieth boutique a bug hit and none
                # of the other thirty-nine -- the column ErrorEvent.boutiques
                # exists to answer, serialised nowhere until now.
                'boutiques': e.boutiques,
                'username': e.username, 'severity': e.severity, 'status': e.status,
                'count': e.count, 'first_seen': e.first_seen, 'last_seen': e.last_seen,
                'notes': e.notes, 'resolved_by': e.resolved_by, 'resolved_at': e.resolved_at,
            } for e in queryset[start:start + page_size]]

            summary = {
                'unresolved': ErrorEvent.objects.exclude(
                    status__in=('resolved', 'ignored')).count(),
                'critical': ErrorEvent.objects.filter(
                    severity='critical').exclude(status__in=('resolved', 'ignored')).count(),
            }

        return Response({'errors': rows, 'count': total, 'page': page,
                         'page_size': page_size,
                         'pages': max(1, -(-total // page_size)), 'summary': summary})


class ErrorSummaryView(ConsoleView):
    """Just the counts, for the navigation badge. Two aggregates, no rows."""

    def get(self, request):
        with public_scope():
            open_errors = ErrorEvent.objects.exclude(status__in=('resolved', 'ignored'))
            return Response({
                'unresolved': open_errors.count(),
                'critical': open_errors.filter(severity='critical').count(),
            })


class ErrorDetailView(ConsoleView):
    """Acknowledge, resolve, ignore or annotate one error group."""

    ALLOWED = {'new', 'acknowledged', 'resolved', 'ignored'}

    def patch(self, request, pk=None):
        from django.utils import timezone

        with public_scope():
            event = ErrorEvent.objects.filter(pk=pk).first()
            if event is None:
                return Response({'error': 'No such error.'}, status=status.HTTP_404_NOT_FOUND)

            before = {'status': event.status, 'notes': event.notes}
            new_status = request.data.get('status')
            if new_status is not None:
                if new_status not in self.ALLOWED:
                    return Response({'error': f"Status must be one of {sorted(self.ALLOWED)}."},
                                    status=status.HTTP_400_BAD_REQUEST)
                event.status = new_status
                if new_status == 'resolved':
                    event.resolved_by = request.user.username
                    event.resolved_at = timezone.now()
                else:
                    # Reopening clears the resolution, or the next person reads a
                    # name and a date against an error that is live again.
                    event.resolved_by = ''
                    event.resolved_at = None
            if 'notes' in request.data:
                event.notes = (request.data['notes'] or '').strip()
            event.save()
            after = {'status': event.status, 'notes': event.notes}

        audit.record(
            request,
            'error.resolve' if after['status'] == 'resolved' else 'error.acknowledge',
            target=f'error:{pk}', boutique=event.boutique, before=before, after=after,
            reason=(request.data.get('reason') or '').strip())
        return Response(after)


# --------------------------------------------------------------- audit

class AuditView(ConsoleView):
    """The trail. Read-only over HTTP -- there is no write route by design.

    AuditLog is append-only: it is written by superadmin.audit.record and by
    nothing else. Exposing an edit or delete route here would make the record of
    an action editable by the same credential that took the action, which is the
    one property an audit trail cannot give up.
    """

    def get(self, request):
        params = request.query_params
        page = _int(params.get('page'), 1)
        page_size = _int(params.get('page_size'), 50, high=200)

        with public_scope():
            queryset = AuditLog.objects.all()
            for field in ('actor', 'action', 'boutique', 'target'):
                if params.get(field):
                    queryset = queryset.filter(**{field: params[field]})
            if params.get('q'):
                term = params['q']
                queryset = queryset.filter(
                    Q(actor__icontains=term) | Q(target__icontains=term)
                    | Q(reason__icontains=term) | Q(action__icontains=term))

            total = queryset.count()
            start = (page - 1) * page_size
            rows = [{
                'id': a.id, 'actor': a.actor, 'action': a.action,
                'action_label': a.get_action_display(), 'target': a.target,
                'boutique': a.boutique, 'before': a.before, 'after': a.after,
                'reason': a.reason, 'ip': a.ip, 'created_at': a.created_at,
            } for a in queryset[start:start + page_size]]

        return Response({'entries': rows, 'count': total, 'page': page,
                         'page_size': page_size, 'pages': max(1, -(-total // page_size)),
                         'actions': [{'value': v, 'label': l} for v, l in AuditLog.ACTIONS]})


# ------------------------------------------------------ orders monitor

class OrdersMonitorView(ConsoleView):
    """Order operations across every boutique, or inside one.

    Aggregates only. The console must be able to spot a systemic problem --
    every boutique's messages queueing, orders piling up at one stage -- without
    reading anybody's order book.
    """

    def get(self, request, schema_name=None):
        if schema_name:
            tenant = _tenant_or_404(schema_name)
            if tenant is None:
                return Response({'error': 'No such boutique.'}, status=status.HTTP_404_NOT_FOUND)
            return Response({'boutique': {'schema_name': tenant.schema_name, 'name': tenant.name},
                             **operational_metrics(tenant)})

        rows, totals = [], {}
        for tenant in _boutiques():
            figures = operational_metrics(tenant)
            rows.append({'schema_name': tenant.schema_name, 'name': tenant.name,
                         'is_active': tenant.is_active, **figures})
            if not figures.get('healthy', True):
                continue
            for bucket in ('by_order_status', 'by_payment_status',
                           'by_production_status', 'by_stage'):
                target = totals.setdefault(bucket, {})
                for label, number in (figures.get(bucket) or {}).items():
                    target[label] = target.get(label, 0) + number
            for scalar in ('orders', 'queued_messages'):
                totals[scalar] = (totals.get(scalar) or 0) + (figures.get(scalar) or 0)
            overdue = (figures.get('overdue') or {}).get('count') or 0
            totals['overdue'] = (totals.get('overdue') or 0) + overdue

        return Response({'totals': totals, 'boutiques': rows})


# -------------------------------------------------------------- search

class SearchView(ConsoleView):
    def get(self, request):
        term = request.query_params.get('q', '')
        limit = _int(request.query_params.get('limit'), search_module.DEFAULT_PER_TYPE,
                     high=search_module.MAX_PER_TYPE)
        return Response({'results': search_module.search(term, list(_boutiques()), limit),
                         'min_term': search_module.MIN_TERM})


# ---------------------------------------------------------- diagnostics

class SupportView(ConsoleView):
    """One boutique, everything a support call needs, in one request.

    Assembled server-side rather than by the console firing six requests: this
    is opened while someone is on the phone, and six round trips over a hosted
    database is the difference between an answer and a wait.
    """

    def get(self, request, schema_name=None):
        tenant = _tenant_or_404(schema_name)
        if tenant is None:
            return Response({'error': 'No such boutique.'}, status=status.HTTP_404_NOT_FOUND)

        with public_scope():
            recent_errors = [
                {'id': e.id, 'exception_type': e.exception_type, 'path': e.path,
                 'count': e.count, 'severity': e.severity, 'status': e.status,
                 'last_seen': e.last_seen}
                # `boutique` holds only the MOST RECENT occurrence, so filtering
                # on it alone hides a bug from every boutique it hit except the
                # one that hit it last -- which on a support call is exactly the
                # error being asked about. `boutiques` is the full list, capped
                # at 20 by core/exceptions.py, and `contains` is a JSON
                # containment test that Postgres can answer directly.
                for e in ErrorEvent.objects.filter(
                    Q(boutique=schema_name) | Q(boutiques__contains=schema_name))[:10]
            ]
            trail = [
                {'actor': a.actor, 'action': a.action, 'action_label': a.get_action_display(),
                 'target': a.target, 'reason': a.reason, 'created_at': a.created_at}
                for a in AuditLog.objects.filter(boutique=schema_name)[:15]
            ]

        # Reading a boutique's diagnostics is itself worth recording: it is the
        # console reaching into one customer's data, which is exactly the class
        # of access an audit trail exists to make reviewable.
        audit.record(request, 'data.view', target='support', boutique=schema_name)

        return Response({
            'boutique': {
                'schema_name': tenant.schema_name, 'name': tenant.name,
                'owner_email': tenant.owner_email, 'created_on': tenant.created_on,
                'is_active': tenant.is_active,
                'enabled_modules': tenant.enabled_modules or {},
            },
            'usage': tenant_metrics(tenant),
            'operations': operational_metrics(tenant),
            'onboarding': onboarding.progress(tenant),
            'users': users_module.list_users([tenant], boutique=schema_name, page_size=100),
            'errors': recent_errors,
            'audit': trail,
            'modules': module_registry.catalogue(),
        })
