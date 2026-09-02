"""The upload driver, checked without a network.

Storage failures are the kind that look fine in development -- where the disk is
real and permanent -- and lose a boutique's photographs in production. So the
things asserted here are the things that differ between the two: which
credential is used, what happens when the bucket refuses a write, and whether a
call can hang forever.
"""

from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from crm_api.storage import SupabaseStorage


class FakeResponse:
    def __init__(self, status_code=200, content=b'', headers=None, text=''):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.text = text


@override_settings(SUPABASE_URL='https://project.supabase.co',
                   SUPABASE_KEY='publishable-key',
                   SUPABASE_SERVICE_KEY='service-key',
                   SUPABASE_BUCKET='boutique-crm')
class SupabaseStorageTests(SimpleTestCase):
    def setUp(self):
        self.storage = SupabaseStorage()

    def test_writes_use_the_service_key_not_the_publishable_one(self):
        """The whole reason this driver was bypassed. The publishable key can
        read; only the service key can write, and using the wrong one fails at
        upload time in production and nowhere else."""
        with patch('crm_api.storage.requests.post',
                   return_value=FakeResponse(200)) as post:
            name = self.storage._save('designs/a.jpg', ContentFile(b'bytes'))

        self.assertEqual(name, 'designs/a.jpg')
        headers = post.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer service-key')
        self.assertEqual(headers['ApiKey'], 'service-key')
        self.assertEqual(headers['Content-Type'], 'image/jpeg')
        self.assertEqual(
            post.call_args.args[0],
            'https://project.supabase.co/storage/v1/object/boutique-crm/designs/a.jpg')

    def test_a_refused_upload_raises_and_does_not_repeat_the_bucket_error(self):
        refusal = FakeResponse(403, text='{"error":"new row violates policy ..."}')
        with patch('crm_api.storage.requests.post', return_value=refusal):
            with self.assertRaises(IOError) as caught:
                self.storage._save('designs/a.jpg', ContentFile(b'bytes'))

        message = str(caught.exception)
        self.assertIn('403', message)
        # The upstream text can carry bucket policy detail, and this message
        # reaches an API caller.
        self.assertNotIn('policy', message)

    def test_every_call_is_bounded_by_a_timeout(self):
        """An unbounded request to a sick storage endpoint holds a gunicorn
        worker open, and the API stops answering for orders too."""
        with patch('crm_api.storage.requests.post', return_value=FakeResponse(200)) as post, \
             patch('crm_api.storage.requests.get', return_value=FakeResponse(200, b'x')) as get, \
             patch('crm_api.storage.requests.head',
                   return_value=FakeResponse(200, headers={'Content-Length': '1'})) as head, \
             patch('crm_api.storage.requests.delete', return_value=FakeResponse(200)) as delete:
            self.storage._save('a.txt', ContentFile(b'x'))
            self.storage._open('a.txt')
            self.storage.exists('a.txt')
            self.storage.size('a.txt')
            self.storage.delete('a.txt')

        for call in (post, get, head, delete):
            self.assertIsNotNone(call.call_args.kwargs.get('timeout'),
                                 f'{call} was made with no timeout')

    def test_the_public_url_is_the_one_a_browser_can_fetch(self):
        self.assertEqual(
            self.storage.url('design refs/a b.jpg'),
            'https://project.supabase.co/storage/v1/object/public/boutique-crm/'
            'design%20refs/a%20b.jpg')

    def test_deleting_something_already_gone_is_success(self):
        with patch('crm_api.storage.requests.delete', return_value=FakeResponse(404)):
            self.assertTrue(self.storage.delete('gone.jpg'))

    def test_exists_is_false_when_the_object_is_not_there(self):
        with patch('crm_api.storage.requests.head', return_value=FakeResponse(404)):
            self.assertFalse(self.storage.exists('gone.jpg'))

    @override_settings(SUPABASE_SERVICE_KEY='')
    def test_falls_back_to_the_publishable_key_only_when_there_is_no_service_key(self):
        self.assertEqual(SupabaseStorage().supabase_key, 'publishable-key')
