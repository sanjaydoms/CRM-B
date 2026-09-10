
import os

workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = 'gthread'

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"


timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30

max_requests = 1000
max_requests_jitter = 100

forwarded_allow_ips = '*'

accesslog = '-'
errorlog = '-'
