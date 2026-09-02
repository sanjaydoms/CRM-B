"""The platform console's API.

Everything here runs in the public schema -- SuperadminPinsPublicSchema in
tenants/middleware.py guarantees it -- and answers only to a superuser in that
schema (permissions.IsPlatformAdmin).

Note that every view names its permission class. settings.DEFAULT_PERMISSION_CLASSES
is core.permissions.RolePermission, which resolves a *boutique* role; left to the
default, these endpoints would ask "is this caller the boutique owner?" of a
request that has no boutique, and resolve_user_role answers OWNER for any
superuser. Naming the class is what keeps that from being the platform console's
front door.
"""

from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status, viewsets
from auth_tokens.services import issue_session, revoke_all, rotate
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
    """Every real boutique. The public schema is the registry the console runs
    in, not a tenant, so it never appears in these lists."""
    return BoutiqueTenant.objects.exclude(
        schema_name=get_public_schema_name()).order_by('name')


class PlatformLoginView(APIView):
    """Sign in to the console.

    Separate from crm_api LoginView rather than a flag on it, because the two
    resolve entirely different accounts: that one finds a boutique by owner
    email and authenticates inside that boutique's schema, while this one
    authenticates in the public schema and refuses anyone who is not a superuser
    there.

    A non-superuser who guesses a correct public password is told the same thing
    as someone with the wrong password. Confirming "those credentials are valid,
    you are just not an administrator" tells an attacker which half of the pair
    to keep.
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # a login must not require a session or token
    # The platform console is the one account that can read and suspend every
    # boutique, so it is the single most valuable password on the deployment.
    # Shares crm_api's throttle scope on purpose: both doors draw from one
    # budget per address, so an attacker cannot get two allowances by
    # alternating between them.
    throttle_classes = [LoginThrottle]

    def post(self, request):
        username = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''
        if not username or not password:
            return Response({'error': 'Please provide a username and password.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)
        if user is None or not user.is_superuser or not user.is_active:
            # Charged for a non-superuser with a correct password too. That is
            # someone probing which public account is the administrator, which
            # is the same hunt by another route.
            LoginThrottle.record_failure(request)
            # The attempted username is the `target`, not the `actor`: nobody
            # authenticated, so there is no actor to name, and recording an
            # unverified name in the actor column would put words in the mouth
            # of whoever owns that account.
            #
            # Recorded whether the account exists or not, and the entry does not
            # say which -- the response already refuses to distinguish the two,
            # and an audit trail that does would be a directory of platform
            # administrators for anyone who can read it.
            audit.record(request, 'console.login_failed', target=username)
            return Response({'error': 'Invalid administrator credentials.'},
                            status=status.HTTP_400_BAD_REQUEST)

        session = issue_session(user)
        # The one action every other entry in this trail hangs off. `console.
        # login` and `console.login_failed` were both in AuditLog.ACTIONS from
        # the start and neither was ever written by anything -- so the trail
        # advertised sign-in history it did not keep, which is worse than not
        # offering it: a reviewer reading a boutique's history saw suspensions
        # and password resets with no record of who had been in the console at
        # all, and no indication that half the vocabulary was decorative.
        # `actor` is passed explicitly: this view authenticates with no token, so
        # request.user is still anonymous here and the entry naming who entered
        # the console would otherwise have no name in it. authenticate() has
        # just verified this one.
        audit.record(request, 'console.login', target=user.username,
                     actor=user.username)
        return Response({
            **session,
            'user': {'username': user.username, 'email': user.email},
        })


class PlatformRefreshView(APIView):
    """The console's half of the refresh exchange.

    Separate from the boutique's TokenRefreshView only because everything under
    /api/superadmin/ is pinned to the public schema by the middleware, and that
    pinning is what keeps a boutique's refresh token from being spendable here
    (and the reverse): the two tables are in different schemas, so neither
    lookup can see the other's rows.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = (request.data.get('refresh') or '').strip()
        result = rotate(raw) if raw else None
        if result is None:
            return Response({'error': 'Please sign in again.',
                             'code': 'refresh_invalid'},
                            status=status.HTTP_401_UNAUTHORIZED)
        user, session = result
        if not (user.is_active and user.is_superuser):
            # An account demoted or disabled since the refresh token was issued
            # must not be able to renew its way back into the console.
            revoke_all(user)
            return Response({'error': 'Please sign in again.',
                             'code': 'refresh_invalid'},
                            status=status.HTTP_401_UNAUTHORIZED)
        return Response({
            **session,
            'user': {'username': user.username, 'email': user.email},
        })


class PlatformMeView(APIView):
    """Who the console thinks you are. The portal calls this on load to decide
    whether the token in storage is still worth anything."""

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response({'username': request.user.username,
                         'email': request.user.email})


class PlatformLogoutView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        # Recorded before the token is deleted, not after: record() reads the
        # actor off request.user, and this is the last moment the session it is
        # describing still exists.
        audit.record(request, 'console.logout', target=request.user.username)
        revoke_all(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OverviewView(APIView):
    """The landing screen: the whole product in one payload.

    One response rather than four endpoints the portal would have to fan out to,
    because the per-tenant figures are already being computed to produce the
    totals -- returning the rows as well costs nothing and saves a second pass
    over every schema.
    """

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
    """The boutiques, and the two things the console can do to one.

    Read-only apart from suspend/reactivate. Everything else about a tenant --
    its name, its owner, above all its schema_name -- is either the boutique's
    own to change or is structural: renaming schema_name here would move no
    Postgres schema and would orphan every row in it.
    """

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
        # .update() rather than .save(): BoutiqueTenant is a TenantMixin, and
        # its save() is what creates and migrates Postgres schemas. Toggling a
        # boolean must not be able to trigger any of that.
        BoutiqueTenant.objects.filter(pk=tenant.pk).update(is_active=active)
        # The middleware caches resolved tenants for a few minutes; drop them so
        # this takes effect immediately in this worker. Other gunicorn workers
        # catch up at their own TTL -- see the note in tenants/middleware.py.
        clear_tenant_cache()
        tenant.refresh_from_db()

        # Suspension is the most consequential thing this console does -- it
        # signs an entire boutique out of its own product -- and until this line
        # existed nothing anywhere recorded who did it. `.update()` fires no
        # signal and writes no LogEntry, so "who suspended this boutique, and
        # why" was simply unanswerable. The reason travels from the confirmation
        # dialog the administrator had to fill in.
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
    """Everything a boutique holds, table by table.

    Two shapes on one view: without a `key` it lists every browsable model in
    that boutique with its row count (the drill-down sidebar); with one it
    returns a page of that model's rows. Both run inside schema_context, which
    is the only way to reach a tenant's tables from the public schema this
    console is pinned to.

    Read-only. The console shows a boutique's data; it does not edit it, because
    every rule that keeps that data correct lives in the boutique's own API and
    none of it would run here.

    **Every access writes an audit row**, and this is the most important line in
    the class. This is the highest-privilege read surface the platform has -- it
    reaches one customer's name, address, phone number and measurements inside
    somebody else's business -- and until now it was the only such surface that
    left no trace. SupportView, which reads strictly less, recorded a `data.view`
    entry; browsing crm_api.customer here recorded nothing, so the question "who
    read this boutique's customer list, and when" had no answer anywhere.
    Measured before the fix: two requests returning customer PII, zero audit
    rows.
    """

    permission_classes = [IsPlatformAdmin]

    #: How much of a search term is kept in the trail. The term is what the
    #: administrator was LOOKING for, so it is the substance of the access
    #: rather than decoration -- an entry saying only "searched something" does
    #: not tell a reviewer whether a boutique's records were being combed for
    #: one person. It is bounded because it is caller-supplied text going into a
    #: log, and it is the only query value recorded: page numbers are recorded
    #: as numbers and nothing else from the query string is stored at all.
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
                    # The sidebar is an access too: it reports how many
                    # customers, orders and measurements a boutique holds, which
                    # is a real fact about someone's business even though no row
                    # is rendered. Recorded as a distinct access type so a
                    # reviewer can tell "opened the table list" from "read the
                    # customer table" instead of seeing one undifferentiated
                    # 'data.view' for both.
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
                    # Also the answer for a model that exists but is excluded
                    # (authtoken, say) or simply not on the allowlist. Saying
                    # "that is off limits" would confirm the table is there and
                    # worth asking about.
                    #
                    # Recorded as well: an administrator naming a table the
                    # console will not serve is exactly the attempt worth having
                    # a record of, and a trail that holds only successful reads
                    # cannot show someone probing for one.
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
                # Written after the read rather than before it, so `rows` records
                # what was actually handed over: an entry claiming fifty rows
                # were read when the query returned none is a worse record than
                # no entry.
                audit.record(
                    request, 'data.view', target=key, boutique=schema_name,
                    after={
                        'access': 'rows',
                        'rows': len(page['rows']),
                        'matching': page['count'],
                        'page': page['page'],
                        'page_size': page['page_size'],
                        # Recorded only when there was one, so the common case is
                        # not a column of empty strings.
                        **({'search': search[:self.SEARCH_TERM_LIMIT]} if search else {}),
                    })
                return Response(page)
        except ValueError:
            # A non-numeric ?page= or ?page_size= reaches int() in datasets.rows.
            return Response({'error': 'page and page_size must be numbers.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            # A schema that is missing or half-migrated is exactly what an
            # administrator opens this page to diagnose, so it is reported
            # rather than served as a 500 with nothing in it.
            return Response(
                {'error': f'That boutique\'s schema could not be read: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY)


class LeadViewSet(viewsets.ModelViewSet):
    """Demo requests from the marketing site.

    No create and no destroy: leads arrive through the public intake view
    (tenants/views.py) and are worked here, never typed here. Deleting one would
    destroy the only record that a prospect ever got in touch.
    """

    permission_classes = [IsPlatformAdmin]
    serializer_class = LeadSerializer
    queryset = DemoRequest.objects.all()
    http_method_names = ['get', 'patch', 'head', 'options']

    def perform_update(self, serializer):
        """Save, and record what changed.

        A lead is a real person's enquiry and its status is what decides whether
        anyone follows it up, so "who moved this to Declined" is a question worth
        being able to answer. Only the fields that actually changed are recorded
        -- an audit row restating the whole object on every keystroke of the
        notes box buries the one change that mattered.
        """
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
