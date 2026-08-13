"""Who is allowed into the platform console.

The whole app answers to one rule, and it is deliberately two conditions rather
than the obvious one.

`is_superuser` alone is not enough. `django.contrib.auth` is in SHARED_APPS *and*
TENANT_APPS, so a `User` table exists in the public schema and in every boutique's
schema, and `is_superuser` is just a column in whichever one the connection is
pointed at. Nothing stops a boutique from ending up with a superuser row of its
own -- seed_data.py creates one, and any `createsuperuser` run inside a tenant
context would too. Checking only the flag would let that account read every other
boutique on the platform.

So the schema is checked as well: the caller must be a superuser *and* the
connection must be on the public schema, which is where the platform's own
administrators live and where SuperadminPinsPublicSchema (tenants/middleware.py)
guarantees these requests run. The two together mean "a superuser in the registry
schema", which is the only thing a platform administrator can be.
"""

from django.db import connection
from django_tenants.utils import get_public_schema_name
from rest_framework import permissions


class IsPlatformAdmin(permissions.BasePermission):
    message = "Platform administrator access only."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_superuser
            and user.is_active
            and connection.schema_name == get_public_schema_name()
        )
