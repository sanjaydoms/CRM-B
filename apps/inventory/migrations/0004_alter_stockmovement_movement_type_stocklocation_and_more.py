
import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm_api', '0020_boutiquesettings_design_approval_required'),
        ('inventory', '0003_seed_catalog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stockmovement',
            name='movement_type',
            field=models.CharField(choices=[('PURCHASE', 'Purchase'), ('GOODS_RECEIPT', 'Goods Receipt'), ('STOCK_IN', 'Stock In'), ('RESERVATION', 'Reservation'), ('RELEASE', 'Reservation Released'), ('ISSUE', 'Issued to Production'), ('CONSUMPTION', 'Consumed'), ('RETURN', 'Return to Stock'), ('TRANSFER', 'Transfer'), ('DAMAGE', 'Damaged'), ('WASTE', 'Waste'), ('ADJUSTMENT', 'Adjustment'), ('SCRAP', 'Scrapped'), ('CUSTOMER_RETURN', 'Customer Return'), ('SUPPLIER_RETURN', 'Supplier Return')], db_index=True, max_length=20),
        ),
        migrations.CreateModel(
            name='StockLocation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('kind', models.CharField(choices=[('MAIN_STORE', 'Main Store'), ('WAREHOUSE', 'Warehouse'), ('WORKSHOP', 'Workshop'), ('CUTTING_UNIT', 'Cutting Unit'), ('EMBROIDERY_UNIT', 'Embroidery Unit'), ('TAILOR', 'Tailor / Master'), ('FINISHING_UNIT', 'Finishing Unit'), ('SHOWROOM', 'Showroom')], db_index=True, max_length=30)),
                ('is_default', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sequence', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tailor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_locations', to='crm_api.tailor')),
            ],
            options={
                'ordering': ['sequence', 'name'],
            },
        ),
        migrations.CreateModel(
            name='LocationStock',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('quantity', models.DecimalField(decimal_places=3, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='location_stocks', to='inventory.inventoryitem')),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stocks', to='inventory.stocklocation')),
            ],
            options={
                'ordering': ['location__sequence'],
            },
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='from_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movements_out', to='inventory.stocklocation'),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='to_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movements_in', to='inventory.stocklocation'),
        ),
        migrations.AddConstraint(
            model_name='stocklocation',
            constraint=models.UniqueConstraint(fields=('name',), name='uniq_stock_location_name'),
        ),
        migrations.AddConstraint(
            model_name='stocklocation',
            constraint=models.UniqueConstraint(condition=models.Q(('is_default', True)), fields=('is_default',), name='one_default_stock_location'),
        ),
        migrations.AddConstraint(
            model_name='locationstock',
            constraint=models.UniqueConstraint(fields=('item', 'location'), name='uniq_item_location_stock'),
        ),
    ]
