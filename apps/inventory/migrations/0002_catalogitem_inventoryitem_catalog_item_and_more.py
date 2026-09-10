
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CatalogItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=200)),
                ('item_type', models.CharField(choices=[('MATERIAL', 'Material'), ('CONSUMABLE', 'Consumable'), ('TOOL', 'Tool'), ('MACHINE', 'Machine'), ('ASSET', 'Asset'), ('DOCUMENT', 'Document'), ('SYSTEM', 'System / Software'), ('PRODUCT_CATEGORY', 'Product Category')], db_index=True, default='MATERIAL', max_length=20)),
                ('default_unit', models.CharField(choices=[('METER', 'Meter'), ('PIECE', 'Piece'), ('PAIR', 'Pair'), ('ROLL', 'Roll'), ('PACKET', 'Packet'), ('BOX', 'Box'), ('SET', 'Set'), ('KILOGRAM', 'Kilogram'), ('GRAM', 'Gram'), ('STRING', 'String'), ('UNIT', 'Unit')], default='PIECE', max_length=20)),
                ('legacy_category', models.CharField(choices=[('FABRIC', 'Fabric'), ('BORDER', 'Border & Trim'), ('LINING', 'Lining'), ('EMBELLISHMENT', 'Embellishment'), ('STITCHING', 'Stitching Material'), ('PACKAGING', 'Packaging'), ('MAGGAM', 'Maggam / Embroidery'), ('OTHER', 'Other')], db_index=True, max_length=30)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['section', 'name'],
            },
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='catalog_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stocked_as', to='inventory.catalogitem'),
        ),
        migrations.CreateModel(
            name='CatalogSection',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('doc', models.CharField(choices=[('MAGGAM', 'Maggam / Aari / Zardosi materials'), ('APPAREL', 'Apparel ecosystem checklist')], db_index=True, max_length=20)),
                ('sequence', models.PositiveIntegerField()),
                ('name', models.CharField(max_length=150)),
                ('subsection', models.CharField(blank=True, max_length=150, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['doc', 'sequence', 'subsection'],
                'constraints': [models.UniqueConstraint(fields=('doc', 'name', 'subsection'), name='uniq_catalog_section')],
            },
        ),
        migrations.AddField(
            model_name='catalogitem',
            name='section',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='inventory.catalogsection'),
        ),
        migrations.AddIndex(
            model_name='catalogitem',
            index=models.Index(fields=['item_type', 'is_active'], name='inventory_c_item_ty_44958d_idx'),
        ),
        migrations.AddConstraint(
            model_name='catalogitem',
            constraint=models.UniqueConstraint(fields=('section', 'name'), name='uniq_catalog_item'),
        ),
    ]
