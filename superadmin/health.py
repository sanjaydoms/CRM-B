
import os
import tempfile
import time

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count, Q
from django_tenants.utils import get_public_schema_name, schema_context

from tenants.models import BoutiqueTenant

from .metrics import tenant_metrics

SLOW_QUERY_MS = 250
VERY_SLOW_QUERY_MS = 1000


def _boutiques():
    return BoutiqueTenant.objects.exclude(schema_name=get_public_schema_name())


def _database():
    started = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    ms = (time.perf_counter() - started) * 1000

    if ms >= VERY_SLOW_QUERY_MS:
        return 'degraded', f'Answering, but a trivial query took {ms:.0f}ms.'
    if ms >= SLOW_QUERY_MS:
        return 'warning', f'Reachable, {ms:.0f}ms for a trivial query -- slow.'
    return 'healthy', f'Reachable, {ms:.0f}ms for a trivial query.'


def _migrations():
    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    shared = {app.rsplit('.', 1)[-1] for app in settings.SHARED_APPS}
    targets = [node for node in executor.loader.graph.leaf_nodes()
               if node[0] in shared]
    plan = executor.migration_plan(targets)

    if not plan:
        return 'healthy', 'Public schema is up to date with SHARED_APPS.'
    names = ', '.join(f'{migration.app_label}.{migration.name}'
                      for migration, _backwards in plan[:5])
    more = f' (+{len(plan) - 5} more)' if len(plan) > 5 else ''
    return 'warning', f'{len(plan)} unapplied in public: {names}{more}.'


def _tenant_schemas():
    tenants = list(_boutiques())
    if not tenants:
        return 'healthy', 'No boutiques on this platform yet.'

    healthy = sum(1 for tenant in tenants if tenant_metrics(tenant)['healthy'])
    detail = f'{healthy} of {len(tenants)} boutique schemas readable.'
    if healthy == len(tenants):
        return 'healthy', detail
    if healthy == 0:
        return 'critical', detail + ' None of them responded.'
    return 'degraded', detail + ' The rest are missing or half-migrated.'


def _media_storage():
    root = str(settings.MEDIA_ROOT)
    ephemeral = ('Uploads go to the local disk -- STORAGES default is '
                 'FileSystemStorage -- which on Render does not survive a '
                 'redeploy.')

    if not os.path.isdir(root):
        return 'warning', (f'{root} does not exist yet. FileSystemStorage '
                           f'creates it on the first upload, so this is normal '
                           f'on a fresh deploy. {ephemeral}')
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix='.healthcheck-'):
            pass
    except OSError as exc:
        return 'critical', f'{root} is not writable: {exc}'
    return 'healthy', f'{root} exists and is writable. {ephemeral}'


def _email():
    if not settings.EMAIL_HOST:
        return 'not_configured', (
            'No EMAIL_HOST, so EMAIL_BACKEND is the console backend: password '
            'reset links are printed to this server\'s stdout and never posted. '
            'Password reset is the only thing in this product that sends mail.')
    return 'healthy', (
        f'SMTP configured: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}. Not '
        f'probed -- opening a connection or sending a test message would be a '
        f'side effect on somebody else\'s mail server.')


def _supabase_storage():
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        return 'not_configured', (
            'Credentials are set but unused: STORAGES["default"] is '
            'FileSystemStorage, so crm_api/storage.py is bypassed entirely (the '
            'bucket\'s RLS policies reject the publishable key).')
    return 'not_configured', (
        'No SUPABASE_URL/SUPABASE_KEY, and setting them would change nothing: '
        'STORAGES["default"] is FileSystemStorage, so crm_api/storage.py is '
        'bypassed entirely.')


def _errors():
    from .models import ErrorEvent

    counts = ErrorEvent.objects.exclude(status__in=('resolved', 'ignored')).aggregate(
        total=Count('id'), critical=Count('id', filter=Q(severity='critical')))
    if counts['critical']:
        return 'critical', (f'{counts["critical"]} unresolved critical error(s), '
                            f'{counts["total"]} unresolved in total.')
    return 'healthy', (f'No unresolved critical errors. {counts["total"]} '
                       f'unresolved at lower severities.')


def _whatsapp():
    from crm_api.models import CustomerMessage

    queued = 0
    unreadable = 0
    for tenant in _boutiques():
        try:
            with schema_context(tenant.schema_name):
                queued += CustomerMessage.objects.filter(status='QUEUED').count()
        except Exception:
            unreadable += 1

    unread_note = (f' {unreadable} schema(s) could not be read, so the real '
                   f'backlog may be higher.' if unreadable else '')
    backend = getattr(settings, 'CUSTOMER_MESSAGE_BACKEND', '')
    if backend:
        return 'healthy', (f'Delivered by {backend}. {queued} message(s) '
                           f'queued.{unread_note}')
    return 'not_configured', (
        f'By design: messages are wa.me links the boutique owner sends from '
        f'their own phone, and CUSTOMER_MESSAGE_BACKEND is unset on purpose. '
        f'{queued} message(s) queued and waiting to be sent by hand.'
        f'{unread_note}')


def _payments():
    return 'not_configured', (
        'No payment gateway exists in this product. An order\'s amount_paid is '
        'what staff recorded by hand; nothing is charged, captured or settled.')


def _background_jobs():
    return 'not_configured', (
        'No job queue exists in this product. Everything happens inside the '
        'request that asked for it -- there is no worker to be down.')


def _sms():
    return 'not_configured', 'No SMS provider exists in this product.'


_CHECKS = (
    ('database', 'Database', _database),
    ('migrations', 'Migrations', _migrations),
    ('tenant_schemas', 'Boutique schemas', _tenant_schemas),
    ('media_storage', 'Media storage', _media_storage),
    ('email', 'Outbound email', _email),
    ('supabase_storage', 'Supabase storage', _supabase_storage),
    ('errors', 'Error feed', _errors),
    ('whatsapp', 'Customer messaging', _whatsapp),
    ('payments', 'Payments', _payments),
    ('background_jobs', 'Background jobs', _background_jobs),
    ('sms', 'SMS', _sms),
)


def checks():
    results = []
    for key, label, probe in _CHECKS:
        try:
            status, detail = probe()
        except Exception as exc:
            status, detail = 'degraded', f'This check could not run: {exc}'
        results.append({'key': key, 'label': label, 'status': status,
                        'detail': detail})
    return results
