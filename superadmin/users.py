"""Every account on the platform, read and acted on from outside every boutique.

There is no cross-schema query in Postgres and no join between two schemas, so
"list the platform's users" is not a queryset -- it is one queryset per boutique,
merged here. That is the whole shape of this module, and it is why `boutique` is
applied to the *tenant list* before any schema is entered: asking about one
boutique costs one schema switch, and asking the same question after the sweep
would cost fifty.

Two things about this that are easy to get wrong, and were:

**tenant_context, not schema_context.** `schema_context(name)` binds a
`FakeTenant` to the connection -- a schema name and nothing else. `core.roles.
resolve_user_role` identifies the boutique owner *positively*, by comparing the
account's address against `connection.tenant.owner_email`, so under
schema_context that check silently reads '' and never fires. The owner then
falls through to the "nothing claimed this account" default, which happens to
answer Owner too -- until the owner also works the floor and has a Tailor
profile, at which point the console labels the boutique's owner "Cutting Master"
while login and /auth/me call the same person Owner. `tenant_context(tenant)`
binds the real registry row, so role resolution here is the same function
answering the same way it does in the boutique's own API. Nothing is
reimplemented; the right object is bound.

**last_login is always NULL.** `django.contrib.auth.login()` is never called
anywhere in this product -- the API issues DRF tokens and nothing writes that
column. It is returned as None with `last_login_tracked: False` beside it in the
envelope, because a console that renders NULL as "never signed in" is stating a
falsehood about every account on the platform.
"""

from django.contrib.auth.models import User
from django.db.models import Q
from django_tenants.utils import get_public_schema_name, schema_context

# MissingSchema is deliberately NOT caught in this module. A read sweep hands
# that to for_each_tenant, which names the boutique as unreadable; a mutation
# (set_user_active and below) lets it propagate, because the alternative -- the
# write landing in `public` on the console administrator's own account -- is the
# defect superadmin/schemas.py exists to stop.
from .schemas import for_each_tenant, tenant_scope
from rest_framework.authtoken.models import Token

from core.roles import resolve_user_role
from crm_api.auth_views import PasswordResetRequestView, find_tenant_for_account
from tenants.models import BoutiqueTenant

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def clamped_int(value, default, low=1, high=None):
    """A query-parameter number, clamped, with junk falling back to `default`.

    Every caller of this is wired straight from request.query_params, which
    hands over *strings* -- so a bare int() turned `?page=abc` into a
    ValueError, an HTTP 500, and (since core.exceptions started recording them)
    an ErrorEvent row on the console's own error screen, for what is nothing but
    a mistyped URL. A malformed number is not an outage; it is the default.

    Here rather than in each caller because search.py had the same cast on
    limit_per_type and would have grown the same bug independently.

    `high` is optional because a page NUMBER has no ceiling worth inventing: an
    out-of-range page is an empty slice of a list already in memory, so it costs
    nothing. A page SIZE does have one, and it is the caller's to state.

    ponytail: superadmin/datasets.py:185 and superadmin/audit.py:123 hold the
    same bare-int() cast. Both are outside this change's file list; datasets is
    at least caught by an `except ValueError` in its view. Point them here when
    either file is next opened.
    """
    try:
        # int(float) is deliberately NOT used: '1e9' and '3.7' are not page
        # numbers anyone typed on purpose, and silently accepting them makes
        # page 3.7 and page 4 the same page under a different URL.
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, number if high is None else min(number, high))


def _tenant(schema_name):
    """The registry row for a schema, or None.

    Read with the public schema named rather than assumed: the console is pinned
    there by the middleware, but these are module functions and the connection
    carries whatever the last caller left on it (CONN_MAX_AGE keeps it alive
    across requests). `public` itself is excluded -- it is the registry the
    console runs in, not a boutique, and it has no owner to protect.
    """
    public = get_public_schema_name()
    if not schema_name or schema_name == public:
        return None
    with schema_context(public):
        return BoutiqueTenant.objects.filter(schema_name=schema_name).first()


def _is_owner(tenant, user):
    """Whether this account is the boutique's owner.

    Both columns are compared because the two are not reliably the same row:
    signup sets `username` and `email` to the address, but staff accounts
    created later (TailorViewSet._ensure_user_account, DesignerViewSet.
    create_login) have carried one or the other at different times. Matching on
    `email` alone would leave an owner whose User row has a blank email
    unprotected by the guard in set_user_active below.
    """
    owner = (getattr(tenant, 'owner_email', '') or '').strip().lower()
    if not owner:
        return False
    return owner in {(user.email or '').strip().lower(),
                     (user.username or '').strip().lower()}


def _rows_for(tenant, search, status):
    """Every matching account in one boutique, as plain dicts.

    Filtering happens in Postgres. Role does not and cannot: it is spread across
    `auth_user`, `crm_api_tailor`, `design_studio_designer` and the registry's
    `owner_email`, so it is resolved per row and filtered by the caller. That is
    affordable only because this table holds a boutique's *staff* -- tens of
    rows, not its customers.
    """
    with tenant_scope(tenant):
        # Both profiles joined in the one query: resolve_user_role asks each
        # user for both, and without this that is two queries per row.
        queryset = User.objects.select_related('tailor_profile', 'designer_profile')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
                | Q(first_name__icontains=search) | Q(last_name__icontains=search))
        if status in ('active', 'inactive'):
            queryset = queryset.filter(is_active=(status == 'active'))

        users = list(queryset.order_by('username'))
        # Whether a token exists, never which token it is. Rendering the key
        # would turn read access to this console into the ability to act as any
        # user in any boutique -- the same rule superadmin/datasets.py enforces
        # by excluding the model outright.
        with_token = set(Token.objects.filter(user__in=users)
                         .values_list('user_id', flat=True))

        rows = []
        for user in users:
            tailor = getattr(user, 'tailor_profile', None)
            designer = getattr(user, 'designer_profile', None)
            rows.append({
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_active': user.is_active,
                'date_joined': user.date_joined.isoformat() if user.date_joined else None,
                # Never populated -- see the module docstring.
                'last_login': None,
                'boutique': tenant.schema_name,
                'boutique_name': tenant.name,
                'role': resolve_user_role(user),
                'has_token': user.id in with_token,
                'tailor_id': tailor.id if tailor else None,
                # Designer.id is a UUID; stringified so the payload is JSON.
                'designer_id': str(designer.id) if designer else None,
            })
        return rows


def list_users(tenants, search='', boutique=None, role=None, status=None,
               page=1, page_size=DEFAULT_PAGE_SIZE):
    """A page of platform users, merged across boutiques.

    `tenants` is the caller's tenant list (superadmin.views._boutiques()), so
    this module never decides which boutiques exist. `boutique` narrows that
    list before any schema is entered.

    Sorted by (boutique schema, username) -- a total order over the merged set,
    which is what makes page 2 stable. Sorting on anything the two schemas can
    tie on (date_joined, say) would silently repeat and skip rows between pages,
    the same trap superadmin/datasets.py avoids by paginating on -pk.

    A boutique whose schema is missing or half-migrated is skipped and named in
    `unreadable` rather than raising: that is precisely the state an
    administrator opens this screen to find, and one broken boutique must not
    take the list of all the others with it.

    ponytail: O(number of boutiques) schema switches per page, the same ceiling
    as superadmin/metrics.py and crm_api.auth_views.find_tenant_for_account.
    Fine at tens. The upgrade is one public-schema index table -- lowercased
    email/username -> schema name -- written wherever a User is created
    (SignupView, TailorViewSet._ensure_user_account, DesignerViewSet.
    create_login); every one of those call sites is already known, because the
    login path needs the same table.
    """
    page_size = clamped_int(page_size, DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
    page = clamped_int(page, 1)
    search = (search or '').strip()
    role = (role or '').strip().lower()
    status = (status or '').strip().lower()

    public = get_public_schema_name()
    chosen = [t for t in tenants if t.schema_name != public]
    if boutique:
        chosen = [t for t in chosen if t.schema_name == boutique]
    chosen.sort(key=lambda t: t.schema_name)

    # Each boutique is read inside its own savepoint (schemas.for_each_tenant),
    # for two reasons that a bare try/except around the loop got wrong.
    #
    # A boutique with a registry row but no schema is not an error at all
    # without the guard: Postgres skips a missing entry in search_path and
    # resolves the query against `public`, where auth_user really does exist
    # because auth is a SHARED_APP. The loop would then report the platform
    # console's own superusers as that boutique's staff, and nothing would
    # raise for the except to catch.
    #
    # And a query that *does* fail inside an enclosing atomic() aborts the
    # transaction, so swallowing it left every later statement in the request
    # failing with "current transaction is aborted" -- one unreadable boutique
    # taking down the whole page, which is precisely what the except was
    # written to prevent.
    per_tenant, unreadable = for_each_tenant(
        chosen, lambda tenant: _rows_for(tenant, search, status))
    found = [row for rows in per_tenant for row in rows]

    if role:
        found = [row for row in found if (row['role'] or '').lower() == role]

    found.sort(key=lambda row: (row['boutique'], row['username']))
    total = len(found)
    start = (page - 1) * page_size
    return {
        'users': found[start:start + page_size],
        'count': total,
        'page': page,
        'page_size': page_size,
        'pages': max(1, -(-total // page_size)),
        'unreadable': unreadable,
        # For the column header. Not a per-row field: it is a fact about the
        # product, not about the account.
        'last_login_tracked': False,
    }


def set_user_active(schema, username, active):
    """Turn one account on or off. Returns (ok, message).

    Deactivating the boutique OWNER is refused. The owner is the only account
    that can create staff, grant logins and reach the boutique's own settings,
    so an owner switched off here has no route back in through the product:
    every screen that could undo it is now refused to them, and password reset
    does not help because PasswordResetRequestView skips inactive users. The
    console's own answer to "this boutique must stop" is suspension, which is
    reversible from the same screen that applied it.

    No token is deleted on deactivation. DRF's TokenAuthentication refuses an
    inactive user outright, so the existing token stops working at the next
    request without this having to hunt it down.
    """
    tenant = _tenant(schema)
    if tenant is None:
        return False, 'No such boutique.'

    with tenant_scope(tenant):
        user = User.objects.filter(username=username).first()
        if user is None:
            return False, 'No such user in that boutique.'
        if not active and _is_owner(tenant, user):
            return False, ("That account is the boutique owner and cannot be "
                           "deactivated -- they would have no way back in. "
                           "Suspend the boutique instead.")
        if user.is_active == active:
            return True, f"{username} is already {'active' if active else 'deactivated'}."

        user.is_active = active
        user.save(update_fields=['is_active'])

    return True, f"{username} {'activated' if active else 'deactivated'}."


def revoke_sessions(schema, username):
    """Sign one account out of every device. Returns (ok, message).

    Deleting the authtoken row is the only real sign-out this product has: DRF
    tokens never expire and there is no session to flush, so a leaked key is
    valid forever until the row is gone. The user can sign in again immediately
    and get a fresh key -- this ends the *current* sessions, it does not lock
    the account. set_user_active is what locks the account.

    An account with no token already satisfies the request, so that is ok=True
    with a message saying so rather than an error the administrator has to
    interpret.
    """
    tenant = _tenant(schema)
    if tenant is None:
        return False, 'No such boutique.'

    with tenant_scope(tenant):
        user = User.objects.filter(username=username).first()
        if user is None:
            return False, 'No such user in that boutique.'
        deleted, _ = Token.objects.filter(user=user).delete()

    if not deleted:
        return True, f'{username} had no active session.'
    return True, f'{username} has been signed out of every device.'


class _ResetRequest:
    """The only attribute PasswordResetRequestView.post reads off a request.

    A shim rather than a real request because the view is reused whole: its
    token generation, its schema-carrying payload and its email copy are the
    ones the product already sends, and a second copy of any of them here would
    drift from the boutique's own reset flow -- the exact failure
    find_tenant_for_account was extracted to prevent.

    Going through the view object rather than its .dispatch() also skips
    _PasswordResetThrottle, which is right: that throttle exists to rate-limit
    strangers on an anonymous endpoint, and this caller is an authenticated
    platform administrator behind IsPlatformAdmin.
    """

    def __init__(self, email):
        self.data = {'email': email}


def trigger_password_reset(schema, username):
    """Send the boutique's own reset email to one account. Returns (ok, message).

    The account is checked here first for two reasons. The view answers
    identically whether or not an address exists -- deliberately, so it cannot
    be used as a directory of every account on the platform -- which is exactly
    the wrong answer for an administrator who needs to know whether anything
    happened. And the view resolves the boutique *from the address alone*, while
    the console is asking about (schema, username): staff emails are unique
    inside a schema and nothing makes them unique across schemas, so an address
    present in two boutiques would reset the account in whichever one
    find_tenant_for_account reaches first. That case is refused rather than
    guessed, because mailing the wrong boutique's staff member a working reset
    link for someone else's account is the one outcome worth failing loudly on.

    RECOMMENDED EXTRACTION (not made here -- crm_api/auth_views.py belongs to
    another change): lift the body of PasswordResetRequestView.post below the
    tenant lookup into `send_password_reset(tenant, user) -> None`, and have
    both the view and this function call it. That removes the shim and the
    ambiguity check in one move, because the caller then states the tenant
    instead of having it inferred from an address.
    """
    tenant = _tenant(schema)
    if tenant is None:
        return False, 'No such boutique.'
    if not tenant.is_active:
        # PasswordResetConfirmView refuses a suspended boutique, so the link
        # would be dead on arrival.
        return False, ("That boutique is suspended -- reactivate it before "
                       "resetting a password.")

    with tenant_scope(tenant):
        user = User.objects.filter(username=username).first()
        if user is None:
            return False, 'No such user in that boutique.'
        if not user.is_active:
            # The view drops inactive users silently; say so instead.
            return False, ('That account is deactivated. Reactivate it before '
                           'sending a reset link.')
        address = (user.email or user.username or '').strip().lower()

    if '@' not in address:
        return False, ('That account has no email address on file, so there is '
                       'nowhere to send a reset link.')

    resolved = find_tenant_for_account(address)
    if resolved is None or resolved.schema_name != tenant.schema_name:
        return False, (f'{address} does not resolve to this boutique -- the '
                       f'same address exists in another one. Reset it from '
                       f'that boutique, or change one of the two addresses.')

    response = PasswordResetRequestView().post(_ResetRequest(address))
    if response.status_code != 200:
        return False, 'That reset could not be started.'
    # The view logs a mail failure rather than raising it, so this reports what
    # is actually known: a link was generated and sending was attempted.
    return True, f'A reset link has been sent to {address}.'
