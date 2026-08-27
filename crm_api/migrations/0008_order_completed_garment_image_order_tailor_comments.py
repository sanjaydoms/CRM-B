
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0007_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='completed_garment_image',
            field=models.ImageField(blank=True, null=True, upload_to='completed_garments/'),
        ),
        migrations.AddField(
            model_name='order',
            name='tailor_comments',
            field=models.TextField(blank=True, null=True),
        ),
    ]
