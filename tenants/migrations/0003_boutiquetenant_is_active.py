
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0002_demorequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='boutiquetenant',
            name='is_active',
            field=models.BooleanField(default=True, help_text='Unticked, this boutique cannot sign in or use the API. Its data is kept.'),
        ),
    ]
