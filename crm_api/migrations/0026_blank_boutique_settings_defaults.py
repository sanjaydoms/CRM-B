
from django.db import migrations, models


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
        migrations.RunPython(clear_vendor_defaults, noop),
    ]
