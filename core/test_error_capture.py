"""
The four error kinds that were invisible before, and the rules that keep them
from swamping the one that was not.

`core/test_exceptions.py` still owns crashes. This file owns everything the
product *handles*: exceptions it catches and logs, refusals its own platform
controls issue, 4xx it returns on purpose, and crashes that happen in a browser.
"""

import logging
from contextlib import contextmanager

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, OperationalError, connection
from django.test import Client, TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.test import APIClient, APIRequestFactory

from core.exceptions import (NO_RESPONSE, ErrorEventLogHandler, record_exception,
                             record_frontend, record_refusal)
from superadmin.models import ErrorEvent, PlatformSetting
from tenants.middleware import clear_platform_cache, clear_tenant_cache
from tenants.tests import temporary_tenant


class QuietConsole:
    """
    Keeps the ERROR records flowing -- the capture handler needs them -- while
    keeping them off the test runner's output. `logging.disable`, which the
    crash tests use, would switch off the very thing under test here.
    """

    def __enter__(self):
        self.silenced = [h for h in logging.getLogger().handlers
                         if isinstance(h, logging.StreamHandler)
                         and not isinstance(h, ErrorEventLogHandler)]
        self.levels = [h.level for h in self.silenced]
        for handler in self.silenced:
            handler.setLevel(logging.CRITICAL + 1)
        return self

    def __exit__(self, *exc):
        for handler, level in zip(self.silenced, self.levels):
            handler.setLevel(level)
        return False


@contextmanager
def broken_writer():
    """
    Makes the ErrorEvent write fail the way a lost database would, and records
    how many times it was attempted so a recursion shows up as a count.
    """
    attempts = []
    original = ErrorEvent.objects.update_or_create

    def fail(*args, **kwargs):
        attempts.append(1)
        raise OperationalError('the database went away')

    ErrorEvent.objects.update_or_create = fail
    try:
        yield attempts
    finally:
        ErrorEvent.objects.update_or_create = original


class HandledExceptionTests(TransactionTestCase):
    """
    A caught exception that the code logged and carried on from. Captured by a
    logging handler rather than by editing the ~49 catch sites, so the ones
    written next month are captured too.
    """

    def setUp(self):
        connection.set_schema_to_public()

    def log_a_failure(self, logger_name='apps.email_service.services.email_service',
                      exc=None, message='Failed to send email to recipients'):
        logger = logging.getLogger(logger_name)
        with QuietConsole():
            try:
                raise exc or RuntimeError('smtp refused the connection')
            except Exception:
                logger.exception(message)

    def test_a_swallowed_failure_becomes_a_visible_row(self):
        self.log_a_failure()
        event = ErrorEvent.objects.get()
        self.assertEqual(event.kind, 'handled')
        self.assertEqual(event.exception_type, 'RuntimeError')
        self.assertEqual(event.severity, 'medium')

    def test_the_row_names_the_module_that_swallowed_it(self):
        self.log_a_failure()
        event = ErrorEvent.objects.get()
        self.assertEqual(event.source, 'apps.email_service.services.email_service')
        self.assertIn('Failed to send email', event.message)
        self.assertIn('smtp refused the connection', event.message)

    def test_the_traceback_is_kept_so_the_row_is_actionable(self):
        self.log_a_failure()
        stored = ErrorEvent.objects.get().traceback
        self.assertIn('core/test_error_capture.py', stored)
        for vendor in ('site-packages', 'dist-packages', '/.venv/'):
            self.assertNotIn(vendor, stored)

    def test_a_handled_error_carries_no_status_code(self):
        # It never became a response. 0 says so; 500 would be a lie about a
        # request that in fact succeeded.
        self.log_a_failure()
        self.assertEqual(ErrorEvent.objects.get().status_code, NO_RESPONSE)

    def test_a_swallowed_database_error_is_still_critical(self):
        # The code carried on, but a write may have been lost. Severity follows
        # the consequence, not whether anybody caught it.
        self.log_a_failure(exc=IntegrityError('constraint'))
        self.assertEqual(ErrorEvent.objects.get().severity, 'critical')

    def test_a_log_line_without_an_exception_records_nothing(self):
        with QuietConsole():
            logging.getLogger('apps.inventory').error('stock went negative')
        self.assertEqual(ErrorEvent.objects.count(), 0)

    def test_a_warning_with_an_exception_records_nothing(self):
        # The handler sits at ERROR. A warning is somebody saying "this is fine".
        with QuietConsole():
            try:
                raise RuntimeError('recoverable')
            except RuntimeError:
                logging.getLogger('apps.inventory').warning('retrying', exc_info=True)
        self.assertEqual(ErrorEvent.objects.count(), 0)

    def test_django_request_is_not_captured_twice(self):
        # django.request logs exactly the unhandled 500s that
        # got_request_exception has already filed as a crash. Capturing them
        # here as well would double every crash: one row with a traceback and
        # one without.
        self.log_a_failure(logger_name='django.request')
        self.assertEqual(ErrorEvent.objects.count(), 0)

    def test_the_same_failure_twice_is_one_row(self):
        self.log_a_failure()
        self.log_a_failure()
        self.assertEqual(ErrorEvent.objects.count(), 1)
        self.assertEqual(ErrorEvent.objects.get().count, 2)

    def test_recording_never_raises_into_the_caller(self):
        # The whole point of capturing swallowed errors is lost if the capture
        # turns a swallowed error into a crash. The database going away is the
        # realistic way this fails, so the writer is made to fail outright.
        request = APIRequestFactory().get('/api/orders/')
        request.user = AnonymousUser()
        with QuietConsole(), broken_writer():
            try:
                raise ValueError('boom')
            except ValueError as exc:
                self.assertIsNone(record_exception(exc, request=request))
        self.assertEqual(ErrorEvent.objects.count(), 0)

    def test_a_failure_inside_the_writer_does_not_recurse(self):
        # The writer failing logs, and that log would be captured, and that
        # capture would fail and log. The latch is what stops it; without it
        # this test does not fail, it hangs or blows the stack.
        request = APIRequestFactory().get('/api/orders/')
        request.user = AnonymousUser()
        with QuietConsole(), broken_writer() as attempts:
            try:
                raise ValueError('boom')
            except ValueError as exc:
                record_exception(exc, request=request)
        self.assertEqual(len(attempts), 1)


class RefusalTests(TransactionTestCase):
    """
    The console's own controls, saying no. None of these were recorded before,
    so an operator could switch a module off and have no way to see it bite.
    """

    def setUp(self):
        connection.set_schema_to_public()
        clear_tenant_cache()
        clear_platform_cache()
        self.addCleanup(clear_tenant_cache)
        self.addCleanup(clear_platform_cache)

    def test_a_suspended_boutique_leaves_a_trace(self):
        with temporary_tenant('refuse_susp', 'owner@refuse.test', 'Refused') as tenant:
            tenant.is_active = False
            tenant.save(update_fields=['is_active'])
            clear_tenant_cache()

            response = Client().get('/api/customers/', HTTP_X_TENANT_ID='refuse_susp')
            self.assertEqual(response.status_code, 403)

            connection.set_schema_to_public()
            event = ErrorEvent.objects.get(kind='refusal')
            self.assertEqual(event.exception_type, 'BoutiqueSuspended')
            self.assertEqual(event.status_code, 403)
            self.assertEqual(event.boutique, 'refuse_susp')
            self.assertEqual(event.severity, 'low')

    def test_a_switched_off_module_is_named_in_the_row(self):
        # The module goes in the identity, not just the message, so two modules
        # switched off are two rows rather than one that keeps rewriting itself.
        with temporary_tenant('refuse_mod', 'owner@refuse.test', 'Refused') as tenant:
            tenant.enabled_modules = {'fabrics': False}
            tenant.save(update_fields=['enabled_modules'])
            clear_tenant_cache()

            self.assertEqual(
                Client().get('/api/fabrics/', HTTP_X_TENANT_ID='refuse_mod').status_code, 403)

            connection.set_schema_to_public()
            event = ErrorEvent.objects.get(kind='refusal')
            self.assertEqual(event.exception_type, 'ModuleDisabled:fabrics')
            self.assertEqual(event.boutique, 'refuse_mod')

    def test_an_unknown_tenant_is_recorded(self):
        response = Client().get('/api/customers/', HTTP_X_TENANT_ID='no_such_boutique')
        self.assertEqual(response.status_code, 400)

        connection.set_schema_to_public()
        self.assertEqual(
            ErrorEvent.objects.get(kind='refusal').exception_type, 'UnknownTenant')

    def test_maintenance_mode_is_recorded(self):
        PlatformSetting.objects.update_or_create(
            key='maintenance_mode',
            defaults={'value': {'enabled': True, 'message': 'Back shortly.'}})
        clear_platform_cache()

        response = Client().get('/api/customers/')
        self.assertEqual(response.status_code, 503)

        connection.set_schema_to_public()
        self.assertEqual(
            ErrorEvent.objects.get(kind='refusal').exception_type, 'MaintenanceMode')

    def test_refusals_do_not_become_crashes(self):
        Client().get('/api/customers/', HTTP_X_TENANT_ID='no_such_boutique')
        connection.set_schema_to_public()
        self.assertEqual(ErrorEvent.objects.filter(kind='crash').count(), 0)

    def test_a_refusal_that_cannot_be_recorded_still_refuses(self):
        # Recording is best-effort. The refusal is not: a boutique whose
        # suspension stopped applying because an unrelated write failed would be
        # a security control undone by a logging bug.
        with temporary_tenant('refuse_broken', 'owner@refuse.test', 'Refused') as tenant:
            tenant.is_active = False
            tenant.save(update_fields=['is_active'])
            clear_tenant_cache()

            with QuietConsole(), broken_writer():
                response = Client().get('/api/customers/',
                                        HTTP_X_TENANT_ID='refuse_broken')
            self.assertEqual(response.status_code, 403)

            connection.set_schema_to_public()
            self.assertEqual(ErrorEvent.objects.count(), 0)


class FrontendCrashTests(TransactionTestCase):
    """
    A React crash in the boutique workspace. The server answered every request
    correctly and the user saw a white screen; this is the only way it hears.
    """

    URL = '/api/client-errors/'

    def setUp(self):
        connection.set_schema_to_public()
        self.client = APIClient()

    def report(self, **payload):
        return self.client.post(self.URL, payload, format='json')

    def test_a_browser_crash_is_recorded(self):
        response = self.report(name='TypeError', message="can't read 'map' of undefined",
                               stack='at OrderList (App.jsx:2140)', route='/orders')
        self.assertEqual(response.status_code, 204)

        event = ErrorEvent.objects.get()
        self.assertEqual(event.kind, 'frontend')
        self.assertEqual(event.exception_type, 'TypeError')
        self.assertEqual(event.path, '/orders')
        self.assertEqual(event.source, 'browser')

    def test_a_white_screen_is_not_low_severity(self):
        self.report(name='TypeError', message='boom', stack='at X (App.jsx:1)')
        self.assertEqual(ErrorEvent.objects.get().severity, 'high')

    def test_it_carries_no_status_code(self):
        self.report(name='TypeError', message='boom')
        self.assertEqual(ErrorEvent.objects.get().status_code, NO_RESPONSE)

    def test_two_components_throwing_the_same_message_are_two_rows(self):
        # A React error message is usually the same sentence wherever it is
        # raised, so without the throw site every crash in the app collapses
        # into one useless row.
        self.report(name='TypeError', message='same', stack='at OrderList (App.jsx:2140)')
        self.report(name='TypeError', message='same', stack='at Customers (App.jsx:5100)')
        self.assertEqual(ErrorEvent.objects.filter(kind='frontend').count(), 2)

    def test_an_empty_report_is_refused(self):
        self.assertEqual(self.report(stack='at X').status_code, 400)
        self.assertEqual(ErrorEvent.objects.filter(kind='frontend').count(), 0)

    def test_oversized_fields_cannot_grow_the_row(self):
        # A public write endpoint. Length caps are the reason it can be one.
        self.report(name='E' * 5000, message='M' * 50000, stack='S' * 100000,
                    route='R' * 5000)
        event = ErrorEvent.objects.get()
        self.assertLessEqual(len(event.exception_type), 200)
        self.assertLessEqual(len(event.message), 2000)
        self.assertLessEqual(len(event.traceback), 4000)
        self.assertLessEqual(len(event.path), 300)

    def test_the_endpoint_survives_a_module_being_switched_off(self):
        # It is in ALWAYS_ON, because a switched-off module is exactly when the
        # frontend is most likely to break.
        with temporary_tenant('fe_mod', 'owner@fe.test', 'FE') as tenant:
            tenant.enabled_modules = {key: False for key in ('fabrics', 'inventory')}
            tenant.save(update_fields=['enabled_modules'])
            clear_tenant_cache()
            self.addCleanup(clear_tenant_cache)

            client = APIClient()
            response = client.post(self.URL, {'name': 'TypeError', 'message': 'boom'},
                                   format='json', HTTP_X_TENANT_ID='fe_mod')
            self.assertEqual(response.status_code, 204)


class ErrorFeedScopeTests(TransactionTestCase):
    """
    The Error Center must stay a crash feed. Everything above writes to the same
    table, and two of the kinds are high-volume by nature.
    """

    def setUp(self):
        connection.set_schema_to_public()
        ErrorEvent.objects.all().delete()
        for kind in ('crash', 'handled', 'refusal', 'client', 'frontend'):
            ErrorEvent.objects.create(
                fingerprint=f'fp-{kind}', kind=kind, exception_type=f'{kind}Error',
                message='x', path=f'/{kind}/', severity='low', status='new')

    def api(self):
        from superadmin.api_views import ErrorsView
        return ErrorsView

    def get(self, **params):
        from django.contrib.auth.models import User

        from superadmin.api_views import ErrorsView
        factory = APIRequestFactory()
        request = factory.get('/api/superadmin/errors/', params)
        request.user = User(username='platform', is_superuser=True, is_staff=True)
        return ErrorsView.as_view()(request).data

    def test_the_feed_shows_crashes_by_default(self):
        data = self.get()
        self.assertEqual([row['kind'] for row in data['errors']], ['crash'])

    def test_a_kind_can_be_asked_for(self):
        data = self.get(kind='refusal')
        self.assertEqual([row['kind'] for row in data['errors']], ['refusal'])

    def test_all_lifts_the_filter(self):
        self.assertEqual(self.get(kind='all')['count'], 5)

    def test_an_unknown_kind_is_refused_rather_than_ignored(self):
        # Ignoring it would silently serve crashes to a caller that asked for
        # something else, which is the worst of the three options.
        from superadmin.api_views import ErrorsView
        from django.contrib.auth.models import User
        request = APIRequestFactory().get('/api/superadmin/errors/', {'kind': 'nonsense'})
        request.user = User(username='platform', is_superuser=True, is_staff=True)
        self.assertEqual(ErrorsView.as_view()(request).status_code, 400)

    def test_the_badge_counts_crashes_only(self):
        # Otherwise one switched-off module pins it at several hundred, which is
        # the state the badge most needs to stay readable in.
        summary = self.get()['summary']
        self.assertEqual(summary['unresolved'], 1)
        self.assertEqual(summary['by_kind']['refusal'], 1)
        self.assertEqual(sum(summary['by_kind'].values()), 5)

    def test_the_health_probe_separates_faults_from_refusals(self):
        from superadmin.health import _errors
        state, detail = _errors()
        # crash + handled + frontend = 3 faults; the refusal is reported apart.
        self.assertIn('3 unresolved', detail)
        self.assertIn('1 platform refusal', detail)


class ReturnedClientErrorTests(TransactionTestCase):
    """
    The 4xx that never raise.

    `platform_exception_handler` only ever sees a thrown exception, which in this
    project is 31 `raise ValidationError(...)` sites. The other 149 are plain
    `return Response({...}, status=400)`. Capturing only the first group would
    have filled the Client tab with a sixth of the client errors the product
    returns while looking like all of them.
    """

    def setUp(self):
        connection.set_schema_to_public()
        self.client = APIClient()
        clear_tenant_cache()
        self.addCleanup(clear_tenant_cache)

    def test_a_returned_4xx_is_captured_even_though_nothing_raised(self):
        # LoginView returns this; it does not raise it.
        response = self.client.post('/api/auth/login/', {}, format='json')
        self.assertEqual(response.status_code, 400)

        event = ErrorEvent.objects.get(kind='client')
        self.assertEqual(event.status_code, 400)
        self.assertEqual(event.path, '/api/auth/login/')

    def test_the_row_names_the_view_and_not_an_invented_exception(self):
        # Nothing was raised, so there is no exception class. Putting one in
        # front of an operator would be a fiction; the status is the only
        # classification the response actually carries.
        self.client.post('/api/auth/login/', {}, format='json')
        event = ErrorEvent.objects.get(kind='client')
        self.assertEqual(event.exception_type, 'HTTP 400')
        self.assertEqual(event.source, 'LoginView')
        self.assertTrue(event.message)

    def test_a_refusal_is_filed_once_as_a_refusal(self):
        # The middleware sits outside the tenant switcher, so it sees refusals
        # too. Those already filed themselves with a reason worth more than a
        # status code, so this must leave them alone.
        with temporary_tenant('ret_mod', 'owner@ret.test', 'Ret') as tenant:
            tenant.enabled_modules = {'fabrics': False}
            tenant.save(update_fields=['enabled_modules'])
            clear_tenant_cache()

            self.assertEqual(
                Client().get('/api/fabrics/', HTTP_X_TENANT_ID='ret_mod').status_code, 403)

            connection.set_schema_to_public()
            self.assertEqual(ErrorEvent.objects.filter(kind='client').count(), 0)
            self.assertEqual(
                ErrorEvent.objects.get(kind='refusal').exception_type,
                'ModuleDisabled:fabrics')

    def test_the_ingest_endpoints_own_refusal_is_not_a_product_error(self):
        # "Nothing to report" is the crash reporter being told off, not the
        # product failing anybody.
        self.assertEqual(
            self.client.post('/api/client-errors/', {}, format='json').status_code, 400)
        self.assertEqual(ErrorEvent.objects.count(), 0)

    def test_the_message_is_the_sentence_not_a_python_repr(self):
        # DRF's shape is {'detail': ErrorDetail(...)}, and str() of that prints
        # the repr. An operator scanning this feed should read the sentence the
        # caller received, not DRF's internals.
        response = self.client.get('/api/superadmin/overview/')
        self.assertEqual(response.status_code, 401)

        event = ErrorEvent.objects.get(kind='client')
        self.assertEqual(event.message, 'Authentication credentials were not provided.')
        self.assertNotIn('ErrorDetail', event.message)

    def test_a_returned_error_body_is_reported_verbatim(self):
        self.client.post('/api/auth/login/', {}, format='json')
        self.assertEqual(ErrorEvent.objects.get(kind='client').message,
                         'Please provide email/username and password')

    def test_a_request_that_succeeds_records_nothing(self):
        response = self.client.post(
            '/api/client-errors/', {'name': 'TypeError', 'message': 'boom'}, format='json')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(ErrorEvent.objects.filter(kind='client').count(), 0)
