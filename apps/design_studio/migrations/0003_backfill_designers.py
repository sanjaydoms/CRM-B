"""Turn the free-text designer credits into Designer rows.

Every design that names a designer gets linked to one. Names are matched
case-insensitively after trimming, because "Priya", "priya " and "PRIYA" are one
person with one portfolio, and splitting them is the whole reason this field is
becoming a foreign key.

The original string is left in place. It is the provenance of an import -- a
Pinterest pin credits someone the boutique has never met -- and dropping it would
lose that.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Designer = apps.get_model('design_studio', 'Designer')
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')

    by_key = {}
    for designer in Designer.objects.all():
        by_key[designer.name.strip().lower()] = designer

    linked = 0
    # Oldest first, so the spelling the boutique used originally is the one the
    # designer ends up named. DesignAsset orders newest-first by default, which
    # would otherwise make the most recent variant win.
    pending = (DesignAsset.objects
               .exclude(designer='')
               .filter(designer_ref__isnull=True)
               .order_by('created_at'))
    for asset in pending:
        name = (asset.designer or '').strip()
        if not name:
            continue
        key = name.lower()
        designer = by_key.get(key)
        if designer is None:
            designer = Designer.objects.create(name=name)
            by_key[key] = designer
        asset.designer_ref = designer
        asset.save(update_fields=['designer_ref'])
        linked += 1

    if linked:
        print(f"  linked {linked} design(s) to {len(by_key)} designer(s)")


def unlink(apps, schema_editor):
    # The Designer rows created here are only reachable through designs, so
    # clearing the links and deleting the rows returns the schema to its
    # previous state without touching the original `designer` strings.
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')
    DesignAsset.objects.update(designer_ref=None)
    apps.get_model('design_studio', 'Designer').objects.filter(user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [('design_studio', '0002_designer_designasset_designer_ref_and_more')]

    operations = [migrations.RunPython(backfill, unlink)]
