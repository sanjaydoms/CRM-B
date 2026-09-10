
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('crm_api', '0019_add_maggam_finishing_pressing_stages'),
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GarmentTemplate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.CharField(db_index=True, max_length=50)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, null=True)),
                ('version', models.IntegerField(default=1)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sequence', models.IntegerField(default=0)),
                ('tenant', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['sequence', 'name'],
                'unique_together': {('key', 'tenant')},
            },
        ),
        migrations.CreateModel(
            name='GarmentJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('template_version', models.IntegerField()),
                ('spec', models.JSONField(blank=True, default=dict)),
                ('measurements', models.JSONField(blank=True, default=dict)),
                ('sequence', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='garment_jobs', to='crm_api.order')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='jobs', to='catalog.garmenttemplate')),
            ],
            options={
                'ordering': ['sequence', 'created_at'],
            },
        ),
        migrations.CreateModel(
            name='JobMaterial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field_key', models.CharField(max_length=60)),
                ('free_text', models.CharField(blank=True, max_length=200, null=True)),
                ('quantity', models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ('unit', models.CharField(blank=True, max_length=20, null=True)),
                ('source', models.CharField(choices=[('STORE', 'Store inventory'), ('CUSTOMER', 'Customer provided')], default='STORE', max_length=20)),
                ('notes', models.CharField(blank=True, max_length=300, null=True)),
                ('inventory_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='job_materials', to='inventory.inventoryitem')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='materials', to='catalog.garmentjob')),
            ],
            options={
                'ordering': ['field_key'],
            },
        ),
        migrations.CreateModel(
            name='TemplateSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('basic', 'Basic Information'), ('measurements', 'Measurements'), ('style', 'Style & Design Options'), ('materials', 'Materials & Accessories'), ('production', 'Production Notes')], max_length=30)),
                ('title', models.CharField(max_length=100)),
                ('sequence', models.IntegerField(default=0)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='catalog.garmenttemplate')),
            ],
            options={
                'ordering': ['sequence'],
                'unique_together': {('template', 'key')},
            },
        ),
        migrations.CreateModel(
            name='TemplateField',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(db_index=True, max_length=60)),
                ('label', models.CharField(max_length=150)),
                ('field_type', models.CharField(choices=[('text', 'Text'), ('textarea', 'Long text'), ('number', 'Number'), ('select', 'Single choice'), ('multiselect', 'Multiple choice'), ('boolean', 'Yes / No'), ('date', 'Date'), ('file', 'File'), ('inventory_ref', 'Inventory item')], max_length=20)),
                ('unit', models.CharField(blank=True, max_length=10, null=True)),
                ('is_required', models.BooleanField(default=False)),
                ('is_repeatable', models.BooleanField(default=False)),
                ('default', models.JSONField(blank=True, null=True)),
                ('help_text', models.CharField(blank=True, max_length=300, null=True)),
                ('sequence', models.IntegerField(default=0)),
                ('visible_when', models.JSONField(blank=True, null=True)),
                ('validation', models.JSONField(blank=True, default=dict)),
                ('inventory_category', models.CharField(blank=True, choices=[('FABRIC', 'Fabric'), ('BORDER', 'Border & Trim'), ('LINING', 'Lining'), ('EMBELLISHMENT', 'Embellishment'), ('STITCHING', 'Stitching Material'), ('PACKAGING', 'Packaging'), ('MAGGAM', 'Maggam / Embroidery'), ('OTHER', 'Other')], max_length=30, null=True)),
                ('section', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fields', to='catalog.templatesection')),
            ],
            options={
                'ordering': ['sequence'],
            },
        ),
        migrations.CreateModel(
            name='TemplateFieldOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.CharField(max_length=60)),
                ('label', models.CharField(max_length=150)),
                ('sequence', models.IntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('field', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='catalog.templatefield')),
            ],
            options={
                'ordering': ['sequence'],
                'unique_together': {('field', 'value')},
            },
        ),
    ]
