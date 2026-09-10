
import re

from django.db import migrations


def _slug(value):
    return re.sub(r'[^a-z0-9]+', '_', str(value).lower()).strip('_')


def backfill(apps, schema_editor):
    GarmentTemplate = apps.get_model('catalog', 'GarmentTemplate')
    DesignAsset = apps.get_model('design_studio', 'DesignAsset')

    templates = list(GarmentTemplate.objects.filter(tenant__isnull=True, is_active=True))
    if not templates:
        return

    by_name = {}
    for template in templates:
        by_name[_slug(template.key)] = template
        by_name[_slug(template.name)] = template

    allowed = {}
    for template in templates:
        for section in template.sections.all():
            for field in section.fields.all():
                values = {o.value for o in field.options.all() if o.is_active}
                if values:
                    allowed.setdefault(field.key, set()).update(values)

    ATTRIBUTE_KEYS = {
        'sleeve': 'sleeve_length',
        'sleeve_style': 'sleeve_length',
        'neck': 'front_neck',
        'neck_type': 'front_neck',
        'neckline': 'front_neck',
        'occasion': 'occasion',
    }

    linked = tagged = 0
    for asset in DesignAsset.objects.all().iterator():
        changed = []

        if asset.template_id is None and asset.garment_type:
            template = by_name.get(_slug(asset.garment_type))
            if template is not None:
                asset.template = template
                changed.append('template')
                linked += 1

        if not asset.spec_tags:
            tags = {}
            candidates = dict(asset.attributes or {})
            if asset.occasion:
                candidates.setdefault('occasion', asset.occasion)

            for raw_key, raw_value in candidates.items():
                key = ATTRIBUTE_KEYS.get(raw_key, raw_key)
                if key not in allowed or not isinstance(raw_value, str):
                    continue
                value = _slug(raw_value)
                if value in allowed[key]:
                    tags[key] = value

            if tags:
                asset.spec_tags = tags
                changed.append('spec_tags')
                tagged += 1

        if changed:
            asset.save(update_fields=changed)

    if linked or tagged:
        print(f"  linked {linked} design(s) to a template, tagged {tagged}")


def clear(apps, schema_editor):
    apps.get_model('design_studio', 'DesignAsset').objects.update(template=None, spec_tags={})


class Migration(migrations.Migration):

    dependencies = [
        ('design_studio', '0004_designasset_approved_at_designasset_approved_by_and_more'),
        ('catalog', '0003_resync_templates'),
    ]

    operations = [migrations.RunPython(backfill, clear)]
