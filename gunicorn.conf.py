"""Gunicorn configuration for the Render deployment.

Used via `gunicorn -c gunicorn.conf.py boutique_crm.wsgi:application`.

The reason this file exists: gunicorn's defaults are one sync worker with one
thread, so the API served exactly one request at a time. The dashboard opens by
firing eight requests at once (dashboard, customers, orders, tailors, fabrics,
designs, settings, notifications), so seven of them sat in the accept queue
waiting their turn. Each one is mostly *waiting on the database*, not burning
CPU, which is the case threads exist for.
"""

import os

# Threads, not processes, are what this workload wants: every request is blocked
# on Postgres for nearly its whole life, and threads share memory where a second
# Django process would double the footprint. Render's smallest instances are
# memory-bound, so a modest worker count with several threads each gives real
# concurrency without another full interpreter per worker.
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = 'gthread'

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Total database connections this process can hold is workers * threads, which
# is what keeps CONN_MAX_AGE safe against Supabase's pooler -- see the DATABASES
# comment in settings.py. Changing either number above changes that budget.

# The default 30s timeout kills a worker mid-request on a slow upload or a cold
# database connection, which surfaces to the user as a dropped request rather
# than a slow one.
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30

# Recycle workers periodically so a slow leak can never accumulate across a long
# uptime. The jitter stops every worker from restarting on the same request.
max_requests = 1000
max_requests_jitter = 100

# Render routes through its own proxy; without this every request logs and
# builds absolute URLs (media, images) from the internal address.
forwarded_allow_ips = '*'

accesslog = '-'
errorlog = '-'
