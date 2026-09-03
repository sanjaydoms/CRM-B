
from django.contrib.auth.models import User
from django.db.models import Q
from django_tenants.utils import get_public_schema_name, schema_context

from .schemas import for_each_tenant, tenant_scope
from rest_framework.authtoken.models import Token

from core.roles import resolve_user_role
from crm_api.auth_views import PasswordResetRequestView, find_tenant_for_account
from tenants.models import BoutiqueTenant

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def clamped_int(value, default, low=1, high=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, number if high is None else min(number, high))


def _tenant(schema_name):
    public = get_public_schema_name()
    if not schema_name or schema_name == public:
        return None
    with schema_context(public):
        return BoutiqueTenant.objects.filter(schema_name=schema_name).first()


def _is_owner(tenant, user):
    owner = (getattr(tenant, 'owner_email', '') or '').strip().lower()
    if not owner:
        return False
    return owner in {(user.email or '').strip().lower(),
                     (user.username or '').strip().lower()}


def _rows_for(tenant, search, status):
    with tenant_scope(tenant):
        queryset = User.objects.select_related('tailor_profile', 'designer_profile')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
                | Q(first_name__icontains=search) | Q(last_name__icontains=search))
        if status in ('active', 'inactive'):
            queryset = queryset.filter(is_active=(status == 'active'))

        users = list(queryset.order_by('username'))
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
                'last_login': None,
                'boutique': tenant.schema_name,
                'boutique_name': tenant.name,
                'role': resolve_user_role(user),
                'has_token': user.id in with_token,
                'tailor_id': tailor.id if tailor else None,
                'designer_id': str(designer.id) if designer else None,
            })
        return rows


def list_users(tenants, search='', boutique=None, role=None, status=None,
               page=1, page_size=DEFAULT_PAGE_SIZE):
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
        'last_login_tracked': False,
    }


def set_user_active(schema, username, active):
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

    def __init__(self, email):
        self.data = {'email': email}


def trigger_password_reset(schema, username):
    tenant = _tenant(schema)
    if tenant is None:
        return False, 'No such boutique.'
    if not tenant.is_active:
        return False, ("That boutique is suspended -- reactivate it before "
                       "resetting a password.")

    with tenant_scope(tenant):
        user = User.objects.filter(username=username).first()
        if user is None:
            return False, 'No such user in that boutique.'
        if not user.is_active:
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
    return True, f'A reset link has been sent to {address}.'


def issue_access_link(schema, username):
    from django.conf import settings

    from crm_api.auth_views import make_reset_link, send_reset_email

    tenant = _tenant(schema)
    if tenant is None:
        return False, 'No such boutique.', None
    if not tenant.is_active:
        return False, ('That boutique is suspended -- reactivate it before '
                       'issuing a sign-in link.'), None

    with tenant_scope(tenant):
        user = User.objects.filter(username=username).first()
        if user is None:
            return False, 'No such user in that boutique.', None
        if not user.is_active:
            return False, ('That account is deactivated. Reactivate it before '
                           'issuing a sign-in link.'), None
        address = (user.email or '').strip()

    link = make_reset_link(tenant, user)

    emailed = False
    if '@' in address and getattr(settings, 'EMAIL_HOST', ''):
        emailed = send_reset_email(tenant, user, link, address)

    minutes = int(getattr(settings, 'PASSWORD_RESET_TIMEOUT', 3600)) // 60
    return True, (
        f'Sign-in link issued for {username}.'
        + (f' Emailed to {address}.' if emailed else ' Copy it and send it to them.')
    ), {
        'link': link,
        'expires_minutes': minutes,
        'emailed': emailed,
        'email_address': address if emailed else '',
        'boutique': tenant.name,
        'username': username,
    }
