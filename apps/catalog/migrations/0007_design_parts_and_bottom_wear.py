"""Design parts on every garment, and Bottom Wear in place of four bottoms.

Two changes arriving together because they are the same edit to definitions.py:

* Every garment now carries `design_parts` -- the parts of it a design
  photograph can be of, so the design library files an upload under "Pallu" or
  "Neck" rather than dropping every image into one undifferentiated gallery.

* Salwar, Churidar, Palazzo and Sharara are retired in favour of one Bottom
  Wear garment whose `bottom_type` names the cut. Four templates that differed
  only in which measurements they asked for made the counter staff choose the
  garment before they knew the cut. Lehenga Blouse is retired for the same
  reason -- it is a Blouse.

Retired, not deleted: GarmentJob.template is PROTECT, so a delete fails the
moment a boutique has taken an order for one, and the orders that already exist
still have to render. sync_global_templates deactivates them instead, which
hides them from the order form and the design library while leaving history
intact. Reactivating one is a single is_active update.
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

    dependencies = [('catalog', '0006_garmenttemplate_design_parts')]

    # Irreversible for the same reason 0003 is: rolling back would need the
    # previous definitions, which live in the file this migration replaces.
    operations = [migrations.RunPython(sync, migrations.RunPython.noop)]
