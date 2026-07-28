"""The single definition of a signed-in user's role.

This lived in three places that disagreed: login and /auth/me reported a user
with no tailor profile as the boutique Owner, while the workflow engine called
the same user 'Staff' and refused every stage transition. Owners were locked
out of their own production workflow as a result.

Staff accounts always have a Tailor profile attached (see
TailorViewSet._ensure_user_account), so "signed in, no profile" means the
boutique owner created at sign-up.
"""

OWNER = 'Owner'


def resolve_user_role(user):
    """Return 'Owner', 'Master', 'Tailor', or None for an anonymous caller."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    if user.is_superuser:
        return OWNER
    profile = getattr(user, 'tailor_profile', None)
    return profile.role if profile else OWNER
