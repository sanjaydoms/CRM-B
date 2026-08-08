"""Customer-facing tracking links.

The link has to survive being opened by someone with no account, no session and
no ``X-Tenant-ID`` header, which is the only reason this needs any thought: the
order lives inside a tenant schema, so the URL itself has to say which schema to
look in, and it has to say so in a way a stranger cannot forge or edit.

``django.core.signing`` already does exactly that -- it packs the payload and
signs it with SECRET_KEY -- so there is no token column, no unique-index
backfill for existing orders, and no public-schema lookup table to keep in sync
with the tenant ones. Every order that already exists is linkable the moment
this ships.

# ponytail: links are stateless, so revoking one means rotating SECRET_KEY
# (which invalidates all of them). Add a per-order nonce column and mix it into
# the salt if a boutique ever needs to kill a single link.
"""

from django.conf import settings
from django.core import signing
from django.db import connection

# Namespaces these signatures so a value signed elsewhere in the project can
# never be replayed as a tracking token, and vice versa.
SALT = 'crm.order-tracking'


def build_token(order):
    """Return the token identifying this order to a customer.

    The tenant schema travels inside the signed payload rather than as a
    separate URL segment, so a token issued by one boutique cannot be edited
    into a lookup against another's data.

    Signed, not encrypted: the payload is base64 of readable JSON, so treat the
    schema name and order id as public. What the signature buys is that neither
    can be *changed*.
    """
    return signing.dumps(
        {'s': connection.schema_name, 'o': order.order_id}, salt=SALT
    )


def read_token(token):
    """Return ``(schema_name, order_id)``, or ``(None, None)`` if not genuine."""
    try:
        payload = signing.loads(token, salt=SALT)
        return payload['s'], payload['o']
    except (signing.BadSignature, KeyError, TypeError):
        return None, None


def tracking_url(order):
    """Absolute URL to give the customer."""
    base = getattr(settings, 'TRACKING_BASE_URL', '') or ''
    return f"{base.rstrip('/')}/track/{build_token(order)}/"
