
import re

from django.db import migrations


NATIONAL_NUMBER_LENGTH = 10
COUNTRY_CODE = '91'


def _canonical(raw):
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


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0023_order_special_instructions'),
    ]

    operations = [
        migrations.RunPython(normalise, noop),
    ]
