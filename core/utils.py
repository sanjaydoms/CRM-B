

import os

from django.conf import settings


def refuse_unless_local_database():
    host = settings.DATABASES['default'].get('HOST', '')
    is_local = (
        os.environ.get('USE_LOCAL_DB') == 'True'
        or host in ('127.0.0.1', 'localhost', '::1', '')
    )
    if not is_local:
        raise SystemExit(
            f"Refusing to run: the configured database is {host!r}, which is "
            f"not local.\n"
            f"This script deletes and rewrites rows. Run it against a local "
            f"database with:\n\n"
            f"  USE_LOCAL_DB=True python {os.path.basename(__import__('sys').argv[0])}\n"
        )
