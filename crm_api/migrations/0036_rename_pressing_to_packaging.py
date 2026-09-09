from django.db import migrations

OLD, NEW = 'Pressing Staff', 'Packaging Staff'


def _rename_in_config(config):
    changed = False
    for stage in config or []:
        if not isinstance(stage, dict):
            continue
        roles = stage.get('roles') or []
        if OLD in roles:
            stage['roles'] = [NEW if r == OLD else r for r in roles]
            changed = True
    return changed


def forwards(apps, schema_editor):
    Tailor = apps.get_model('crm_api', 'Tailor')
    Notification = apps.get_model('crm_api', 'Notification')
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')

    Tailor.objects.filter(role=OLD).update(role=NEW)
    Notification.objects.filter(recipient_role=OLD).update(recipient_role=NEW)

    for s in BoutiqueSettings.objects.all():
        dirty = _rename_in_config(s.workflow_config)
        rm = s.role_modules
        if isinstance(rm, dict) and OLD in rm and NEW not in rm:
            rm[NEW] = rm.pop(OLD)
            dirty = True
        if dirty:
            s.save(update_fields=['workflow_config', 'role_modules'])


def backwards(apps, schema_editor):
    Tailor = apps.get_model('crm_api', 'Tailor')
    Notification = apps.get_model('crm_api', 'Notification')
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')
    Tailor.objects.filter(role=NEW).update(role=OLD)
    Notification.objects.filter(recipient_role=NEW).update(recipient_role=OLD)
    for s in BoutiqueSettings.objects.all():
        changed = False
        for stage in s.workflow_config or []:
            if isinstance(stage, dict) and NEW in (stage.get('roles') or []):
                stage['roles'] = [OLD if r == NEW else r for r in stage['roles']]
                changed = True
        if changed:
            s.save(update_fields=['workflow_config'])


class Migration(migrations.Migration):
    dependencies = [('crm_api', '0035_alter_tailor_role')]
    operations = [migrations.RunPython(forwards, backwards)]
