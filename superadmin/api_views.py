
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
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    parsed = max(low, parsed)
    return min(parsed, high) if high is not None else parsed


def _tenant_or_404(schema_name):
    return _boutiques().filter(schema_name=schema_name).first()


class ConsoleView(APIView):

    permission_classes = [IsPlatformAdmin]



class UsersView(ConsoleView):

    def get(self, request):
        params = request.query_params
        search = params.get('q', '')
        boutique = params.get('boutique') or None
        page = users_module.list_users(
            list(_boutiques()),
            search=search,
            boutique=boutique,
            role=params.get('role') or None,
            status=params.get('status') or None,
            page=_int(params.get('page'), 1),
            page_size=_int(params.get('page_size'), users_module.DEFAULT_PAGE_SIZE,
                           high=users_module.MAX_PAGE_SIZE),
        )
        audit.record(request, 'data.view', target='users',
                     boutique=boutique or '',
                     after={'access': 'user_directory',
                            'returned': len(page['users']),
                            'matching': page['count'],
                            **({'search': search.strip()[:120]} if search.strip() else {})})
        return Response(page)


class UserActionView(ConsoleView):

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

        audit.record(request, audit_action, target=username, boutique=schema_name,
                     after={'ok': ok, 'result': message},
                     reason=(request.data.get('reason') or '').strip())

        return Response({'ok': ok, 'message': message},
                        status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST)



class OnboardingView(ConsoleView):

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



class ModulesView(ConsoleView):

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
            BoutiqueTenant.objects.filter(pk=tenant.pk).update(enabled_modules=after)

        clear_tenant_cache()

        audit.record(request, 'boutique.modules', target=schema_name,
                     boutique=schema_name, before=before, after=after,
                     reason=(request.data.get('reason') or '').strip())

        return Response({
            'schema_name': schema_name,
            'enabled_modules': after,
            'note': 'Other server workers apply this within 5 minutes.',
        })



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



class ConfigView(ConsoleView):

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

        clear_platform_cache()

        audit.record(request, 'setting.change', target=key, before=before, after=after,
                     reason=(request.data.get('reason') or '').strip())
        return Response({'key': key, 'value': after,
                         'note': 'Other server workers apply this within 5 minutes.'})



class HealthView(ConsoleView):
    def get(self, request):
        results = health.checks()
        rank = ['critical', 'offline', 'degraded', 'warning', 'not_configured', 'healthy']
        worst = next((s for s in rank if any(r['status'] == s for r in results)), 'healthy')
        return Response({'overall': worst, 'checks': results})



class ErrorsView(ConsoleView):

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

    def get(self, request):
        with public_scope():
            open_errors = ErrorEvent.objects.exclude(status__in=('resolved', 'ignored'))
            return Response({
                'unresolved': open_errors.count(),
                'critical': open_errors.filter(severity='critical').count(),
            })


class ErrorDetailView(ConsoleView):

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



class AuditView(ConsoleView):

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



class OrdersMonitorView(ConsoleView):

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



class SearchView(ConsoleView):

    def get(self, request):
        term = request.query_params.get('q', '')
        limit = _int(request.query_params.get('limit'), search_module.DEFAULT_PER_TYPE,
                     high=search_module.MAX_PER_TYPE)
        results = search_module.search(term, list(_boutiques()), limit)

        if len((term or '').strip()) >= search_module.MIN_TERM:
            audit.record(request, 'data.view', target='search',
                         after={'access': 'search',
                                'search': term.strip()[:120],
                                'hits': len(results)})
        return Response({'results': results, 'min_term': search_module.MIN_TERM})



class SupportView(ConsoleView):

    def get(self, request, schema_name=None):
        tenant = _tenant_or_404(schema_name)
        if tenant is None:
            return Response({'error': 'No such boutique.'}, status=status.HTTP_404_NOT_FOUND)

        with public_scope():
            recent_errors = [
                {'id': e.id, 'exception_type': e.exception_type, 'path': e.path,
                 'count': e.count, 'severity': e.severity, 'status': e.status,
                 'last_seen': e.last_seen}
                for e in ErrorEvent.objects.filter(
                    Q(boutique=schema_name) | Q(boutiques__contains=schema_name))[:10]
            ]
            trail = [
                {'actor': a.actor, 'action': a.action, 'action_label': a.get_action_display(),
                 'target': a.target, 'reason': a.reason, 'created_at': a.created_at}
                for a in AuditLog.objects.filter(boutique=schema_name)[:15]
            ]

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
