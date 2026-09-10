
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UniversalActivity',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('user_name_snapshot', models.CharField(blank=True, max_length=150, null=True)),
                ('module', models.CharField(db_index=True, max_length=50)),
                ('entity_type', models.CharField(db_index=True, max_length=50)),
                ('entity_id', models.CharField(db_index=True, max_length=100)),
                ('action', models.CharField(db_index=True, max_length=50)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('old_value', models.JSONField(blank=True, default=dict)),
                ('new_value', models.JSONField(blank=True, default=dict)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activities', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Universal Activities',
                'ordering': ['-timestamp'],
            },
        ),
    ]
