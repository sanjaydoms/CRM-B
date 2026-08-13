"""Store every existing customer's mobile number in its canonical form.

CustomerSerializer.validate_mobile_number now returns whatsapp_number(value)
rather than the raw string, so new and edited customers are stored canonically.
Without this migration only new rows would be, which is the worse of the two
states: the same person could exist twice, once under each spelling, and
searching either one would find only its own row.

Collisions are expected and are NOT merged here. Two customer records that
normalise to the same number are two records with their own orders,
measurements and history, and deciding which survives is a business call rather
than a migration's. Those rows are left exactly as they are and reported in the
migration output, so an operator can see which clients need merging by hand.
Everything else is normalised, which is the overwhelming majority.
"""

import re

from django.db import migrations


NATIONAL_NUMBER_LENGTH = 10
COUNTRY_CODE = '91'


def _canonical(raw):
    """A copy of crm_api.models.whatsapp_number, deliberately.

    A migration must keep doing what it did on the day it was written. Calling
    the live helper would make this migration's result change the next time
    that function is tuned -- and a data migration that rewrites a unique column
    differently depending on when it runs is how two databases silently diverge.
    """
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('00'):
        digits = digits[2:]
    if len(digits) > NATIONAL_NUMBER_LENGTH and digits.startswith(COUNTRY_CODE):
        national = digits[len(COUNTRY_CODE):]
    else:
        national = digits
    national = national.lstrip('0')
    if len(national) == NATIONAL_NUMBER_LENGTH:
        return COUNTRY_CODE + national
    return digits if 11 <= len(digits) <= 15 else ''


def normalise(apps, schema_editor):
    Customer = apps.get_model('crm_api', 'Customer')

    taken = set()
    pending = []
    for customer in Customer.objects.all().order_by('pk'):
        canonical = _canonical(customer.mobile_number)
        if not canonical or canonical == customer.mobile_number:
            # Unparseable numbers are left alone rather than blanked: the digits
            # someone typed are the only record of how to reach that client, and
            # a migration must not be the thing that throws them away.
            taken.add(customer.mobile_number)
            continue
        pending.append((customer, canonical))

    collisions = []
    for customer, canonical in pending:
        if canonical in taken:
            collisions.append((customer.pk, customer.mobile_number, canonical))
            continue
        customer.mobile_number = canonical
        customer.save(update_fields=['mobile_number'])
        taken.add(canonical)

    if collisions:
        print(f"\n  {len(collisions)} customer(s) left unnormalised -- their "
              f"number already belongs to another record. Merge by hand:")
        for pk, raw, canonical in collisions:
            print(f"    customer {pk}: {raw!r} would become {canonical!r}")


def noop(apps, schema_editor):
    """Irreversible by design.

    The original spellings are not recorded anywhere, so there is nothing to
    restore. Reversing the migration leaves the canonical numbers in place,
    which is harmless -- they are valid numbers either way.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0023_order_special_instructions'),
    ]

    operations = [
        migrations.RunPython(normalise, noop),
    ]
