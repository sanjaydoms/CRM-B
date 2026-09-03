
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from crm_api.auth_views import LoginThrottle

from tenants.middleware import clear_tenant_cache
from tenants.models import BoutiqueTenant, DemoRequest

from . import audit, datasets
from .metrics import platform_totals
from .permissions import IsPlatformAdmin
from .serializers import LeadSerializer, TenantSerializer


def _boutiques():
    return BoutiqueTenant.objects.exclude(
        schema_name=get_public_schema_name()).order_by('name')


class PlatformLoginView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []  # a login must not require a session or token
    throttle_classes = [LoginThrottle]

    def post(self, request):
        username = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''
        if not username or not password:
            return Response({'error': 'Please provide a username and password.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)
        if user is None or not user.is_superuser or not user.is_active:
            LoginThrottle.record_failure(request)
            audit.record(request, 'console.login_failed', target=username)
            return Response({'error': 'Invalid administrator credentials.'},
                            status=status.HTTP_400_BAD_REQUEST)

        token, _ = Token.objects.get_or_create(user=user)
        audit.record(request, 'console.login', target=user.username,
                     actor=user.username)
        return Response({
            'token': token.key,
            'user': {'username': user.username, 'email': user.email},
        })


class PlatformMeView(APIView):

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response({'username': request.user.username,
                         'email': request.user.email})


class PlatformLogoutView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        audit.record(request, 'console.logout', target=request.user.username)
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OverviewView(APIView):

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        tenants = list(_boutiques())
        totals = platform_totals(tenants)

        since = timezone.now() - timedelta(days=30)
        leads = DemoRequest.objects.aggregate(
            total=Count('id'),
            new=Count('id', filter=Q(status='NEW')),
            last_30_days=Count('id', filter=Q(created_at__gte=since)),
        )
        return Response({
            'totals': totals,
            'leads': leads,
            'boutiques': TenantSerializer(tenants, many=True).data,
            'administrators': User.objects.filter(is_superuser=True, is_active=True).count(),
        })


class TenantViewSet(viewsets.ViewSet):

    permission_classes = [IsPlatformAdmin]

    def list(self, request):
        return Response(TenantSerializer(list(_boutiques()), many=True).data)

    def retrieve(self, request, schema_name=None):
        tenant = _boutiques().filter(schema_name=schema_name).first()
        if tenant is None:
            return Response({'error': 'No such boutique.'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(TenantSerializer(tenant).data)

    def _set_active(self, request, schema_name, active):
        tenant = _boutiques().filter(schema_name=schema_name).first()
        if tenant is None:
            return Response({'error': 'No such boutique.'},
                            status=status.HTTP_404_NOT_FOUND)

        was_active = tenant.is_active
        BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=active)
        clear_tenant_cache()
        tenant.refresh_from_db()

        audit.record(
            request,
            'boutique.reactivate' if active else 'boutique.suspend',
            target=schema_name, boutique=schema_name,
            before={'is_active': was_active}, after={'is_active': active},
            reason=(request.data.get('reason') or '').strip(),
        )
        return Response(TenantSerializer(tenant).data)

    def suspend(self, request, schema_name=None):
        return self._set_active(request, schema_name, False)

    def reactivate(self, request, schema_name=None):
        return self._set_active(request, schema_name, True)


class BoutiqueDataView(APIView):

    permission_classes = [IsPlatformAdmin]

    SEARCH_TERM_LIMIT = 120

    def get(self, request, schema_name=None, key=None):
        tenant = _boutiques().filter(schema_name=schema_name).first()
        if tenant is None:
            return Response({'error': 'No such boutique.'},
                            status=status.HTTP_404_NOT_FOUND)

        search = (request.query_params.get('q') or '').strip()

        try:
            with schema_context(tenant.schema_name):
                if key is None:
                    listed = datasets.inventory()
                    audit.record(request, 'data.view', target='datasets',
                                 boutique=schema_name,
                                 after={'access': 'model_index',
                                        'models': len(listed)})
                    return Response({
                        'boutique': {'schema_name': tenant.schema_name, 'name': tenant.name},
                        'datasets': listed,
                    })

                model = datasets.get_model(key)
                if model is None:
                    audit.record(request, 'data.view', target=key,
                                 boutique=schema_name,
                                 after={'access': 'refused', 'reason': 'not_browsable'})
                    return Response({'error': 'No such dataset.'},
                                    status=status.HTTP_404_NOT_FOUND)

                page = datasets.rows(
                    model,
                    page=request.query_params.get('page', 1),
                    page_size=request.query_params.get('page_size'),
                    search=search,
                )
                audit.record(
                    request, 'data.view', target=key, boutique=schema_name,
                    after={
                        'access': 'rows',
                        'rows': len(page['rows']),
                        'matching': page['count'],
                        'page': page['page'],
                        'page_size': page['page_size'],
                        **({'search': search[:self.SEARCH_TERM_LIMIT]} if search else {}),
                    })
                return Response(page)
        except ValueError:
            return Response({'error': 'page and page_size must be numbers.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {'error': f'That boutique\'s schema could not be read: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY)


class LeadViewSet(viewsets.ModelViewSet):

    permission_classes = [IsPlatformAdmin]
    serializer_class = LeadSerializer
    queryset = DemoRequest.objects.all()
    http_method_names = ['get', 'patch', 'head', 'options']

    def perform_update(self, serializer):
        lead = serializer.instance
        before = {field: getattr(lead, field) for field in serializer.validated_data}
        instance = serializer.save()
        after = {field: getattr(instance, field) for field in serializer.validated_data}
        changed = {field for field in after if before.get(field) != after.get(field)}
        if changed:
            audit.record(
                self.request, 'lead.update', target=f'lead:{instance.pk}',
                before={f: before[f] for f in changed},
                after={f: after[f] for f in changed},
            )
