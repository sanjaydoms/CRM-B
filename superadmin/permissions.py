
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
