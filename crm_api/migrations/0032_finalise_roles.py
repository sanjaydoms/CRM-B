from django.db import migrations, models

#: The four specialist roles the boutique retired. Their stages remain -- the
#: measuring, drafting, cutting and hemming still happen -- but they are no
#: longer gated on a dedicated role, so they fall to whoever hands work out.
DROPPED = ('Measurement Master', 'Pattern Master', 'Cutting Master',
           'Finishing Master')

#: Renamed in place. 'Master' in this boutique means a generalist who
#: supervises the floor, which a quality inspector is not.
RENAMED = {'QC Master': 'QC Staff'}

#: Whoever can hand work out. A stage left with nobody after the specialists
#: were removed would be unadvanceable, so it falls back to these two.
ASSIGNERS = ['Owner', 'Master']


def _remap(role):
    """None if the role is gone, otherwise its current name."""
    if role in DROPPED:
        return None
    return RENAMED.get(role, role)


def _rewrite_stage_roles(config):
    """Strip retired roles from a stored workflow, in place. Returns changed."""
    changed = False
    for stage in config or []:
        if not isinstance(stage, dict):
            continue
        roles, out, seen = stage.get('roles') or [], [], set()
        for role in roles:
            current = _remap(role)
            if current is None or current in seen:
                continue
            seen.add(current)
            out.append(current)
        # The new role joins the handwork stage, otherwise a Karigar in an
        # existing boutique has an empty queue for ever.
        if stage.get('key') == 'maggam_work' and 'Karigar' not in out:
            out.append('Karigar')
            seen.add('Karigar')
        # A boutique that had narrowed a stage to one specialist is left with
        # nothing here, and a stage no role performs is an order that cannot
        # move. Hand it to the people who were always allowed to.
        if not out:
            out = list(ASSIGNERS)
        if out != roles:
            stage['roles'] = out
            changed = True
    return changed


def forwards(apps, schema_editor):
    Tailor = apps.get_model('crm_api', 'Tailor')
    Notification = apps.get_model('crm_api', 'Notification')
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')

    # People keep their job; only the label moves. A retired specialist and a
    # Tailor already resolved to the same module set (core.modules._TAILOR),
    # so nobody gains or loses access here.
    Tailor.objects.filter(role__in=DROPPED).update(role='Tailor')
    Notification.objects.filter(recipient_role__in=DROPPED).update(
        recipient_role='Tailor')
    for old, new in RENAMED.items():
        Tailor.objects.filter(role=old).update(role=new)
        Notification.objects.filter(recipient_role=old).update(
            recipient_role=new)

    for settings in BoutiqueSettings.objects.all():
        dirty = _rewrite_stage_roles(settings.workflow_config)

        # {role: {module: bool}} written by the owner. A key naming a role
        # nobody can hold any more is dead weight; the renamed one must follow
        # its role or the owner's decision is silently forgotten.
        role_modules = settings.role_modules
        if isinstance(role_modules, dict):
            for old, new in RENAMED.items():
                if old in role_modules and new not in role_modules:
                    role_modules[new] = role_modules.pop(old)
                    dirty = True
            for gone in DROPPED:
                if role_modules.pop(gone, None) is not None:
                    dirty = True

        if dirty:
            settings.save(update_fields=['workflow_config', 'role_modules'])


def backwards(apps, schema_editor):
    """Best effort: the rename reverses, the retirements cannot.

    Which Tailors used to be a Cutting Master is not recorded anywhere once
    forwards() has run, so this restores the name QC Master and leaves the
    rest alone rather than guessing at people's jobs.
    """
    Tailor = apps.get_model('crm_api', 'Tailor')
    Notification = apps.get_model('crm_api', 'Notification')
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')
    for old, new in RENAMED.items():
        Tailor.objects.filter(role=new).update(role=old)
        Notification.objects.filter(recipient_role=new).update(
            recipient_role=old)
    for settings in BoutiqueSettings.objects.all():
        changed = False
        for stage in settings.workflow_config or []:
            if not isinstance(stage, dict):
                continue
            roles = stage.get('roles') or []
            back = [old for r in roles for old, new in RENAMED.items()
                    if r == new] or None
            if back:
                stage['roles'] = [
                    {v: k for k, v in RENAMED.items()}.get(r, r) for r in roles]
                changed = True
        if changed:
            settings.save(update_fields=['workflow_config'])


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0031_boutiquesettings_role_modules'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tailor',
            name='role',
            field=models.CharField(
                choices=[('Master', 'Master (generalist)'), ('Tailor', 'Tailor'),
                         ('Maggam Master', 'Maggam Master'), ('Karigar', 'Karigar'),
                         ('Pressing Staff', 'Pressing Staff'), ('QC Staff', 'QC Staff')],
                default='Tailor', max_length=50),
        ),
        migrations.RunPython(forwards, backwards),
    ]
