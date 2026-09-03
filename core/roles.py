
OWNER = 'Owner'
DESIGNER = 'Designer'


def resolve_user_role(user):
    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    if user.is_superuser:
        return OWNER
    try:
        from django.db import connection
        tenant_owner = getattr(connection.tenant, 'owner_email', '') or ''
        if tenant_owner and (user.email or '').lower() == tenant_owner.lower():
            return OWNER
    except Exception:
        pass

    profile = getattr(user, 'tailor_profile', None)
    if profile:
        return profile.role
    designer_profile = getattr(user, 'designer_profile', None)
    if designer_profile:
        return DESIGNER

    return OWNER
