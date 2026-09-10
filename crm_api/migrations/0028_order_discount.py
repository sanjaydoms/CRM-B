
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0027_orderdraft'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='discount',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=10),
        ),
    ]
