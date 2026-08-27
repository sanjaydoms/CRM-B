
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

    created = updated = 0
    for definition in all_templates():
        template, was_created = Template.objects.get_or_create(
            key=definition['key'], tenant=None,
            defaults={'name': definition['name'], 'sequence': definition['sequence']},
        )
        if was_created:
            created += 1
        else:
            template.name = definition['name']
            template.sequence = definition['sequence']
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

    return {'created': created, 'updated': updated}
