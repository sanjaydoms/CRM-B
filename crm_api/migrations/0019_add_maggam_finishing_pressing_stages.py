from django.db import migrations

NEW_STAGES = [
    ('pattern_cutting', {
        'key': 'maggam_work', 'name': 'Maggam Work', 'sla_hours': 96,
        'roles': ['Owner', 'Master', 'Maggam Master'], 'optional': True,
    }),
    ('stitching_completed', {
        'key': 'finishing', 'name': 'Hemming & Finishing', 'sla_hours': 24,
        'roles': ['Owner', 'Master', 'Finishing Master'],
    }),
    ('finishing', {
        'key': 'pressing', 'name': 'Pressing', 'sla_hours': 12,
        'roles': ['Owner', 'Master', 'Pressing Staff'],
    }),
]

ROLES_TO_DROP = {'ready_for_delivery': ['Finishing Master', 'Pressing Staff']}


def add_stages(apps, schema_editor):
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')
    for config in BoutiqueSettings.objects.all():
        workflow = list(config.workflow_config or [])
        if not workflow:
            continue
        present = {s.get('key') for s in workflow}
        changed = False

        for anchor_key, stage in NEW_STAGES:
            if stage['key'] in present:
                continue
            anchor = next((i for i, s in enumerate(workflow) if s.get('key') == anchor_key), None)
            if anchor is None:
                workflow.append(dict(stage))
            else:
                workflow.insert(anchor + 1, dict(stage))
            present.add(stage['key'])
            changed = True

        for key, drop in ROLES_TO_DROP.items():
            for s in workflow:
                if s.get('key') == key and s.get('roles'):
                    kept = [r for r in s['roles'] if r not in drop]
                    if kept != s['roles']:
                        s['roles'] = kept
                        changed = True

        if changed:
            config.workflow_config = workflow
            config.save(update_fields=['workflow_config'])


def remove_stages(apps, schema_editor):
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')
    added = {s['key'] for _, s in NEW_STAGES}
    for config in BoutiqueSettings.objects.all():
        workflow = [s for s in (config.workflow_config or []) if s.get('key') not in added]
        for key, dropped in ROLES_TO_DROP.items():
            for s in workflow:
                if s.get('key') == key and s.get('roles'):
                    for role in dropped:
                        if role not in s['roles']:
                            s['roles'].append(role)
        config.workflow_config = workflow
        config.save(update_fields=['workflow_config'])


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0018_merge_specialist_roles_into_workflow'),
    ]

    operations = [
        migrations.RunPython(add_stages, remove_stages),
    ]
