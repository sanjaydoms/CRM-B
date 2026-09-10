from django.db import migrations

NEW_ROLES_BY_STAGE = {
    'measurements_completed': ['Measurement Master'],
    'pattern_cutting': ['Pattern Master', 'Cutting Master'],
    'master_quality_check': ['QC Master'],
    'ready_for_delivery': ['Finishing Master', 'Pressing Staff'],
}


def merge_specialist_roles(apps, schema_editor):
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')
    for config in BoutiqueSettings.objects.all():
        workflow = config.workflow_config or []
        changed = False
        for stage in workflow:
            additions = NEW_ROLES_BY_STAGE.get(stage.get('key'))
            if not additions:
                continue
            roles = stage.get('roles')
            if not roles:
                continue
            for role in additions:
                if role not in roles:
                    roles.append(role)
                    changed = True
            stage['roles'] = roles
        if changed:
            config.workflow_config = workflow
            config.save(update_fields=['workflow_config'])


def unmerge_specialist_roles(apps, schema_editor):
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')
    added = {r for roles in NEW_ROLES_BY_STAGE.values() for r in roles}
    for config in BoutiqueSettings.objects.all():
        workflow = config.workflow_config or []
        for stage in workflow:
            roles = stage.get('roles')
            if roles:
                stage['roles'] = [r for r in roles if r not in added]
        config.workflow_config = workflow
        config.save(update_fields=['workflow_config'])


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0017_designpreference_approved_at_and_more'),
    ]

    operations = [
        migrations.RunPython(merge_specialist_roles, unmerge_specialist_roles),
    ]
