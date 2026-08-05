"""Move the BoutiqueDesign catalogue into the design library.

One library, one set of filters, one place to attribute and approve a design.
Before this, half the boutique's designs lived in a table with no designer, no
status and no tags, so half the library could not be filtered or approved.

A move, not a copy. The rows are written here and the endpoints that served them
switch over in the same commit, so there is never a moment with two live copies
to keep in sync -- which is what the comment at the top of models.py warns about.

BoutiqueDesign itself is left in place and stops being written to. Deleting the
table is a separate change, once this has run everywhere.
"""

from django.db import migrations


def move(apps, schema_editor):
    BoutiqueDesign = apps.get_model('crm_api', 'BoutiqueDesign')
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')

    moved = 0
    for design in BoutiqueDesign.objects.all().order_by('id'):
        source = 'catalogue' if design.is_boutique else 'suggestion'
        external_id = str(design.id)

        # external_id + source is already unique-constrained, so a second run
        # updates the row it created rather than making another one.
        existing = DesignAsset.objects.filter(source=source, external_id=external_id).first()
        if existing is not None:
            continue

        attributes = {}
        if design.neckline_style:
            attributes['neckline_style'] = design.neckline_style
        if design.sleeve_style:
            attributes['sleeve_style'] = design.sleeve_style

        DesignAsset.objects.create(
            source=source,
            external_id=external_id,
            title=design.name,
            image_url=design.image_url,
            description=design.description or '',
            garment_type=design.garment_type or '',
            attributes=attributes,
            estimated_price=design.price,
            # Catalogue entries are live work the boutique already sells.
            status='ACTIVE',
            visibility='BOUTIQUE',
        )
        moved += 1

    if moved:
        print(f"  moved {moved} catalogue design(s) into the library")


def unmove(apps, schema_editor):
    # Only the rows this migration created: they are the ones carrying a
    # catalogue/suggestion source together with an external id.
    apps.get_model('design_studio', 'DesignAsset').objects.filter(
        source__in=['catalogue', 'suggestion']
    ).exclude(external_id='').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('design_studio', '0006_designasset_description_alter_designasset_source'),
        ('crm_api', '0001_initial'),
    ]

    operations = [migrations.RunPython(move, unmove)]
