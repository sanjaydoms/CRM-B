
from django.db import transaction

from .catalog_definitions import CATALOG
from .models import Category, ItemType

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
