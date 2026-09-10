"""Lehenga Blouse comes back as a garment of its own.

0007 retired it into `blouse` on the grounds that a lehenga blouse is a blouse.
The boutique wants it separable again, so that a lehenga blouse photograph is
filed under its own garment in the design library rather than mixed in with
saree blouses.

Reactivated, not recreated: sync_global_templates sets is_active=True on a
template it finds by key, so the original row keeps its id and every GarmentJob
that still points at it goes on rendering. Nothing is taken away from `blouse`
-- the styles 0007 moved there stay there, and a boutique that has been filing
lehenga blouses under Blouse can carry on doing so.
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

    dependencies = [('catalog', '0007_design_parts_and_bottom_wear')]

    # Irreversible for the same reason 0007 is: rolling back would need the
    # previous definitions, which live in the file this migration replaces.
    operations = [migrations.RunPython(sync, migrations.RunPython.noop)]
