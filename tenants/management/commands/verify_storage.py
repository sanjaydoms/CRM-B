"""Prove that an upload survives.

The question this answers is the one a unit test cannot: does the storage this
particular environment is configured with actually keep a file, and can it be
read back afterwards -- by the server, and by a browser with no credentials, the
way an <img> tag does.

    python manage.py verify_storage

It writes one small object with a random name, reads it back three ways, and
deletes it. Run it after a deploy, and again after the NEXT deploy without the
--cleanup flag if you want to see persistence across releases with your own
eyes:

    python manage.py verify_storage --keep --name release-check.txt   # deploy 1
    python manage.py verify_storage --read release-check.txt          # deploy 2

That second form is the deployment-persistence test. Nothing else in this
repository can tell you the difference between object storage and a disk that is
about to be thrown away, because on the day of the deploy they behave
identically.
"""

import uuid

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import BaseCommand, CommandError

BODY = b'boutique-crm storage check\n'


class Command(BaseCommand):
    help = "Write, read and delete one object through the configured file storage."

    def add_arguments(self, parser):
        parser.add_argument('--name', default='', help='Object name to write (default: random).')
        parser.add_argument('--keep', action='store_true',
                            help='Leave the object in place, to be read after a later deploy.')
        parser.add_argument('--read', default='',
                            help='Only read an object written by an earlier run.')

    def handle(self, *args, **options):
        # default_storage is a lazy proxy, so its own class name is always
        # 'DefaultStorage'. isinstance sees through it to the real backend.
        on_disk = isinstance(default_storage, FileSystemStorage)
        self.stdout.write(
            f'storage backend: {type(default_storage._wrapped).__name__}')
        if on_disk:
            self.stdout.write(self.style.WARNING(
                'This environment stores uploads on the local disk. On a host '
                'with an ephemeral filesystem every uploaded file is destroyed '
                'by the next deploy. Set SUPABASE_SERVICE_KEY to switch to '
                'object storage.'))

        if options['read']:
            return self._read_back(options['read'], expect_public=not on_disk)

        name = options['name'] or f'storage-checks/{uuid.uuid4()}.txt'
        saved = default_storage.save(name, ContentFile(BODY))
        self.stdout.write(f'wrote:  {saved}')

        self._read_back(saved, expect_public=not on_disk)

        if options['keep']:
            self.stdout.write(self.style.SUCCESS(
                f'kept. After the next deploy, run:\n'
                f'  python manage.py verify_storage --read {saved}'))
            return

        default_storage.delete(saved)
        if default_storage.exists(saved):
            raise CommandError('delete() reported success but the object is still there.')
        self.stdout.write(self.style.SUCCESS('write, read, public read and delete all passed.'))

    def _read_back(self, name, expect_public):
        if not default_storage.exists(name):
            raise CommandError(f'{name} is not there. Nothing was persisted.')

        with default_storage.open(name) as handle:
            if handle.read() != BODY:
                raise CommandError(f'{name} read back with different contents.')
        self.stdout.write(f'read:   {name} ({default_storage.size(name)} bytes)')

        url = default_storage.url(name)
        self.stdout.write(f'url:    {url}')
        if not expect_public or not url.startswith('http'):
            return

        # The check that matters for an <img> tag: fetched with no credentials
        # at all, exactly as a browser will fetch it.
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            raise CommandError(
                f'The public URL answered {response.status_code}. The object is '
                f'stored but no browser can display it -- the bucket is probably '
                f'not public.')
        self.stdout.write(self.style.SUCCESS('public URL is readable with no credentials.'))
