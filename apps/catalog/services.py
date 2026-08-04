"""Loading the shipped templates into the database.

Only the global rows (tenant is null) are touched. A boutique that has forked a
garment owns its copy outright, so a redeploy can never undo the owner's edits.
"""

from django.db import transaction

from .definitions import all_templates


@transaction.atomic
def sync_global_templates(models=None):
    """Create or update the twelve defaults. Safe to run repeatedly.

    `models` lets a data migration pass in its historical model classes rather
    than importing the live ones, which is what keeps old migrations replayable.
    """
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
            # Rebuilding is simpler than diffing, and safe: jobs keep their own
            # frozen spec, they do not point at field rows.
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
                # Copy rather than pop: the common-field dicts are module-level
                # and shared by all twelve templates.
                attrs = {k: v for k, v in field_def.items() if k != 'options'}
                db_field = Field.objects.create(section=section, sequence=order, **attrs)
                for opt_order, (value, label) in enumerate(field_def['options']):
                    Option.objects.create(
                        field=db_field, value=value, label=label, sequence=opt_order,
                    )

    return {'created': created, 'updated': updated}
