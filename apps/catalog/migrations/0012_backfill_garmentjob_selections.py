# Orders placed before GarmentJob.selections existed. Their design picks did
# reach the design board at confirm, so those are read back from there, part
# by part. Their fabric picks reached nothing at all -- confirm dropped them --
# so for these orders the stage panel shows the designs and "No fabric
# selected". Nothing can restore what was never written.

from django.db import migrations

CUSTOMER_SOURCES = ('customer_upload', 'customer_link')


def backfill(apps, schema_editor):
    GarmentJob = apps.get_model('catalog', 'GarmentJob')
    DesignBoardItem = apps.get_model('design_studio', 'DesignBoardItem')
    DesignImage = apps.get_model('design_studio', 'DesignImage')

    for job in GarmentJob.objects.filter(selections={}):
        items = [i for i in DesignBoardItem.objects.filter(garment_job=job).order_by('position')
                 if i.image_url]
        if not items:
            continue
        # The board item kept the photograph and the part, not the catalogue
        # design it came off. The photograph itself finds the design again.
        titles = dict(
            DesignImage.objects.filter(image_url__in=[i.image_url for i in items])
            .values_list('image_url', 'design__title'))
        parts, part_refs = {}, {}
        for item in items:
            row = {'id': str(item.id), 'part': item.part, 'part_label': item.title,
                   'image_url': item.image_url, 'source': item.source}
            if item.source in CUSTOMER_SOURCES:
                part_refs.setdefault(item.part, []).append(
                    {**row, 'design_title': item.title, 'source_url': item.source_url})
            elif item.is_selected and item.part not in parts:
                parts[item.part] = {**row, 'design_title': titles.get(item.image_url, '')}
        if not parts and not part_refs:
            continue
        job.selections = {
            'design': {'parts': parts, 'part_refs': part_refs},
            'fabrics': {}, 'fabric_items': [], 'slot_labels': {},
        }
        job.save(update_fields=['selections'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0011_garmentjob_selections'),
        ('design_studio', '0019_designasset_catalogue'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
