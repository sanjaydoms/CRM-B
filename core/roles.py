"""The single definition of a signed-in user's role.

This lived in three places that disagreed: login and /auth/me reported a user
with no tailor profile as the boutique Owner, while the workflow engine called
the same user 'Staff' and refused every stage transition. Owners were locked
out of their own production workflow as a result.

Staff accounts always have a Tailor profile attached (see
TailorViewSet._ensure_user_account), so "signed in, no profile" used to mean
the boutique owner created at sign-up -- and only that, because a Tailor
profile was the only kind of profile a non-owner account could have.

That stopped being true once designers got their own accounts (see
DesignerViewSet.create_login). A designer with no Tailor profile is not the
boutique owner; they are a designer. Treating them as OWNER would hand a
design-only account full access to customers, orders and financials -- exactly
what the module's permission matrix promises never happens. So the fallback is
no longer "no Tailor profile -> OWNER".

Phase 8 finished that thought. Owner is now decided POSITIVELY and only
positively -- by BoutiqueTenant.owner_email, the address signup puts on the
tenant and on the owner's own User -- and an account that no profile claims and
that is not the owner resolves to None, which every permission class denies.
Ownership is never inferred from an absence, because the absences are reachable:
deleting a staff row created one, and so did repointing an account's email.
"""

OWNER = 'Owner'
DESIGNER = 'Designer'


def resolve_user_role(user):
    """Return the caller's role, or None for an anonymous caller.

    A Tailor profile wins first, and reports whatever it carries -- 'Master'
    and 'Tailor' for a generalist boutique, or one of the specialists
    (Measurement Master, Pattern Master, Cutting Master, Maggam Master,
    Finishing Master, Pressing Staff, QC Master) where the studio has split the
    work. See Tailor.ROLE_CHOICES.

    A Designer profile is checked next and reports DESIGNER. Designer is
    deliberately not a Tailor role -- see apps/design_studio/models.py:Designer
    -- so it needs its own check here rather than falling out of the Tailor
    lookup above.

    Only when neither claims the user do they fall through to OWNER. That is
    now a real "nothing else matched" default rather than a guess, because
    every kind of staff profile has been asked first.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    # The owner is identified POSITIVELY, and first. Owner used to be what was
    # left when no staff profile claimed the user -- an identity defined by
    # absence -- and that cut both ways with equal force:
    #
    #   * Attach a profile to the owner and they stop being the owner. Granting
    #     a designer login on the boutique's own address links that very
    #     account, so one click on the roster ended the owner's ownership. There
    #     is no in-product way back: every screen that could undo it is now
    #     refused to them.
    #   * Remove a profile and the account BECOMES the owner. Deleting a
    #     designer leaves their User with no profile at all, so that login --
    #     password unchanged, token still live -- is promoted to boutique owner.
    #
    # The real owner is a plain create_user (crm_api/auth_views.py), not a
    # superuser, so the is_superuser check below never protected them.
    if user.is_superuser:
        return OWNER
    try:
        from django.db import connection
        tenant_owner = getattr(connection.tenant, 'owner_email', '') or ''
        if tenant_owner and (user.email or '').lower() == tenant_owner.lower():
            return OWNER
    except Exception:
        # No tenant bound (management commands, the public schema). Fall
        # through rather than crash role resolution.
        pass

    profile = getattr(user, 'tailor_profile', None)
    if profile:
        return profile.role
    designer_profile = getattr(user, 'designer_profile', None)
    if designer_profile:
        return DESIGNER

    # Nothing claims this account, so it gets NOTHING.
    #
    # This answered OWNER until Phase 8, which made deleting a staff member an
    # act of promotion: Tailor.user is SET_NULL, so removing somebody from the
    # roster left their User with no profile of any kind, and their existing
    # token -- password unchanged, never revoked -- resolved to boutique owner
    # on the next request. Payroll, deposits, advances and payouts all opened.
    # Firing someone was the exploit.
    #
    # A MISSING PROFILE IS NOT PROOF OF OWNERSHIP. Owner is established
    # positively above, from BoutiqueTenant.owner_email -- the address signup
    # writes onto both the tenant and the owner's User, unique across the
    # platform, and the same field LoginView already trusts to find a boutique.
    # An account that matches nothing is unknown, and every permission class in
    # core.permissions denies on None. Denial is the safe answer; ownership is
    # not something to infer from an absence.
    #
    # The reason this was deferred through Phases 1-7 was recorded here as
    # "TenantTestCase builds ONE tenant for the whole run". That is not true of
    # this version: setUpClass constructs a fresh tenant and calls the class's
    # own setup_tenant before saving, and tearDownClass drops it. Each class
    # gets its own owner_email, so the positive check above fires for each.
    return None
