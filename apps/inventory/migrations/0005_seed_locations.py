
from django.db import migrations

LOCATIONS = [
    ('Main Store', 'MAIN_STORE', 1),
    ('Warehouse', 'WAREHOUSE', 2),
    ('Workshop', 'WORKSHOP', 3),
    ('Cutting Unit', 'CUTTING_UNIT', 4),
    ('Embroidery Unit', 'EMBROIDERY_UNIT', 5),
    ('Tailor / Master', 'TAILOR', 6),
    ('Finishing Unit', 'FINISHING_UNIT', 7),
    ('Showroom', 'SHOWROOM', 8),
]


def seed(apps, schema_editor):
    StockLocation = apps.get_model('inventory', 'StockLocation')
    LocationStock = apps.get_model('inventory', 'LocationStock')
    InventoryItem = apps.get_model('inventory', 'InventoryItem')

    for name, kind, sequence in LOCATIONS:
        StockLocation.objects.get_or_create(
            name=name,
            defaults={'kind': kind, 'sequence': sequence, 'is_default': kind == 'MAIN_STORE'},
        )

    main_store = StockLocation.objects.filter(is_default=True).first()
    if main_store is None:
        return
    for item in InventoryItem.objects.exclude(current_stock=0):
        LocationStock.objects.get_or_create(
            item=item, location=main_store, defaults={'quantity': item.current_stock},
        )


def unseed(apps, schema_editor):
    apps.get_model('inventory', 'LocationStock').objects.all().delete()
    apps.get_model('inventory', 'StockLocation').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [('inventory', '0004_alter_stockmovement_movement_type_stocklocation_and_more')]

    operations = [migrations.RunPython(seed, unseed)]
