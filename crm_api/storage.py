"""Where uploaded files actually live.

Until now: nowhere durable. `STORAGES['default']` was FileSystemStorage and the
service runs on an ephemeral disk, so every fabric photograph, design reference
and customer profile picture uploaded since the last deploy was deleted BY the
next deploy. The comment in boutique_crm/urls.py has said so in writing for
months. On the web that is a slow leak somebody notices eventually. On a phone,
where photographing the garment IS the workflow, it is the product not working.

This driver existed and was bypassed, for a reason worth recording rather than
rediscovering: `SUPABASE_KEY` is the *publishable* key. Storage RLS refuses
writes made with it, so uploads failed and the bypass was the workaround. The
fix is not a different bucket policy -- it is the right credential. Writes use
`SUPABASE_SERVICE_KEY`, which is a server-side secret and must never reach the
browser, the Android bundle, a Vite variable or an API response.

Reads need no credential at all: the `boutique-crm` bucket is public, so `url()`
returns the public object URL and the browser fetches it directly rather than
proxying every image through Django. What that means, said plainly rather than
left implicit: **anyone who has an object's URL can fetch it without signing
in.** The paths carry UUIDs so they cannot be guessed or enumerated, and this is
the same exposure the product already had -- `/media/` is served with no
authentication whatsoever (boutique_crm/urls.py). If customer photographs need
to be private, that is a bucket policy change plus signed URLs here, and signed
URLs cost one API round trip per image per render, which is why they are not the
default.
"""

import logging
import mimetypes
from io import BytesIO
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

logger = logging.getLogger(__name__)

#: Every call is a network round trip inside a request the user is waiting on.
#: Unbounded, one unhealthy storage endpoint holds a gunicorn worker forever and
#: the API stops answering -- for orders and customers too, not just images.
TIMEOUT = (5, 30)


@deconstructible
class SupabaseStorage(Storage):
    def __init__(self, bucket_name=None, supabase_url=None, supabase_key=None):
        self.bucket_name = bucket_name or getattr(settings, 'SUPABASE_BUCKET', 'boutique-crm')
        self.supabase_url = (supabase_url or getattr(settings, 'SUPABASE_URL', '')).rstrip('/')
        # The service key when there is one, and only then a fall back to the
        # publishable key -- which can read but cannot write, so a deployment
        # that forgets the service key fails on upload with a 4xx from Supabase
        # rather than appearing to work.
        self.supabase_key = (
            supabase_key
            or getattr(settings, 'SUPABASE_SERVICE_KEY', '')
            or getattr(settings, 'SUPABASE_KEY', '')
        )

    # --- addressing -------------------------------------------------------

    def _object_url(self, name):
        return f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{quote(name)}"

    def _headers(self, extra=None):
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "ApiKey": self.supabase_key,
        }
        if extra:
            headers.update(extra)
        return headers

    # --- Storage API ------------------------------------------------------

    def _open(self, name, mode='rb'):
        res = requests.get(self._object_url(name), headers=self._headers(),
                           timeout=TIMEOUT)
        if res.status_code == 200:
            return BytesIO(res.content)
        raise FileNotFoundError(f"{name} is not in the {self.bucket_name} bucket")

    def _save(self, name, content):
        content.seek(0)
        body = content.read()
        mime_type, _ = mimetypes.guess_type(name)
        headers = self._headers({
            "Content-Type": mime_type or 'application/octet-stream',
            # Django has already made the name unique via get_available_name,
            # so an upsert here overwrites only a name we just proved was free
            # -- a race between two uploads, where losing the file is worse than
            # overwriting a half-written duplicate.
            "x-upsert": "true",
        })

        res = requests.post(self._object_url(name), headers=headers, data=body,
                            timeout=TIMEOUT)
        if res.status_code not in (200, 201):
            # The response text is logged, never raised to the caller: it can
            # carry the bucket policy and, on some errors, the request headers.
            logger.error("supabase upload of %s failed: %s %s",
                         name, res.status_code, res.text[:500])
            raise IOError(
                f"Could not store {name}. The upload was refused by storage "
                f"({res.status_code}).")
        return name

    def exists(self, name):
        res = requests.head(self._object_url(name), headers=self._headers(),
                            timeout=TIMEOUT)
        return res.status_code == 200

    def size(self, name):
        """Django asks for this whenever a template or serializer reads .size."""
        res = requests.head(self._object_url(name), headers=self._headers(),
                            timeout=TIMEOUT)
        if res.status_code != 200:
            raise FileNotFoundError(name)
        return int(res.headers.get('Content-Length', 0))

    def url(self, name):
        return (f"{self.supabase_url}/storage/v1/object/public/"
                f"{self.bucket_name}/{quote(name)}")

    def delete(self, name):
        res = requests.delete(self._object_url(name), headers=self._headers(),
                              timeout=TIMEOUT)
        # 404 is not a failure: the caller wanted the object gone and it is.
        if res.status_code not in (200, 404):
            logger.warning("supabase delete of %s answered %s", name, res.status_code)
        return res.status_code in (200, 404)
