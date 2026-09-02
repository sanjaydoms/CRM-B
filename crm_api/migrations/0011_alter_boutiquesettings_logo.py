
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0010_boutiquesettings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='boutiquesettings',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='stage_images/'),
        ),
    ]
