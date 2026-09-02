
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0021_boutiquesettings_customer_messaging_enabled_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='garment_images_published',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='GarmentImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('view', models.CharField(choices=[('FRONT', 'Front view'), ('BACK', 'Back view'), ('LEFT', 'Left side'), ('RIGHT', 'Right side'), ('DETAIL', 'Close-up detail'), ('FABRIC', 'Fabric texture'), ('SLEEVE', 'Sleeve detail'), ('BLOUSE', 'Blouse detail'), ('DUPATTA', 'Dupatta styling')], default='FRONT', max_length=20)),
                ('image', models.ImageField(upload_to='finished_garments/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='garment_images', to='crm_api.order')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['view', 'uploaded_at'],
            },
        ),
    ]
