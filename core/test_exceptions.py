"""What the error feed must contain, and what it must never contain.

The value of this feed is entirely in its grouping. An error store that files a
row per crash is unreadable by the second day, and one that files client
validation errors alongside real crashes is unreadable by the first afternoon --
so the tests that matter here are the ones about what does *not* create a row.

The views below are the whole point of the module-level URLconf: capture only
runs inside real request handling, so a genuine request has to reach something
that genuinely raises. Half of them are deliberately NOT DRF views -- the defect
that motivated the current capture point is that DRF-only capture saw neither
the public tracking page nor the tenant middleware.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, connection
from django.http import HttpResponse
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.urls import path
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient, APIRequestFactory

from boutique_crm.settings import _log_level
from core.exceptions import _BOUTIQUE_LIST_LIMIT, _record
from superadmin.models import ErrorEvent


@api_view(['GET'])
@permission_classes([AllowAny])
def boom(request, pk=None):
    raise ValueError('deliberate crash')


@api_view(['GET'])
@permission_classes([AllowAny])
def db_boom(request):
    raise IntegrityError('deliberate constraint violation')


@api_view(['GET'])
@permission_classes([AllowAny])
def refuse(request):
    raise ValidationError({'size': 'That is not a size.'})


@require_GET
def plain_boom(request):
    """The shape of crm_api.tracking_views.order_tracking and
    tenants.views.demo_request: no DRF anywhere in the call stack."""
    raise ValueError('deliberate crash in a plain django view')


def middleware_boom(get_response):
    """The shape of a TenantHeaderMiddleware crash -- before any view runs."""
    def middleware(request):
        if request.path == '/middleware-boom/':
            raise RuntimeError('deliberate crash in middleware')
        return get_response(request)
    return middleware


def ok(request):
    return HttpResponse('ok')


urlpatterns = [
    path('boom/', boom),
    path('boom/<int:pk>/', boom),
    # Same function, different endpoint: the only thing separating this from
    # /boom/ in a fingerprint is the path.
    path('elsewhere/', boom),
    path('db-boom/', db_boom),
    path('refuse/', refuse),
    path('plain-boom/', plain_boom),
    # Never reached; middleware_boom raises first. It exists so the request
    # fails in the middleware rather than at URL resolution.
    path('middleware-boom/', ok),
]


@override_settings(ROOT_URLCONF=__name__)
class ErrorCaptureTests(TransactionTestCase):
    def setUp(self):
        connection.set_schema_to_public()
        self.client = APIClient()
        # The exception is re-raised past DRF on purpose, and the test client
        # would re-raise it here instead of letting Django return the 500 that a
        # real client sees.
        self.client.raise_request_exception = False

        # Every one of these requests logs a full traceback through
        # django.request, which is the point of the LOGGING config and pure
        # noise in a test run.
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def bare_schema(self, schema_name):
        """A real but EMPTY Postgres schema, created for the life of the test.

        These tests used to name a schema that did not exist, on the reasoning
        that `set_schema` only changes what the *next* query would use. That is
        no longer legal: tenants/schema_guard.py refuses to point the connection
        at a schema that is not there, because Postgres silently resolves such a
        query against `public` and that fallthrough was a real vulnerability.

        An empty schema keeps every assertion below exactly as it was -- the
        point is that ErrorEvent is written to `public` from a connection
        pointed somewhere else, and an empty schema is pointed somewhere else
        just as well as an imaginary one. It is also closer to the situation
        being described: a half-migrated boutique.
        """
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA IF NOT EXISTS "%s"' % schema_name)
        self.addCleanup(self._drop_schema, schema_name)
        return schema_name

    def _drop_schema(self, schema_name):
        connection.set_schema_to_public()
        with connection.cursor() as cursor:
            cursor.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema_name)
        from superadmin.schemas import forget
        forget(schema_name)

    def crash(self, url='/boom/'):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        return response

    def test_a_drf_exception_is_recorded_exactly_once(self):
        """The double-count this capture point had to be traced to avoid.

        DRF's handle_exception calls EXCEPTION_HANDLER and, when it returns
        None, re-raises -- so the exception reaches Django and fires
        got_request_exception too. If platform_exception_handler also recorded,
        one request would be two occurrences here, and `count` would mean
        something different for a DRF view than for a plain one.
        """
        self.crash()
        self.assertEqual(ErrorEvent.objects.get().count, 1)

    def test_a_plain_django_view_is_recorded(self):
        # The public tracking page. It never touches DRF dispatch, so nothing
        # recorded it while capture hung off EXCEPTION_HANDLER -- the customer
        # tracking page could 500 on every link a boutique sent out and the
        # console would still report the platform healthy.
        self.crash('/plain-boom/')
        event = ErrorEvent.objects.get()
        self.assertEqual(event.exception_type, 'ValueError')
        self.assertEqual(event.path, '/plain-boom/')
        self.assertEqual(event.count, 1)

    def test_a_middleware_crash_is_recorded(self):
        # TenantHeaderMiddleware runs on every request and before every view.
        # Nothing downstream of a view could ever have seen this one.
        with override_settings(MIDDLEWARE=['core.test_exceptions.middleware_boom']
                                          + list(settings.MIDDLEWARE)):
            self.crash('/middleware-boom/')
        event = ErrorEvent.objects.get()
        self.assertEqual(event.exception_type, 'RuntimeError')
        self.assertEqual(event.count, 1)

    def test_an_unhandled_exception_is_recorded(self):
        self.crash()
        event = ErrorEvent.objects.get()
        self.assertEqual(event.exception_type, 'ValueError')
        self.assertEqual(event.path, '/boom/')
        self.assertEqual(event.method, 'GET')
        self.assertEqual(event.status_code, 500)
        self.assertEqual(event.status, 'new')
        self.assertEqual(event.severity, 'high')
        self.assertEqual(event.count, 1)

    def test_the_same_crash_twice_is_one_row_with_a_count_of_two(self):
        self.crash()
        self.crash()
        self.assertEqual(ErrorEvent.objects.count(), 1)
        self.assertEqual(ErrorEvent.objects.get().count, 2)

    def test_an_id_in_the_path_does_not_split_one_bug_into_many(self):
        # The whole reason paths are normalised: one broken endpoint hit across
        # an order book would otherwise be one row per order.
        self.crash('/boom/1/')
        self.crash('/boom/2/')
        self.assertEqual(ErrorEvent.objects.count(), 1)
        self.assertEqual(ErrorEvent.objects.get().count, 2)

    def test_a_different_path_is_a_different_bug(self):
        self.crash('/boom/')
        self.crash('/elsewhere/')
        self.assertEqual(ErrorEvent.objects.count(), 2)
        self.assertEqual(sorted(ErrorEvent.objects.values_list('path', flat=True)),
                         ['/boom/', '/elsewhere/'])

    def test_a_validation_error_records_nothing(self):
        self.assertEqual(self.client.get('/refuse/').status_code, 400)
        self.assertEqual(ErrorEvent.objects.count(), 0)

    def test_a_database_error_is_critical(self):
        self.crash('/db-boom/')
        self.assertEqual(ErrorEvent.objects.get().severity, 'critical')

    def test_a_resolved_error_reopens_when_it_happens_again(self):
        self.crash()
        ErrorEvent.objects.update(status='resolved')
        self.crash()
        event = ErrorEvent.objects.get()
        self.assertEqual(event.status, 'new')
        self.assertEqual(event.count, 2)

    def test_an_ignored_error_stays_ignored(self):
        # Ignoring is a standing decision about a known-noisy error. If a
        # recurrence undid it, it could never be made to stick.
        self.crash()
        ErrorEvent.objects.update(status='ignored')
        self.crash()
        self.assertEqual(ErrorEvent.objects.get().status, 'ignored')

    def test_the_traceback_holds_only_this_project(self):
        self.crash()
        stored = ErrorEvent.objects.get().traceback
        self.assertIn('core/test_exceptions.py', stored)
        self.assertIn('raise ValueError', stored)
        for marker in ('site-packages', 'dist-packages', '/.venv/'):
            self.assertNotIn(marker, stored)

    def test_a_boutique_crash_is_written_to_public_and_leaves_the_schema_alone(self):
        """The case that would silently corrupt the feed.

        ErrorEvent exists only in public, but a crash almost always happens on a
        request whose connection is pointed at a boutique's schema. No query is
        ever issued against the fake schema below -- set_schema only changes what
        the *next* query would use -- so this needs no tenant and still exercises
        the exact switch that matters.
        """
        request = APIRequestFactory().get('/api/orders/7/')
        request.user = AnonymousUser()
        try:
            raise ValueError('crashed inside a boutique')
        except ValueError as exc:
            connection.set_schema(self.bare_schema('boutique_elsewhere'))
            try:
                _record(exc, request)
                self.assertEqual(connection.schema_name, 'boutique_elsewhere')
            finally:
                connection.set_schema_to_public()

        event = ErrorEvent.objects.get()
        self.assertEqual(event.boutique, 'boutique_elsewhere')
        self.assertEqual(event.boutiques, ['boutique_elsewhere'])
        self.assertEqual(event.path, '/api/orders/7/')

    def crash_as(self, schema_name, path='/api/orders/7/'):
        """One occurrence of the same bug, as `schema_name`.

        No query is issued against the fake schema -- set_schema only changes
        what the next query would use -- so this needs no real tenant.
        """
        request = APIRequestFactory().get(path)
        request.user = AnonymousUser()
        try:
            raise ValueError('one bug, many boutiques')
        except ValueError as exc:
            connection.set_schema(self.bare_schema(schema_name))
            try:
                _record(exc, request)
            finally:
                connection.set_schema_to_public()

    def test_every_affected_boutique_is_kept_not_just_the_latest(self):
        # The lie: `boutique` is overwritten on every occurrence, so a bug
        # hitting three boutiques reported the third and made the first two
        # unattributable -- while the index and the console's search column
        # present that field as THE affected boutique.
        for schema in ('boutique_a', 'boutique_b', 'boutique_c'):
            self.crash_as(schema)

        event = ErrorEvent.objects.get()
        self.assertEqual(event.count, 3)
        self.assertEqual(event.boutiques, ['boutique_a', 'boutique_b', 'boutique_c'])
        # Still the most recent, which is now all it claims to be.
        self.assertEqual(event.boutique, 'boutique_c')

    def test_the_same_boutique_twice_is_listed_once(self):
        self.crash_as('boutique_a')
        self.crash_as('boutique_a')
        event = ErrorEvent.objects.get()
        self.assertEqual(event.count, 2)
        self.assertEqual(event.boutiques, ['boutique_a'])

    def test_the_boutique_list_is_capped(self):
        # Updated on every occurrence and never trimmed, this would grow with
        # the tenant count forever.
        for n in range(_BOUTIQUE_LIST_LIMIT + 5):
            self.crash_as(f'boutique_{n}')
        self.assertEqual(len(ErrorEvent.objects.get().boutiques), _BOUTIQUE_LIST_LIMIT)

    def test_a_public_schema_crash_lists_no_boutique(self):
        self.crash()
        event = ErrorEvent.objects.get()
        self.assertEqual(event.boutique, '')
        self.assertEqual(event.boutiques, [])


class LogLevelTests(SimpleTestCase):
    """DJANGO_LOG_LEVEL=info used to kill every worker inside django.setup()."""

    def test_a_lowercase_level_is_accepted(self):
        self.assertEqual(_log_level('info'), 'INFO')

    def test_a_nonsense_level_falls_back_instead_of_raising(self):
        for raw in ('verbose', '', '   ', None, 'TRUE'):
            self.assertEqual(_log_level(raw), 'WARNING')

    def test_every_answer_is_one_dictconfig_accepts(self):
        # The actual failure was dictConfig rejecting the value, so assert
        # against dictConfig rather than against a list copied out of it.
        import logging.config
        # dictConfig is process-global; put the real config back or every test
        # that runs after this one logs through whatever the last loop iteration
        # left behind.
        self.addCleanup(logging.config.dictConfig, settings.LOGGING)
        for raw in ('debug', 'INFO', 'warn', 'nonsense', None):
            logging.config.dictConfig({
                'version': 1,
                'disable_existing_loggers': False,
                'root': {'level': _log_level(raw)},
            })
