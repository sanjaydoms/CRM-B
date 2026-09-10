
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0019_add_maggam_finishing_pressing_stages'),
        ('design_studio', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Designer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=150)),
                ('employee_id', models.CharField(blank=True, default='', max_length=50)),
                ('profile_image', models.CharField(blank=True, default='', max_length=500)),
                ('specialisation', models.CharField(blank=True, default='', max_length=150)),
                ('experience_years', models.DecimalField(decimal_places=1, default=0, max_digits=4)),
                ('bio', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('joined_at', models.DateField(blank=True, null=True)),
                ('last_active_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('staff', models.ForeignKey(blank=True, help_text='Set when this designer also works on the production floor.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='designer_profiles', to='crm_api.tailor')),
                ('user', models.OneToOneField(blank=True, help_text='Set once designers have their own login. Null means credit only.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='designer_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='designasset',
            name='designer_ref',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='designs', to='design_studio.designer'),
        ),
        migrations.AddConstraint(
            model_name='designer',
            constraint=models.UniqueConstraint(fields=('name',), name='designer_unique_name'),
        ),
    ]
