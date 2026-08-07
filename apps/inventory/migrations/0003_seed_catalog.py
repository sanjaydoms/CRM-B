"""Load the published inventory catalogue.

A data migration rather than a fixture, so a redeploy re-syncs the catalogue
into every tenant schema while leaving each boutique's own stock rows alone.
"""

from django.db import migrations

from apps.inventory.catalog_sync import sync_catalog


def seed(apps, schema_editor):
    sync_catalog({
        'CatalogSection': apps.get_model('inventory', 'CatalogSection'),
        'CatalogItem': apps.get_model('inventory', 'CatalogItem'),
    })


def unseed(apps, schema_editor):
    # Stock rows survive: InventoryItem.catalog_item is SET_NULL.
    apps.get_model('inventory', 'CatalogSection').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [('inventory', '0002_catalogitem_inventoryitem_catalog_item_and_more')]

    operations = [migrations.RunPython(seed, unseed)]
