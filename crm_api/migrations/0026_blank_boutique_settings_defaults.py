"""Stop the vendor's demo contact details printing as the boutique's own.

Changing the field defaults only helps rows created after this runs. Every
BoutiqueSettings that already exists still carries "123 Atelier Way, Fashion
District", "+91 9999999999" and "contact@scaleezy.com" -- and that row is
conjured by get_or_create(id=1) wherever it is first needed, so boutiques that
never opened their profile screen are exactly the ones holding it. Those strings
render on the printed invoice and on the public customer tracking page as the
boutique's own address and phone number.

So the old defaults are cleared where they are still EXACTLY the defaults. An
exact match is the whole safety argument: nobody types "123 Atelier Way, Fashion
District" as their real address, and any value that differs by even a character
is somebody's edit and is left alone.
"""

from django.db import migrations, models


# The values as they were defined before this migration. Written out rather than
# imported, so this keeps doing the same thing when the model moves on.
OLD_DEFAULTS = {
    'name': 'Scaleezy Atelier',
    'address': '123 Atelier Way, Fashion District',
    'phone': '+91 9999999999',
    'email': 'contact@scaleezy.com',
}


def clear_vendor_defaults(apps, schema_editor):
    BoutiqueSettings = apps.get_model('crm_api', 'BoutiqueSettings')
    for row in BoutiqueSettings.objects.all():
        changed = [field for field, old in OLD_DEFAULTS.items()
                   if getattr(row, field) == old]
        if not changed:
            continue
        for field in changed:
            setattr(row, field, '')
        row.save(update_fields=changed)


def noop(apps, schema_editor):
    """Not reversible: an empty string and an untouched default are the same
    state once cleared, and restoring the demo strings would put the vendor's
    address back on a real boutique's invoice."""


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0025_unguessable_upload_paths'),
    ]

    operations = [
        migrations.AlterField(
            model_name='boutiquesettings',
            name='address',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='boutiquesettings',
            name='email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AlterField(
            model_name='boutiquesettings',
            name='name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='boutiquesettings',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        # After the AlterFields, so the column can hold '' when this runs.
        migrations.RunPython(clear_vendor_defaults, noop),
    ]
