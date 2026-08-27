
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
    raise ValueError('deliberate crash in a plain django view')


def middleware_boom(get_response):
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
    path('elsewhere/', boom),
    path('db-boom/', db_boom),
    path('refuse/', refuse),
    path('plain-boom/', plain_boom),
    path('middleware-boom/', ok),
]


@override_settings(ROOT_URLCONF=__name__)
class ErrorCaptureTests(TransactionTestCase):
    def setUp(self):
        connection.set_schema_to_public()
        self.client = APIClient()
        self.client.raise_request_exception = False

        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def bare_schema(self, schema_name):
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
        self.crash()
        self.assertEqual(ErrorEvent.objects.get().count, 1)

    def test_a_plain_django_view_is_recorded(self):
        self.crash('/plain-boom/')
        event = ErrorEvent.objects.get()
        self.assertEqual(event.exception_type, 'ValueError')
        self.assertEqual(event.path, '/plain-boom/')
        self.assertEqual(event.count, 1)

    def test_a_middleware_crash_is_recorded(self):
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
        for schema in ('boutique_a', 'boutique_b', 'boutique_c'):
            self.crash_as(schema)

        event = ErrorEvent.objects.get()
        self.assertEqual(event.count, 3)
        self.assertEqual(event.boutiques, ['boutique_a', 'boutique_b', 'boutique_c'])
        self.assertEqual(event.boutique, 'boutique_c')

    def test_the_same_boutique_twice_is_listed_once(self):
        self.crash_as('boutique_a')
        self.crash_as('boutique_a')
        event = ErrorEvent.objects.get()
        self.assertEqual(event.count, 2)
        self.assertEqual(event.boutiques, ['boutique_a'])

    def test_the_boutique_list_is_capped(self):
        for n in range(_BOUTIQUE_LIST_LIMIT + 5):
            self.crash_as(f'boutique_{n}')
        self.assertEqual(len(ErrorEvent.objects.get().boutiques), _BOUTIQUE_LIST_LIMIT)

    def test_a_public_schema_crash_lists_no_boutique(self):
        self.crash()
        event = ErrorEvent.objects.get()
        self.assertEqual(event.boutique, '')
        self.assertEqual(event.boutiques, [])


class LogLevelTests(SimpleTestCase):

    def test_a_lowercase_level_is_accepted(self):
        self.assertEqual(_log_level('info'), 'INFO')

    def test_a_nonsense_level_falls_back_instead_of_raising(self):
        for raw in ('verbose', '', '   ', None, 'TRUE'):
            self.assertEqual(_log_level(raw), 'WARNING')

    def test_every_answer_is_one_dictconfig_accepts(self):
        import logging.config
        self.addCleanup(logging.config.dictConfig, settings.LOGGING)
        for raw in ('debug', 'INFO', 'warn', 'nonsense', None):
            logging.config.dictConfig({
                'version': 1,
                'disable_existing_loggers': False,
                'root': {'level': _log_level(raw)},
            })
