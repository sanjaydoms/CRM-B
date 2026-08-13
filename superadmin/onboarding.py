"""How far into setting itself up a boutique actually is.

The trap this screen exists to avoid is that a boutique is never empty. Signing
up hands it four tailors, five fabrics and eleven catalogue designs
(crm_api.utils.seed_tenant_defaults), and migrating its schema adds eight stock
locations, fifteen garment templates and some seven hundred catalogue items
(apps/inventory/migrations/0003, 0005 and apps/catalog/migrations/0002).
`Tailor.objects.count() == 4` an hour after signup. So does
`DesignAsset.objects.count() == 11`. Read any of those as progress and every
boutique on the platform is a wall of green on its first day, while nobody has
entered a single customer -- which is the one thing this page exists to notice.

Every signal below is therefore something no seeder can write. Where the obvious
table is a seeded one, the count is narrowed to the rows a seeder could not have
produced: accounts that are not the owner's, tailors in a specialist role rather
than the Master/Tailor pair. `logo` is the load-bearing one for the boutique profile --
it is the only field on BoutiqueSettings with no default, so it is the only field
whose presence is certainly the boutique's own doing. address and phone have
class defaults that signup leaves in place unless the owner typed something, so
they are compared against those defaults rather than against emptiness.

The other half of the job is the steps this boutique cannot be scored on, and
there are two kinds. Both come back `tracked: False` with `done: None` and are
excluded from the percentage, because reporting either as unfinished would put a
red cross against a boutique that did nothing wrong, and someone would go and
ring it up.

**No signal in the product.** Email verification, WhatsApp, payments and
integrations do not exist anywhere here, so no boutique can have completed them
and their absence says nothing about any boutique. Two more joined them after
their signals turned out to be wrong rather than missing -- see UNTRACKED.

**Switched off for this boutique.** An administrator who turns off a module
makes TenantHeaderMiddleware refuse every URL that module owns, so the boutique
physically cannot add a design, a designer or a stock item -- and scoring it on
those steps reports work it was forbidden to do as work it failed to do, and
drags its percentage down for as long as the switch is off. Each step therefore
names the module key it depends on (`module`), and a step whose module is off
reports `state: 'module_off'` and leaves the percentage alone. Steps on an
ALWAYS_ON prefix (the boutique profile) or on a STRUCTURAL one (customers,
orders, messaging) name no module: nothing can switch those off.

Readability follows superadmin/metrics.py exactly: a schema that is missing or
half-migrated reports `unreadable`, never 0%. "This boutique has done nothing"
and "we could not look" are opposite findings and must not share a rendering.
"""

from django.db.models import Count, Min
from django_tenants.utils import get_public_schema_name

from core.modules import MODULES, is_enabled

from .schemas import tenant_scope

#: Steps the specification asks for that this product has no way to answer.
#: (key, label, why there is no signal). Kept as data rather than as five
#: branches because the honest answer for all five is the same shape: nothing
#: exists to check, so nothing is checked.
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
    # The two below were scored steps until the signals behind them were read
    # properly. Both were reporting real work as undone, which is worse than
    # reporting nothing: a step that can never complete holds a finished
    # boutique below 100% for ever and sends somebody to chase it.
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

#: Percentage at which a boutique is treated as nearly there rather than midway.
#: One threshold, named, because the console and the tests must agree on it.
ALMOST_COMPLETE_PERCENT = 80


def _profile_default(field_name):
    """The class default for a BoutiqueSettings field.

    Read off the field rather than repeated here as a literal. These strings
    ("123 Atelier Way, Fashion District", "+91 9999999999") are what every
    boutique's invoice showed before signup started writing real ones, and a
    copy of them in this file would go stale the moment the model changed --
    silently, by reporting every boutique as having set an address.
    """
    from crm_api.models import BoutiqueSettings

    return BoutiqueSettings._meta.get_field(field_name).default


def _step(key, label, done, detail, module=None):
    """One scored step. `module` is the core.modules key its screens live behind.

    None means the step cannot be switched off: either the URL is in ALWAYS_ON
    (the boutique profile) or it is STRUCTURAL (customers, orders and the
    messaging queue all hang off /api/orders/ and /api/customers/, which
    core.modules refuses to gate). `state` is what the console renders on; it is
    the only field that tells `done` apart from `module_off` apart from
    `untracked` without the caller reconstructing the rule.
    """
    return {'key': key, 'label': label, 'done': bool(done), 'detail': detail,
            'tracked': True, 'state': 'done' if done else 'todo',
            'module': module}


def _module_off(step):
    """A step whose module an administrator has switched off.

    done is None, exactly as for an untracked step: with the module off,
    TenantHeaderMiddleware answers the URLs this step measures with a 403, so
    the boutique could not have completed it however hard it tried. The old
    reading is kept on the end of the sentence rather than thrown away -- a
    boutique that added five designers before the switch was thrown still did
    that, and the console should not pretend the rows are gone.
    """
    label, prefixes, _description = MODULES[step['module']]
    return {**step, 'done': None, 'tracked': False, 'state': 'module_off',
            'detail': (f'Not counted: the {label} module is switched off for this '
                       f'boutique, so TenantHeaderMiddleware refuses '
                       f'{" and ".join(prefixes)} and there is no way for its '
                       f'staff to complete this step. Last reading: {step["detail"]}')}


def _tracked_steps(tenant):
    """The steps with a real signal behind them. Runs inside the tenant schema.

    One pass, ~13 aggregates. Every import is local because these models live in
    TENANT_APPS: importing them at module scope would be harmless, but reading
    them outside the tenant scope would silently query whichever schema the
    connection happened to be on -- which for the console is always public.

    Every step is measured whether or not its module is on. Skipping the queries
    for a disabled module would save four counts and cost the console the "last
    reading" line in _module_off, which is what tells an administrator whether
    the boutique had done the work before the switch was thrown.
    """
    from django.contrib.auth.models import User

    from apps.design_studio.models import Collection, DesignBoard, Designer
    from apps.inventory.models import InventoryItem, PurchaseOrder, Supplier
    from crm_api.models import (BoutiqueSettings, Customer, CustomerMessage,
                                Order, Tailor)

    # .order_by('id') because the table has no Meta.ordering and holds exactly
    # one row, written as id=1 by SignupView. An unordered first() on one row is
    # the same row, but only by luck.
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

        # 'tailors': the only screen that invites staff is Manage Tailors --
        # TailorViewSet._ensure_user_account is what creates the User, and it is
        # mounted at /api/tailors/. (DesignerViewSet can also mint an account,
        # but that path is behind design_studio, so with the team module off
        # there is no route a boutique can be expected to have used.)
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

        # No module key: CustomerMessage hangs off /api/orders/, which
        # core.modules lists as STRUCTURAL precisely because messaging, payments
        # and the production workflow share that one prefix. It cannot be
        # switched off, so this step is always the boutique's to complete.
        _step('communication', 'A customer message actually sent',
              sent_messages > 0,
              f'{sent_messages} message(s) marked SENT.' if sent_messages else
              'No message has been marked SENT. Rows here queue themselves on '
              'order events, so their mere existence proves nothing -- only the '
              'SENT status means somebody actually sent one.'),

        # Designers, collections and boards are all routers under
        # /api/design-studio/ (apps/design_studio/urls.py), which is the
        # design_studio module's own prefix.
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
              # 'inventory', not 'inventory_catalog': all three tables counted
              # here are served from /api/inventory/, and the narrower
              # /api/inventory/catalog/ module owns CatalogItem, which is
              # exactly what this step refuses to count.
              module='inventory'),
    ]


def _unreadable(detail):
    """What every field says when the schema could not be read.

    percent is None rather than 0 on purpose. A 0% and an unreadable boutique
    look identical on a progress bar and mean opposite things: one has done
    nothing, the other has a broken schema and needs an engineer.
    """
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
    """The single word the console colours a row with.

    Suspension wins over progress: a suspended boutique cannot sign in
    (TenantHeaderMiddleware refuses it with a 403), so its remaining steps are
    not work it has failed to do, and showing it as "in progress" would put it
    in the queue of boutiques somebody is meant to chase.
    """
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
    """Onboarding for one boutique: the steps, the percentage and the blockage.

    ponytail: one schema switch and ~13 aggregates per boutique, so a console
    page that calls this for every tenant is O(tenants) round trips -- the same
    ceiling superadmin/metrics.py already carries. Roll it into a public-schema
    summary table on a schedule if the tenant count reaches the hundreds.
    """
    if tenant.schema_name == get_public_schema_name():
        return _unreadable('The public schema is the registry the console runs '
                           'in, not a boutique.')

    try:
        # tenant_scope, not schema_context: a registry row whose schema was
        # never created would otherwise resolve auth_user against public and
        # report the platform's own superuser as this boutique's staff. See
        # superadmin/schemas.py -- nothing raises, so nothing catches it.
        with tenant_scope(tenant):
            declared = _tracked_steps(tenant)
    except Exception as exc:
        # Same discipline as metrics.tenant_metrics: one broken boutique reports
        # itself broken and does not take the rest of the page down. This is
        # exactly the state an administrator opens this screen to find.
        return _unreadable(f"This boutique's schema could not be read: {exc}")

    # The split that keeps a switched-off module from reading as a failure.
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
        # The whole step, not just its key: this is what the console prints as
        # the reason a boutique is stuck, and it already carries the sentence.
        'blocked_on': blocked_on,
        'tracked_steps': len(tracked),
        'completed_steps': completed,
        'percent_basis': (
            f'{completed} of {len(tracked)} tracked steps. {len(gated)} step(s) '
            f'belong to a module switched off for this boutique and '
            f'{len(UNTRACKED)} have no signal in this product; both sets are '
            f'excluded from this percentage rather than counted as incomplete.'),
        'steps': tracked + gated + [
            # done is None, not False. False renders as a red cross, and a cross
            # against a step nothing can measure is an accusation.
            {'key': key, 'label': label, 'done': None, 'detail': detail,
             'tracked': False, 'state': 'untracked', 'module': None}
            for key, label, detail in UNTRACKED
        ],
        'detail': '',
    }


def steps(tenant):
    """The ordered step list alone, for a caller that wants only the checklist.

    Empty for an unreadable schema -- see _unreadable(): there is nothing
    truthful to say about a step in a schema that could not be opened. Call
    progress() if you need to tell that apart from a boutique with no steps.
    """
    return progress(tenant)['steps']
