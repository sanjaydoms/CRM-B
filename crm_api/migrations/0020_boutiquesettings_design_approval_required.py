
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0019_add_maggam_finishing_pressing_stages'),
    ]

    operations = [
        migrations.AddField(
            model_name='boutiquesettings',
            name='design_approval_required',
            field=models.BooleanField(default=False),
        ),
    ]
