
from django.db import migrations


def backfill(apps, schema_editor):
    from importlib import import_module
    module = import_module('apps.design_studio.migrations.0005_backfill_template_tags')
    module.backfill(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [('design_studio', '0007_move_catalogue_into_library')]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
