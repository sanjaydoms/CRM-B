
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_add_gown_suit_sherwani'),
        ('inventory', '0008_customermaterial_customermaterialmovement_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordermaterialline',
            name='garment_job',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='material_lines', to='catalog.garmentjob'),
        ),
        migrations.AddField(
            model_name='ordermaterialline',
            name='job_material',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='material_lines', to='catalog.jobmaterial'),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='garment_job',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_movements', to='catalog.garmentjob'),
        ),
        migrations.AlterField(
            model_name='ordermaterialplan',
            name='bom',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='plans', to='inventory.billofmaterials'),
        ),
        migrations.AlterField(
            model_name='ordermaterialplan',
            name='bom_version',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
