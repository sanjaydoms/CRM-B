
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0020_boutiquesettings_design_approval_required'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='boutiquesettings',
            name='customer_messaging_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='CustomerMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channel', models.CharField(default='whatsapp', max_length=30)),
                ('template_key', models.CharField(db_index=True, max_length=100)),
                ('to_number', models.CharField(max_length=20)),
                ('body', models.TextField()),
                ('status', models.CharField(choices=[('QUEUED', 'Queued'), ('SENT', 'Sent'), ('DELIVERED', 'Delivered'), ('READ', 'Read'), ('FAILED', 'Failed')], db_index=True, default='QUEUED', max_length=20)),
                ('provider_message_id', models.CharField(blank=True, max_length=255, null=True)),
                ('error', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_messages', to='crm_api.order')),
                ('sent_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
