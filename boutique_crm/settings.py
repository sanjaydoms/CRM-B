
import getpass
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip().strip('\'"'))



_load_dotenv(BASE_DIR / '.env')



DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

_DEV_SECRET_KEY = 'django-insecure-local-development-only-do-not-use-in-production'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG or 'test' in sys.argv:
        SECRET_KEY = _DEV_SECRET_KEY
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. It signs the customer tracking "
            "links, so running on the development key published in this "
            "repository would let anyone mint a link to any order in any "
            "boutique. Generate one with:\n\n"
            "  python -c \"from django.core.management.utils import "
            "get_random_secret_key; print(get_random_secret_key())\"\n\n"
            "and set it in the environment. Rotating it invalidates tracking "
            "links already sent to customers, which is intended."
        )
elif SECRET_KEY == _DEV_SECRET_KEY and not (DEBUG or 'test' in sys.argv):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is set to the development key that is published in "
        "this repository. Generate a real one; see the comment in "
        "boutique_crm/settings.py."
    )

ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',') if h]



SHARED_APPS = [
    'django_tenants',  
    'tenants',
    'superadmin',
    # Owns no models, so it adds no migration to either schema set. Installed
    # only so CoreConfig.ready() imports core.checks -- the module registry's
    # guards have to be registered to fail a deploy.
    'core',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'apps.email_service',
    'cloudinary',
    'cloudinary_storage',
]

TENANT_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'rest_framework.authtoken',
    'crm_api',
    'apps.production',
    'apps.activities',
    'apps.scheduling',
    'apps.design_studio',
    'apps.inventory',
    'apps.catalog',
    'apps.staff',
    'apps.payroll',
    'apps.finance',
    'apps.alterations',
]

INSTALLED_APPS = list(set(SHARED_APPS + TENANT_APPS))

MIDDLEWARE = [
    'core.exceptions.capture_middleware',
    # Outermost real middleware, so it sees the final status of every request --
    # including the ones TenantHeaderMiddleware refuses before a view is
    # reached. Those file themselves with a reason, and set a marker this reads,
    # so a refusal is recorded once as a refusal rather than twice.
    'core.exceptions.ClientErrorMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'tenants.middleware.TenantHeaderMiddleware',  
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'boutique_crm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'boutique_crm.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.environ.get('DB_NAME', 'postgres'),
        'USER': os.environ.get('DB_USER', 'postgres.gbdabwahffdgdykbujpx'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'aws-1-ap-southeast-1.pooler.supabase.com'),
        'PORT': os.environ.get('DB_PORT', '5432'),

        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'OPTIONS': {
            'connect_timeout': int(os.environ.get('DB_CONNECT_TIMEOUT', '10')),
            **({'sslmode': os.environ['DB_SSLMODE']}
               if os.environ.get('DB_SSLMODE') else {}),
            **({'sslrootcert': os.environ['DB_SSLROOTCERT']}
               if os.environ.get('DB_SSLROOTCERT') else {}),
        },
    }
}

def _os_account():

    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return getpass.getuser()


_running_tests = 'test' in sys.argv
_use_local_db = os.environ.get('USE_LOCAL_DB')
if _use_local_db is None and _running_tests:
    _use_local_db = 'True'
_local_db = (_use_local_db == 'True')

if _local_db and not (DEBUG or _running_tests):
    raise ImproperlyConfigured(
        "USE_LOCAL_DB=True with DEBUG=False. Refusing to point a production "
        "process at a development database. Unset USE_LOCAL_DB and set "
        "DB_NAME, DB_USER, DB_PASSWORD and DB_HOST."
    )

if _local_db:
    DATABASES['default'].update({
        'NAME': os.environ.get('LOCAL_DB_NAME', 'boutique_crm'),
        'USER': os.environ.get('LOCAL_DB_USER', _os_account()),
        'PASSWORD': os.environ.get('LOCAL_DB_PASSWORD', ''),
        'HOST': os.environ.get('LOCAL_DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('LOCAL_DB_PORT', '5432'),
    })

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

TENANT_LIMIT_SET_CALLS = False

TENANT_MODEL = 'tenants.BoutiqueTenant'

TENANT_BASE_SCHEMA = 'tenant_base'
TENANT_DOMAIN_MODEL = 'tenants.Domain'

EXTRA_SET_TENANT_METHOD_PATH = 'tenants.schema_guard.enforce_tenant_schema'



AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]



LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True



STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

_cors_origins = [o for o in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if o]
CORS_ALLOW_CREDENTIALS = False
if _cors_origins:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = _cors_origins
else:
    CORS_ALLOW_ALL_ORIGINS = True

from corsheaders.defaults import default_headers, default_methods
CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-tenant-id',
]
CORS_ALLOW_METHODS = list(default_methods)


EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend' if EMAIL_HOST
    else 'django.core.mail.backends.console.EmailBackend'
)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@scaleezy.com')

PASSWORD_RESET_BASE_URL = os.environ.get(
    'PASSWORD_RESET_BASE_URL', 'http://localhost:5173/app.html'
)

PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', '3600'))


SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
SUPABASE_BUCKET = os.environ.get('SUPABASE_BUCKET', 'boutique-crm')


CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')

_use_cloudinary = bool(CLOUDINARY_URL) and not _running_tests

STORAGES = {
    "default": {
        "BACKEND": ("cloudinary_storage.storage.MediaCloudinaryStorage"
                    if _use_cloudinary
                    else "django.core.files.storage.FileSystemStorage"),
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

if _use_cloudinary:
    import cloudinary

    cloudinary.config(secure=True)

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'core.permissions.RolePermission',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'password_reset': os.environ.get('PASSWORD_RESET_RATE', '5/hour'),
        'login': os.environ.get('LOGIN_RATE', '20/hour'),
        # A public write endpoint, so it is rate limited. Generous enough that a
        # component crashing in a render loop still gets its first reports
        # through, low enough that it cannot be used to fill the table.
        'client_error': os.environ.get('CLIENT_ERROR_RATE', '30/hour'),
    },
    'EXCEPTION_HANDLER': 'core.exceptions.platform_exception_handler',
}




import logging 


def _log_level(raw):
    level = (raw or '').strip().upper()
    return level if level in logging.getLevelNamesMapping() else 'WARNING'


#: The one switch that turns off capture of handled exceptions. It writes a row
#: per distinct swallowed failure, which is the point, but a capture path that
#: cannot be switched off is a capture path that has to be deployed perfectly
#: the first time. Set CAPTURE_HANDLED_ERRORS=0 to fall back to log-only.
CAPTURE_HANDLED_ERRORS = os.environ.get('CAPTURE_HANDLED_ERRORS', '1') != '0'


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'plain': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'plain',
        },
        # Files every logger.exception() in the project as an ErrorEvent of
        # kind='handled'. This is what makes a swallowed failure -- an order
        # email that did not send, a metric that could not be read -- visible in
        # the Super Admin console instead of only in the Render log stream.
        #
        # A handler rather than edits at the ~49 catch sites, so the ones written
        # after today are captured without anyone remembering to. ERROR level, so
        # a warning carrying exc_info is not filed as a product error.
        'error_events': {
            'class': 'core.exceptions.ErrorEventLogHandler',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console'] + (
            ['error_events'] if CAPTURE_HANDLED_ERRORS else []),
        'level': _log_level(os.environ.get('DJANGO_LOG_LEVEL')),
    },
    'loggers': {
        # Left on the console handler alone, and deliberately not given
        # 'error_events': this logger carries exactly the unhandled 500s that
        # got_request_exception has already filed as kind='crash'. Capturing it
        # here too would file every crash twice -- once with its traceback, once
        # without. core.exceptions._LOGGERS_ALREADY_CAPTURED enforces the same
        # rule for anything that reaches the handler by another route.
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}


TRACKING_BASE_URL = (
    os.environ.get('TRACKING_BASE_URL')
    or os.environ.get('RENDER_EXTERNAL_URL')
    or 'http://localhost:8000'
)

CUSTOMER_MESSAGE_BACKEND = os.environ.get(
    'CUSTOMER_MESSAGE_BACKEND',
    'domains.orders.messaging.whatsapp_backend',
)

WHATSAPP_COUNTRY_CODE = os.environ.get('WHATSAPP_COUNTRY_CODE', '91')


DESIGN_STUDIO_INTELLIGENCE = os.environ.get(
    'DESIGN_STUDIO_INTELLIGENCE',
    'apps.design_studio.intelligence.rules.RuleBasedIntelligence',
)

DESIGN_STUDIO_PINTEREST_TOKEN = os.environ.get('DESIGN_STUDIO_PINTEREST_TOKEN', '')
DESIGN_STUDIO_GOOGLE_API_KEY = os.environ.get('DESIGN_STUDIO_GOOGLE_API_KEY', '')

UPSTASH_REDIS_REST_URL = os.environ.get(
    'UPSTASH_REDIS_REST_URL',
    'https://charmed-mastiff-150004.upstash.io'
)
UPSTASH_REDIS_REST_TOKEN = os.environ.get(
    'UPSTASH_REDIS_REST_TOKEN',
    'gQAAAAAAAkn0AAIgcDFhMjY5MTkxMTQ5YzM0OTU2YTljZDMwNDQwNjNkYzc3Zg'
)

INTERNAL_API_SECRET = os.environ.get(
    'INTERNAL_API_SECRET',
    'scaleezy_internal_secret_key_2026'
)
WHATSAPP_SERVICE_URL = os.environ.get(
    'WHATSAPP_SERVICE_URL',
    'http://127.0.0.1:3001'
)




