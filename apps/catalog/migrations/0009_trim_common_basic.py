"""Drop Occasion, Material Source, Design Reference, Reference Links and
Priority from every garment's Basic Information section.

Values already saved under those keys stay in GarmentJob.spec (a JSON field);
only the form stops asking for them.
"""

from django.db import migrations

from apps.catalog.services import sync_global_templates


def sync(apps, schema_editor):
    sync_global_templates({
        'GarmentTemplate': apps.get_model('catalog', 'GarmentTemplate'),
        'TemplateSection': apps.get_model('catalog', 'TemplateSection'),
        'TemplateField': apps.get_model('catalog', 'TemplateField'),
        'TemplateFieldOption': apps.get_model('catalog', 'TemplateFieldOption'),
    })


class Migration(migrations.Migration):

    dependencies = [('catalog', '0008_revive_lehenga_blouse')]

    operations = [migrations.RunPython(sync, migrations.RunPython.noop)]
