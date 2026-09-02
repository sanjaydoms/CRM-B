
from django.conf import settings
from django.core import signing
from django.db import connection

SALT = 'crm.order-tracking'


def build_token(order):
    return signing.dumps(
        {'s': connection.schema_name, 'o': order.order_id}, salt=SALT
    )


def read_token(token):

    try:
        payload = signing.loads(token, salt=SALT)
        return payload['s'], payload['o']
    except (signing.BadSignature, KeyError, TypeError):
        return None, None


def tracking_url(order):

    base = getattr(settings, 'TRACKING_BASE_URL', '') or ''
    return f"{base.rstrip('/')}/track/{build_token(order)}/"
