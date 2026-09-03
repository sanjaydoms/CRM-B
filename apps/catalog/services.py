
from django.db import transaction

from .definitions import all_templates


@transaction.atomic
def sync_global_templates(models=None):
    if models is None:
        from . import models as live
        models = {
            'GarmentTemplate': live.GarmentTemplate,
            'TemplateSection': live.TemplateSection,
            'TemplateField': live.TemplateField,
            'TemplateFieldOption': live.TemplateFieldOption,
        }

    Template = models['GarmentTemplate']
    Section = models['TemplateSection']
    Field = models['TemplateField']
    Option = models['TemplateFieldOption']

    # Migration 0003 and 0004 call this with their own historical models, which
    # were frozen before design_parts existed (0006). Writing the column
    # unconditionally makes those two migrations fail on any database built
    # from scratch -- which is every test run. Ask the model what it has rather
    # than assuming the current shape; a data migration that calls live code
    # has to survive being replayed against an older schema.
    has_parts = any(f.name == 'design_parts' for f in Template._meta.get_fields())

    created = updated = 0
    for definition in all_templates():
        defaults = {'name': definition['name'], 'sequence': definition['sequence']}
        if has_parts:
            defaults['design_parts'] = definition['design_parts']
        template, was_created = Template.objects.get_or_create(
            key=definition['key'], tenant=None, defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            template.name = definition['name']
            template.sequence = definition['sequence']
            if has_parts:
                template.design_parts = definition['design_parts']
            template.version += 1
            template.is_active = True
            template.save()
            Section.objects.filter(template=template).delete()
            updated += 1

        for section_def in definition['sections']:
            section = Section.objects.create(
                template=template,
                key=section_def['key'],
                title=section_def['title'],
                sequence=section_def['sequence'],
            )
            for order, field_def in enumerate(section_def['fields']):
                attrs = {k: v for k, v in field_def.items() if k != 'options'}
                db_field = Field.objects.create(section=section, sequence=order, **attrs)
                for opt_order, (value, label) in enumerate(field_def['options']):
                    Option.objects.create(
                        field=db_field, value=value, label=label, sequence=opt_order,
                    )

    # A garment dropped from definitions.py is retired, not deleted. GarmentJob
    # points at its template with PROTECT, so a delete would fail the moment any
    # boutique had taken an order for it -- and the orders that already exist
    # still have to render. Deactivating hides it from the order form and the
    # design library while leaving every past job readable.
    retired = (Template.objects
               .filter(tenant=None, is_active=True)
               .exclude(key__in=[d['key'] for d in all_templates()])
               .update(is_active=False))

    return {'created': created, 'updated': updated, 'retired': retired}
