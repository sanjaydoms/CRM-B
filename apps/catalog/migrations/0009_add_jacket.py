"""The ethnic jacket joins the garment templates.

Same shape as 0004 and 0007: the definitions gained a garment, so the global
templates are re-synced from them. Existing templates keep their rows and
their jobs; only their sections are rewritten from the same definitions they
already came from.
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

    dependencies = [('catalog', '0008_revive_lehenga_blouse')]

    operations = [migrations.RunPython(resync, migrations.RunPython.noop)]
