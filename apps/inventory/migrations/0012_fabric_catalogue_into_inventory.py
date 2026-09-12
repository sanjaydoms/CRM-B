# The fabric catalogue (crm_api.BoutiqueFabric) becomes stock. Every roll the
# boutique catalogued is copied to an InventoryItem with its photographs,
# shade, taxonomy kind and garment-part placements, so the order wizard keeps
# picking from the same rolls and the ledger can finally count their metres.
#
# Quantities start at zero: the catalogue never held any, and inventing an
# opening figure would be a lie the ledger then has to unpick. The owner
# records what is on the shelf with a Stock In. Price per metre is carried as
# both cost and selling price until corrected -- the catalogue only ever knew
# the one number.

from django.db import migrations

# Catalogue kind -> stock category, following the purchasing catalogue's own
# filing (apps/inventory/catalog_sync.py). Unclassified rolls are fabric.
KIND_TO_CATEGORY = {
    '': 'FABRIC', 'FABRIC': 'FABRIC',
    'LINING': 'LINING', 'BACKING': 'LINING', 'CANCAN': 'LINING',
    'BORDER': 'BORDER', 'LACE': 'BORDER', 'GOTA': 'BORDER', 'KIRAN': 'BORDER',
    'DORI': 'EMBELLISHMENT', 'TASSEL': 'EMBELLISHMENT', 'MOTIF': 'EMBELLISHMENT',
    'PADDING': 'EMBELLISHMENT', 'BONING': 'EMBELLISHMENT', 'HORSEHAIR': 'EMBELLISHMENT',
    'SHOULDER_PADS': 'EMBELLISHMENT',
    'BUTTON': 'STITCHING', 'ZIPPER': 'STITCHING', 'HOOK': 'STITCHING', 'ELASTIC': 'STITCHING',
    'OTHER': 'OTHER',
}
METRE_CATEGORIES = {'FABRIC', 'LINING', 'BORDER'}


def forwards(apps, schema_editor):
    BoutiqueFabric = apps.get_model('crm_api', 'BoutiqueFabric')
    InventoryItem = apps.get_model('inventory', 'InventoryItem')
    ItemPlacement = apps.get_model('inventory', 'ItemPlacement')

    taken = set(InventoryItem.objects.values_list('item_code', flat=True))
    counter = 0

    def next_code():
        nonlocal counter
        while True:
            counter += 1
            code = f'FAB-{counter:04d}'
            if code not in taken:
                taken.add(code)
                return code

    for fabric in BoutiqueFabric.objects.order_by('id').prefetch_related('placements'):
        if InventoryItem.objects.filter(legacy_fabric_id=fabric.id).exists():
            continue
        category = KIND_TO_CATEGORY.get(fabric.kind or '', 'OTHER')
        item = InventoryItem.objects.create(
            item_code=next_code(),
            name=fabric.name[:200],
            category=category,
            material_type=(fabric.material or '')[:100] or None,
            color=(fabric.color or '')[:50] or None,
            color_hex=fabric.color_hex or '',
            unit='METER' if category in METRE_CATEGORIES else 'PIECE',
            purchase_price=fabric.price_per_meter,
            selling_price=fabric.price_per_meter,
            image_url=(fabric.image_url or '')[:500],
            image_urls=list(fabric.image_urls or []),
            kind=fabric.kind or '',
            variant=fabric.variant or '',
            status='ACTIVE' if fabric.is_available else 'INACTIVE',
            legacy_fabric_id=fabric.id,
        )
        ItemPlacement.objects.bulk_create([
            ItemPlacement(item=item, garment=p.garment, section=p.section, slot=p.slot,
                          image_urls=list(p.image_urls or []))
            for p in fabric.placements.all()
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0011_item_catalogue_fields'),
        ('crm_api', '0042_orderstage_verification_note'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
