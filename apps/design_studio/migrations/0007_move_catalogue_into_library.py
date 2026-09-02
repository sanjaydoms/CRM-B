
from django.db import migrations


def move(apps, schema_editor):
    BoutiqueDesign = apps.get_model('crm_api', 'BoutiqueDesign')
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')

    moved = 0
    for design in BoutiqueDesign.objects.all().order_by('id'):
        source = 'catalogue' if design.is_boutique else 'suggestion'
        external_id = str(design.id)

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
            status='ACTIVE',
            visibility='BOUTIQUE',
        )
        moved += 1

    if moved:
        print(f"  moved {moved} catalogue design(s) into the library")


def unmove(apps, schema_editor):
    apps.get_model('design_studio', 'DesignAsset').objects.filter(
        source__in=['catalogue', 'suggestion']
    ).exclude(external_id='').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('design_studio', '0006_designasset_description_alter_designasset_source'),
        ('crm_api', '0001_initial'),
    ]

    operations = [migrations.RunPython(move, unmove)]
