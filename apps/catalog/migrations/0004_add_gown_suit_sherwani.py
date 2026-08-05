"""Add Gown, Suit and Sherwani.

The boutique stitches all three -- the seeded catalogue has three gowns, and the
order wizard offered Gown, Suit and Sherwani before the templates replaced its
hardcoded list. Without templates for them those designs sat in the library's
Uncategorised section and no order could be taken for them at all.

Suit is the kameez and Sherwani is the coat: the bottom and the dupatta worn with
either are separate dresses on the order, which is what lets each carry its own
measurements and go to its own tailor.
"""

from django.db import migrations

from apps.catalog.services import sync_global_templates


def resync(apps, schema_editor):
    sync_global_templates({
        'GarmentTemplate': apps.get_model('catalog', 'GarmentTemplate'),
        'TemplateSection': apps.get_model('catalog', 'TemplateSection'),
        'TemplateField': apps.get_model('catalog', 'TemplateField'),
        'TemplateFieldOption': apps.get_model('catalog', 'TemplateFieldOption'),
    })


class Migration(migrations.Migration):

    dependencies = [('catalog', '0003_resync_templates')]

    operations = [migrations.RunPython(resync, migrations.RunPython.noop)]
