"""Link designs stranded by a garment that had no template yet.

The seeded catalogue's three gowns sat in the library's Uncategorised section
because there was no Gown template to link them to. catalog.0004 adds Gown, Suit
and Sherwani, so the pass can now place them.

Same idempotent backfill as 0005 and 0008: it only touches designs with no
template and no tags, so anything already linked or corrected by hand is left
alone. It runs again here rather than being folded into the earlier migration
because those have already been applied.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    from importlib import import_module
    module = import_module('apps.design_studio.migrations.0005_backfill_template_tags')
    module.backfill(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('design_studio', '0008_backfill_moved_catalogue_tags'),
        ('catalog', '0004_add_gown_suit_sherwani'),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
