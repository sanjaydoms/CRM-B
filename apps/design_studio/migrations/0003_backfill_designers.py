
from django.db import migrations


def backfill(apps, schema_editor):
    Designer = apps.get_model('design_studio', 'Designer')
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')

    by_key = {}
    for designer in Designer.objects.all():
        by_key[designer.name.strip().lower()] = designer

    linked = 0
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
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')
    DesignAsset.objects.update(designer_ref=None)
    apps.get_model('design_studio', 'Designer').objects.filter(user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [('design_studio', '0002_designer_designasset_designer_ref_and_more')]

    operations = [migrations.RunPython(backfill, unlink)]
