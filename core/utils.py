"""Shared guards for the scripts that are not part of the running product."""

import os

from django.conf import settings


def refuse_unless_local_database():
    """Stop a destructive seed script from running against a hosted database.

    seed_mock_orders.py opens by deleting every OrderStageHistory, Order,
    Customer, Notification and Tailor row, and it does that inside a loop over
    every non-public tenant. seed_data.py and seed_v2_tasks.py write rows into
    whatever database they find.

    None of them chooses a database. settings.py points at the Supabase pooler
    unless USE_LOCAL_DB is 'True', and that variable is exported by exactly one
    thing -- start.sh. A developer who runs `python seed_mock_orders.py` by hand
    inherits the production defaults, and the first thing that happens is every
    boutique's order book being deleted. There is no confirmation prompt and no
    dry run.

    So the check is on the connection that is actually configured rather than on
    the environment variable: DB_HOST can be pointed at a hosted instance
    directly, and USE_LOCAL_DB is not the only way to get there. The variable is
    honoured too, because a test database name will not look local on its own.

    Not a warning, and not a prompt. A prompt is answered 'y' by reflex at the
    end of a long day, which is the exact moment this matters.
    """
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
