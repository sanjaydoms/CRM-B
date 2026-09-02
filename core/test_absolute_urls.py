"""Absolute URLs must carry the scheme the client actually used.

This is not a style point. Django builds absolute URLs in two places that
matter -- the `next` link on a paged list, and the address of an uploaded image
-- and behind a TLS-terminating proxy it believes every request arrived over
http:// unless SECURE_PROXY_SSL_HEADER tells it otherwise. An https page refuses
an http subresource as mixed content, and an Android release build refuses
cleartext outright. So the second page of a list silently never loads and
uploaded photographs never appear, with nothing in any log to say why.
"""

from django.test import RequestFactory, SimpleTestCase, override_settings


class ProxySchemeTests(SimpleTestCase):
    def _uri(self, **extra):
        return RequestFactory().get('/api/customers/', **extra).build_absolute_uri()

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_a_forwarded_https_request_builds_https_urls(self):
        self.assertTrue(self._uri(HTTP_X_FORWARDED_PROTO='https').startswith('https://'))

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_a_forwarded_http_request_still_builds_http_urls(self):
        """The header is trusted, not assumed: a proxy that reports http gets
        http, which is what keeps local development working."""
        self.assertTrue(self._uri(HTTP_X_FORWARDED_PROTO='http').startswith('http://'))

    def test_the_setting_is_what_makes_the_difference(self):
        """Without it -- the state this project was in -- a request that reached
        the edge over TLS is built back as http://."""
        with override_settings(SECURE_PROXY_SSL_HEADER=None):
            self.assertTrue(self._uri(HTTP_X_FORWARDED_PROTO='https').startswith('http://'))
