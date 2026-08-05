"""Link the moved catalogue rows to their templates.

Ordering gap: 0005 backfilled `template` and `spec_tags` across the library, and
0007 then moved the catalogue in behind it. The moved rows therefore arrived
after the only pass that would have linked them, and every one of them landed in
the library's "Uncategorised" section -- eleven designs in the seeded boutique,
which is the entire catalogue.

Re-runs the same pass. It only touches rows with no template and no tags, so
designs already linked or hand-corrected are left exactly as they are, and 0005
remains correct for anyone migrating from scratch in the other order.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    from importlib import import_module
    module = import_module('apps.design_studio.migrations.0005_backfill_template_tags')
    module.backfill(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [('design_studio', '0007_move_catalogue_into_library')]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
