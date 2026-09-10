
from contextlib import contextmanager

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django.urls import get_resolver
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from superadmin.permissions import IsPlatformAdmin
from tenants.models import BoutiqueTenant, Domain

PUBLIC_ROUTES = {'/api/superadmin/auth/login/'}


@contextmanager
def temporary_tenant(schema_name, owner_email, name):
    connection.set_schema_to_public()
    tenant = BoutiqueTenant(schema_name=schema_name, owner_email=owner_email, name=name)
    tenant.save()
    Domain.objects.create(domain=f'{schema_name}.localhost', tenant=tenant, is_primary=True)
    try:
        yield tenant
    finally:
        connection.set_schema_to_public()
        tenant.delete(force_drop=True)


def console_routes():

    found = []

    def walk(patterns, prefix=''):
        for entry in patterns:
            if hasattr(entry, 'url_patterns'):
                walk(entry.url_patterns, prefix + str(entry.pattern))
            else:
                found.append((prefix + str(entry.pattern), entry.callback))

    walk(get_resolver().url_patterns)
    return [(p, cb) for p, cb in found if p.startswith('api/superadmin/')]


def concrete_url(pattern):
    url = '/' + pattern
    substitutions = {
        '<str:schema_name>': 'no_such_boutique', '<str:username>': 'nobody',
        '<str:action>': 'revoke', '<str:key>': 'no.such.key', '<int:pk>': '1',
        '(?P<pk>[^/.]+)': '1',
    }
    for token, value in substitutions.items():
        url = url.replace(token, value)
    return url


class PerimeterTests(TransactionTestCase):


    def setUp(self):
        connection.set_schema_to_public()

    def test_every_route_declares_the_platform_permission(self):
        missing = []
        for pattern, callback in console_routes():
            url = concrete_url(pattern)
            if url in PUBLIC_ROUTES or '(?P<format>' in pattern or 'format_suffix' in pattern:
                continue
            view_class = getattr(callback, 'cls', None) or getattr(callback, 'view_class', None)
            if view_class is None:
                continue
            classes = getattr(view_class, 'permission_classes', [])
            if IsPlatformAdmin not in classes:
                missing.append(f'{pattern} -> {view_class.__name__} has {classes}')
        self.assertEqual(missing, [], 'Console views without IsPlatformAdmin:\n'
                                      + '\n'.join(missing))

    def test_anonymous_is_refused_everywhere(self):
        client = APIClient()
        allowed = []
        for pattern, _cb in console_routes():
            url = concrete_url(pattern)
            if url in PUBLIC_ROUTES or '(?P<format>' in pattern:
                continue
            for method in ('get', 'post', 'patch', 'put', 'delete'):
                response = getattr(client, method)(url)
                if response.status_code not in (401, 403, 404, 405):
                    allowed.append(f'{method.upper()} {url} -> {response.status_code}')
        self.assertEqual(allowed, [], 'Anonymous callers reached:\n' + '\n'.join(allowed))

    def test_a_boutique_superuser_token_is_refused_everywhere(self):
        with temporary_tenant('sec_rogue', 'owner@rogue.test', 'Rogue Atelier'):
            with schema_context('sec_rogue'):
                rogue = User.objects.create_superuser(
                    username='rogue@rogue.test', email='rogue@rogue.test', password='pw')
                key = Token.objects.get_or_create(user=rogue)[0].key

            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION='Token ' + key,
                               HTTP_X_TENANT_ID='sec_rogue')

            reached = []
            for pattern, _cb in console_routes():
                url = concrete_url(pattern)
                if url in PUBLIC_ROUTES or '(?P<format>' in pattern:
                    continue
                response = client.get(url)
                if response.status_code not in (401, 403, 404, 405):
                    reached.append(f'GET {url} -> {response.status_code}')
            self.assertEqual(reached, [], 'A boutique superuser reached:\n' + '\n'.join(reached))

    def test_a_plain_public_user_is_refused_everywhere(self):
        User.objects.filter(username='plain@perimeter.test').delete()
        user = User.objects.create_user(username='plain@perimeter.test', password='pw')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)

        reached = []
        for pattern, _cb in console_routes():
            url = concrete_url(pattern)
            if url in PUBLIC_ROUTES or '(?P<format>' in pattern:
                continue
            response = client.get(url)
            if response.status_code not in (401, 403, 404, 405):
                reached.append(f'GET {url} -> {response.status_code}')
        self.assertEqual(reached, [], 'A non-superuser reached:\n' + '\n'.join(reached))


class SecretsTests(TransactionTestCase):


    def setUp(self):
        connection.set_schema_to_public()

    def _admin(self):
        User.objects.filter(username='sec@admin.test').delete()
        User.objects.create_superuser(username='sec@admin.test', email='sec@admin.test',
                                      password='sec-admin-pass')
        client = APIClient()
        response = client.post('/api/superadmin/auth/login/',
                               {'username': 'sec@admin.test', 'password': 'sec-admin-pass'},
                               format='json')
        assert response.status_code == 200, response.content
        self.token = response.json()['token']
        client.credentials(HTTP_AUTHORIZATION='Token ' + self.token)
        return client

    def test_no_response_contains_a_password_hash_or_a_token_key(self):
        with temporary_tenant('sec_leak', 'owner@leak.test', 'Leak Atelier'):
            with schema_context('sec_leak'):
                staff = User.objects.create_user(username='staff@leak.test',
                                                 password='a-password-to-hash')
                staff_token = Token.objects.get_or_create(user=staff)[0].key

            client = self._admin()
            urls = [
                '/api/superadmin/overview/',
                '/api/superadmin/users/',
                '/api/superadmin/users/?boutique=sec_leak',
                '/api/superadmin/search/?q=staff',
                '/api/superadmin/boutiques/sec_leak/data/auth.user/',
                '/api/superadmin/support/sec_leak/',
                '/api/superadmin/config/',
                '/api/superadmin/health/',
            ]
            for url in urls:
                body = client.get(url).content.decode()
                self.assertNotIn('pbkdf2', body, url)
                self.assertNotIn('argon2', body, url)
                self.assertNotIn('a-password-to-hash', body, url)
                self.assertNotIn(staff_token, body, url)

    def test_config_reports_credential_presence_but_never_values(self):
        from django.test import override_settings

        with override_settings(SUPABASE_KEY='super-secret-key-value',
                               SUPABASE_URL='https://example.supabase.co',
                               DESIGN_STUDIO_GOOGLE_API_KEY='google-secret-abc'):
            body = self._admin().get('/api/superadmin/config/').content.decode()
        self.assertNotIn('super-secret-key-value', body)
        self.assertNotIn('google-secret-abc', body)
        self.assertIn('supabase', body)
