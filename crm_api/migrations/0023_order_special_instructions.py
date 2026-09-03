
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0022_order_garment_images_published_garmentimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='special_instructions',
            field=models.TextField(blank=True, default=''),
        ),
    ]
