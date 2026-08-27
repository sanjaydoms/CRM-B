
from django.db.models import Count, Min
from django_tenants.utils import get_public_schema_name

from core.modules import MODULES, is_enabled

from .schemas import tenant_scope

UNTRACKED = (
    ('email_verified', 'Email address verified',
     'Not tracked: nothing verifies an email address. The address is taken at '
     'signup and used to sign in, and no confirmation is ever sent or recorded.'),
    ('phone_verified', 'Phone number verified',
     'Not tracked: nothing verifies a phone number. It is stored exactly as it '
     'was typed, and there is no OTP anywhere in this product.'),
    ('whatsapp_connected', 'WhatsApp connected',
     'Not tracked, and nothing to connect: customer messages are wa.me links the '
     'owner sends from their own phone. See CUSTOMER_MESSAGE_BACKEND in '
     'settings.py -- that is a product decision, not a missing step.'),
    ('payment_configured', 'Payments configured',
     'Not tracked: there is no payment gateway. Order money is what staff record '
     'by hand against the order.'),
    ('integrations_configured', 'Integrations configured',
     'Not tracked: this product integrates with nothing, so there is nothing a '
     'boutique could have configured.'),
    ('real_designs', 'Own designs in the library',
     'Not tracked: nothing in the table separates a design the boutique added '
     'from one the signup seeder wrote. Both arrive as source=catalogue with an '
     'empty external_id and no created_by -- crm_api.serializers.'
     'BoutiqueDesignSerializer.create() stamps source=catalogue on every design '
     'saved from Manage Designs, and neither it nor BoutiqueDesignViewSet sets '
     'created_by, which is exactly what crm_api.utils.seed_tenant_defaults also '
     'leaves. The only difference is the title, and the seeder\'s eleven titles '
     'are a literal inside that function. Counting "source is not '
     'catalogue/suggestion" scored the boutique\'s own Manage Designs work as '
     'seed data and never completed.'),
    ('design_approval_configured', 'Design approval decision made',
     'Not tracked: BoutiqueSettings.design_approval_required is a two-state '
     'BooleanField defaulting to False, so "the boutique chose not to review '
     'uploads" and "nobody has decided" are the same stored value. Scoring it '
     'held every correctly configured boutique that leaves the approval queue '
     'off below 100% permanently.'),
)

ALMOST_COMPLETE_PERCENT = 80


def _profile_default(field_name):
    from crm_api.models import BoutiqueSettings

    return BoutiqueSettings._meta.get_field(field_name).default


def _step(key, label, done, detail, module=None):
    return {'key': key, 'label': label, 'done': bool(done), 'detail': detail,
            'tracked': True, 'state': 'done' if done else 'todo',
            'module': module}


def _module_off(step):
    label, prefixes, _description = MODULES[step['module']]
    return {**step, 'done': None, 'tracked': False, 'state': 'module_off',
            'detail': (f'Not counted: the {label} module is switched off for this '
                       f'boutique, so TenantHeaderMiddleware refuses '
                       f'{" and ".join(prefixes)} and there is no way for its '
                       f'staff to complete this step. Last reading: {step["detail"]}')}


def _tracked_steps(tenant):
    from django.contrib.auth.models import User

    from apps.design_studio.models import Collection, DesignBoard, Designer
    from apps.inventory.models import InventoryItem, PurchaseOrder, Supplier
    from crm_api.models import (BoutiqueSettings, Customer, CustomerMessage,
                                Order, Tailor)

    profile = BoutiqueSettings.objects.order_by('id').first()
    no_profile = 'No boutique profile row exists in this schema at all.'

    staff = User.objects.exclude(email__iexact=tenant.owner_email).count()
    specialists = Tailor.objects.exclude(role__in=('Master', 'Tailor')).count()
    designers = Designer.objects.count()
    collections = Collection.objects.count()
    boards = DesignBoard.objects.count()
    items = InventoryItem.objects.count()
    suppliers = Supplier.objects.count()
    purchase_orders = PurchaseOrder.objects.count()
    customers = Customer.objects.aggregate(n=Count('id'), first=Min('created_at'))
    orders = Order.objects.aggregate(n=Count('id'), first=Min('order_date'))
    sent_messages = CustomerMessage.objects.filter(status='SENT').count()

    return [
        _step('logo_uploaded', 'Logo uploaded',
              profile is not None and bool(profile.logo),
              'Logo uploaded.' if profile is not None and profile.logo else
              (no_profile if profile is None else
               'No logo. This is the only field on the boutique profile with no '
               'default, so it is the one field that is always the boutique\'s '
               'own work.')),

        _step('address_set', 'Address entered',
              profile is not None and profile.address != _profile_default('address'),
              'Address entered.' if profile is not None
              and profile.address != _profile_default('address') else
              (no_profile if profile is None else
               f'Still the shipped default ({_profile_default("address")!r}). '
               'Signup only writes an address when the owner typed one.')),

        _step('phone_set', 'Phone number entered',
              profile is not None and profile.phone != _profile_default('phone'),
              'Phone number entered.' if profile is not None
              and profile.phone != _profile_default('phone') else
              (no_profile if profile is None else
               f'Still the shipped default ({_profile_default("phone")!r}). '
               'Signup only writes a number when the owner gave one.')),

        _step('staff_added', 'Staff invited', staff > 0,
              f'{staff} account(s) besides the owner.' if staff else
              'Only the owner has an account. Counted as accounts, not as Tailor '
              'rows: signup seeds four tailors, so counting the team list would '
              'report every boutique as fully staffed on day one.',
              module='tailors'),

        _step('specialist_roles', 'Specialist production roles in use',
              specialists > 0,
              f'{specialists} tailor(s) in a specialist role.' if specialists else
              'Everyone is still Master or Tailor -- the two roles the signup '
              'seeder creates. Cutting, Maggam, QC and the rest are untouched.',
              module='tailors'),

        _step('first_customer', 'First customer added', customers['n'] > 0,
              f'{customers["n"]} customer(s), first on '
              f'{customers["first"]:%Y-%m-%d}.' if customers['n'] else
              'No customers. Nothing seeds this table, so this is the cleanest '
              'signal on the page: zero means the boutique has not started.'),

        _step('first_order', 'First order taken', orders['n'] > 0,
              f'{orders["n"]} order(s), first on {orders["first"]:%Y-%m-%d}.'
              if orders['n'] else
              'No orders. The boutique is set up but has not booked any work.'),

        _step('communication', 'A customer message actually sent',
              sent_messages > 0,
              f'{sent_messages} message(s) marked SENT.' if sent_messages else
              'No message has been marked SENT. Rows here queue themselves on '
              'order events, so their mere existence proves nothing -- only the '
              'SENT status means somebody actually sent one.'),

        _step('designers', 'Designers set up', designers > 0,
              f'{designers} designer(s).' if designers else
              'No designers. Nothing seeds this table.',
              module='design_studio'),

        _step('collections', 'Collections created', collections > 0,
              f'{collections} collection(s).' if collections else
              'No collections. Nothing seeds this table.',
              module='design_studio'),

        _step('boards', 'Design boards used', boards > 0,
              f'{boards} board(s).' if boards else
              'No design boards -- the shortlist an owner builds with a customer '
              'during order creation. Nothing seeds this table.',
              module='design_studio'),

        _step('real_inventory', 'Real stock tracked',
              items or suppliers or purchase_orders,
              f'{items} item(s), {suppliers} supplier(s), '
              f'{purchase_orders} purchase order(s).'
              if (items or suppliers or purchase_orders) else
              'No stock items, suppliers or purchase orders. Deliberately not '
              'counting CatalogItem, StockLocation or GarmentTemplate: all three '
              'are seeded by migrations and every boutique has hundreds.',
              module='inventory'),
    ]


def _unreadable(detail):
    return {
        'readable': False,
        'percent': None,
        'status': 'unreadable',
        'blocked_on': None,
        'tracked_steps': 0,
        'completed_steps': 0,
        'percent_basis': 'Not computed.',
        'steps': [],
        'detail': detail,
    }


def _status(tenant, percent):
    if not tenant.is_active:
        return 'blocked'
    if percent >= 100:
        return 'completed'
    if percent >= ALMOST_COMPLETE_PERCENT:
        return 'almost_complete'
    if percent == 0:
        return 'not_started'
    return 'in_progress'


def progress(tenant):
    if tenant.schema_name == get_public_schema_name():
        return _unreadable('The public schema is the registry the console runs '
                           'in, not a boutique.')

    try:
        with tenant_scope(tenant):
            declared = _tracked_steps(tenant)
    except Exception as exc:
        return _unreadable(f"This boutique's schema could not be read: {exc}")

    tracked, gated = [], []
    for step in declared:
        if step['module'] and not is_enabled(tenant.enabled_modules, step['module']):
            gated.append(_module_off(step))
        else:
            tracked.append(step)

    completed = sum(1 for step in tracked if step['done'])
    percent = round(100 * completed / len(tracked)) if tracked else 0
    blocked_on = next((step for step in tracked if not step['done']), None)

    return {
        'readable': True,
        'percent': percent,
        'status': _status(tenant, percent),
        'blocked_on': blocked_on,
        'tracked_steps': len(tracked),
        'completed_steps': completed,
        'percent_basis': (
            f'{completed} of {len(tracked)} tracked steps. {len(gated)} step(s) '
            f'belong to a module switched off for this boutique and '
            f'{len(UNTRACKED)} have no signal in this product; both sets are '
            f'excluded from this percentage rather than counted as incomplete.'),
        'steps': tracked + gated + [
            {'key': key, 'label': label, 'done': None, 'detail': detail,
             'tracked': False, 'state': 'untracked', 'module': None}
            for key, label, detail in UNTRACKED
        ],
        'detail': '',
    }


def steps(tenant):
    return progress(tenant)['steps']
