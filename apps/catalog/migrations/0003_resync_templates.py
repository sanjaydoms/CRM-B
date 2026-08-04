"""Re-sync the shipped templates after two definition changes.

Delivery date is no longer required, and the saree's style and material groups
now appear only for the services actually ticked. Boutiques that forked a
garment keep their own copy -- sync_global_templates only touches tenant=null.
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

    dependencies = [('catalog', '0002_seed_templates')]

    # Irreversible by design: rolling back would need the previous definitions,
    # which live in the file this migration exists to replace.
    operations = [migrations.RunPython(resync, migrations.RunPython.noop)]
