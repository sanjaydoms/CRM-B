"""Load the twelve shipped garment templates.

Written as a data migration rather than a fixture so a redeploy re-syncs the
global defaults, while every boutique's own forked template is left alone.
"""

from django.db import migrations

from apps.catalog.services import sync_global_templates


def seed(apps, schema_editor):
    sync_global_templates({
        'GarmentTemplate': apps.get_model('catalog', 'GarmentTemplate'),
        'TemplateSection': apps.get_model('catalog', 'TemplateSection'),
        'TemplateField': apps.get_model('catalog', 'TemplateField'),
        'TemplateFieldOption': apps.get_model('catalog', 'TemplateFieldOption'),
    })


def unseed(apps, schema_editor):
    apps.get_model('catalog', 'GarmentTemplate').objects.filter(tenant__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [('catalog', '0001_initial')]

    operations = [migrations.RunPython(seed, unseed)]
