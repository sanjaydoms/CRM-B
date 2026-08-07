"""Loading the published catalogue into a tenant's database.

Mirrors apps.catalog.services.sync_global_templates: a data migration passes in
its historical models so old migrations stay replayable, and the function is
safe to run repeatedly so a redeploy re-syncs rather than duplicating.

Only catalogue rows are touched. An InventoryItem the boutique has created from
a catalogue row is its own record and is never rewritten from here.
"""

from django.db import transaction

from .catalog_definitions import CATALOG
from .models import Category, ItemType

#: Which of the eight legacy categories a section's items belong to. The legacy
#: field stays because existing rows, screens and the garment templates in
#: apps.catalog all key on it; this is the bridge, not a replacement for the
#: section, which is what actually preserves the source taxonomy.
_LEGACY_BY_SECTION = {
    'Base Fabrics': Category.FABRIC,
    'Fabrics': Category.FABRIC,
    'Embroidery Threads': Category.MAGGAM,
    'Needles': Category.MAGGAM,
    'Frames': Category.MAGGAM,
    'Beads': Category.MAGGAM,
    'Stones': Category.MAGGAM,
    'Sequins': Category.MAGGAM,
    'Mirrors': Category.MAGGAM,
    'Traditional Zardosi Materials': Category.MAGGAM,
    'Laces & Borders': Category.BORDER,
    'Appliqué Materials': Category.MAGGAM,
    'Cords & Decorative Elements': Category.MAGGAM,
    'Backing & Support Materials': Category.LINING,
    'Adhesives': Category.MAGGAM,
    'Marking Tools': Category.OTHER,
    'Cutting Tools': Category.OTHER,
    'Measuring Tools': Category.OTHER,
    'Finishing Materials': Category.OTHER,
    'Decorative Embellishments': Category.EMBELLISHMENT,
    'Modern Luxury Embellishments': Category.EMBELLISHMENT,
    'Specialty Materials': Category.EMBELLISHMENT,
    'Tools & Accessories': Category.OTHER,
    'Product Planning & Design': Category.OTHER,
    'Interlining & Support': Category.LINING,
    'Sewing Threads': Category.STITCHING,
    'Buttons': Category.STITCHING,
    'Zippers': Category.STITCHING,
    'Elastics': Category.STITCHING,
    'Labels & Branding': Category.PACKAGING,
    'Decorative Materials': Category.EMBELLISHMENT,
    'Maggam / Hand Embroidery Materials': Category.MAGGAM,
    'Printing Materials': Category.OTHER,
    'Garment Accessories': Category.STITCHING,
    'Pattern Making Tools': Category.OTHER,
    'Cutting Room': Category.OTHER,
    'Sewing Machines': Category.OTHER,
    'Finishing': Category.OTHER,
    'Quality Control': Category.OTHER,
    'Packaging': Category.PACKAGING,
    'Warehouse': Category.OTHER,
    'Retail Store': Category.OTHER,
    'E-commerce': Category.OTHER,
    'Logistics': Category.PACKAGING,
    "Women's Clothing Categories": Category.OTHER,
    "Men's Clothing Categories": Category.OTHER,
    "Boys' Clothing": Category.OTHER,
    "Girls' Clothing": Category.OTHER,
    'Customer Delivery': Category.PACKAGING,
}


@transaction.atomic
def sync_catalog(models=None):
    """Create or update every published section and item. Returns a count dict."""
    if models is None:
        from . import models as live
        models = {'CatalogSection': live.CatalogSection, 'CatalogItem': live.CatalogItem}

    Section = models['CatalogSection']
    Item = models['CatalogItem']

    sections = items = 0
    for group in CATALOG:
        section, made = Section.objects.get_or_create(
            doc=group['doc'], name=group['section'], subsection=group['subsection'],
            defaults={'sequence': group['sequence']},
        )
        if made:
            sections += 1
        elif section.sequence != group['sequence']:
            section.sequence = group['sequence']
            section.save(update_fields=['sequence'])

        legacy = _LEGACY_BY_SECTION.get(group['section'], Category.OTHER)
        for name, item_type, unit in group['items']:
            _, made = Item.objects.get_or_create(
                section=section, name=name,
                defaults={
                    'item_type': item_type,
                    'default_unit': unit,
                    'legacy_category': legacy,
                },
            )
            if made:
                items += 1

    return {'sections': sections, 'items': items}
