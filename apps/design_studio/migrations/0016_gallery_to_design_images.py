"""Move existing gallery URLs onto DesignImage rows.

`DesignAsset.gallery` is a flat list of URL strings with no notion of which part
of the garment each one shows. Every one of them becomes an 'overall' image,
which is the honest answer: nobody recorded a part, so the only thing that can
be claimed is that the picture is of the design.

`gallery` is left populated rather than cleared. It is still what the portfolio
serializer reads, and emptying it here would blank those galleries in the same
deploy that adds the new table for no gain. It stops being written on new
uploads; the column can be dropped once nothing reads it.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')
    DesignImage = apps.get_model('design_studio', 'DesignImage')

    rows = []
    for asset in DesignAsset.objects.exclude(gallery=[]).iterator():
        for position, url in enumerate(asset.gallery or []):
            if not url:
                continue
            rows.append(DesignImage(
                design=asset, part='overall', image_url=url, sequence=position))
    DesignImage.objects.bulk_create(rows, batch_size=500)


def backwards(apps, schema_editor):
    # The rows this migration created are the ones it can identify: 'overall'
    # images whose URL is already in the design's gallery. Anything uploaded
    # against a real part after this ran is new data and is left alone.
    DesignImage = apps.get_model('design_studio', 'DesignImage')
    for image in DesignImage.objects.filter(part='overall').select_related('design'):
        if image.image_url in (image.design.gallery or []):
            image.delete()


class Migration(migrations.Migration):

    dependencies = [('design_studio', '0015_designimage')]

    operations = [migrations.RunPython(forwards, backwards)]
