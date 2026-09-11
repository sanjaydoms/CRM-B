"""Garment, section, slot and accessory vocabulary for the fabric catalogue.

One source of truth: the API serves this to the browser, and the serializer
validates against it. Garment keys are GarmentTemplate.key values.
"""

KINDS = {
    'FABRIC': {'label': 'Fabric', 'accessory': False},
    'LINING': {'label': 'Lining', 'accessory': False},
    'BACKING': {'label': 'Backing Fabric', 'accessory': False},
    'CANCAN': {'label': 'Can-Can', 'accessory': False},
    'DORI': {
        'label': 'Dori',
        'accessory': True,
        'variant_label': 'Dori Type',
        'variants': {
            'LATKAN_DORI': 'Latkan Dori',
            'FABRIC_FLOWER_DORI': 'Fabric Flower Dori',
            'POTLI_DORI': 'Potli Dori',
            'OTHER_DORI': 'Other Dori',
        },
    },
    'TASSEL': {'label': 'Tassel / Latkan', 'accessory': True},
    'BORDER': {'label': 'Border', 'accessory': True},
    'LACE': {'label': 'Lace / Trim', 'accessory': True},
    'GOTA': {'label': 'Gota', 'accessory': True},
    'KIRAN': {'label': 'Kiran', 'accessory': True},
    'BUTTON': {'label': 'Buttons', 'accessory': True},
    'ZIPPER': {'label': 'Zipper', 'accessory': True},
    'HOOK': {'label': 'Hooks', 'accessory': True},
    'ELASTIC': {'label': 'Elastic / Drawstring', 'accessory': True},
    'PADDING': {'label': 'Padding / Cups', 'accessory': True},
    'BONING': {'label': 'Boning', 'accessory': True},
    'HORSEHAIR': {'label': 'Horsehair Braid', 'accessory': True},
    'SHOULDER_PADS': {'label': 'Shoulder Pads', 'accessory': True},
    'MOTIF': {'label': 'Decorative Motifs', 'accessory': True},
    'OTHER': {'label': 'Other', 'accessory': True},
}

ACCESSORY_KINDS = [key for key, spec in KINDS.items() if spec['accessory']]

SLOTS = {
    'MAIN_FABRIC': 'Main Fabric / Body',
    'SAREE_BODY': 'Main Fabric / Saree Body',
    'PALLU': 'Pallu',
    'PLEAT': 'Pleat / Pleats',
    'FALL': 'Fall',
    'LINING': 'Lining',
    'BACKING_FABRIC': 'Backing',
    'BORDER': 'Border',
    'DORI': 'Dori',
    'DRAWSTRING_DORI': 'Drawstring / Dori',
    'DORI_DRAWSTRING': 'Dori / Drawstring',
    'TASSEL_LATKAN': 'Tassel / Latkan',
    'LACE_TRIM': 'Lace / Trim',
    'LACE_GOTA_KIRAN': 'Lace / Gota / Kiran',
    'PADDING_CUPS': 'Padding / Cups',
    'HOOKS_ZIPPER': 'Hooks / Zipper',
    'ZIPPER_HOOKS': 'Zipper / Hooks',
    'HOOKS': 'Hooks',
    'BUTTONS': 'Buttons',
    'FLAIR': 'Flair',
    'CAN_CAN': 'Can-Can',
    'WAISTBAND': 'Waistband',
}

_BLOUSE = ['MAIN_FABRIC', 'LINING', 'BACKING_FABRIC', 'BORDER', 'DORI',
           'PADDING_CUPS', 'HOOKS_ZIPPER', 'LACE_TRIM']

_DUPATTA = ['MAIN_FABRIC', 'BACKING_FABRIC', 'BORDER', 'TASSEL_LATKAN',
            'LACE_GOTA_KIRAN']

GARMENTS = {
    'saree': {
        'label': 'Saree',
        'section_label': None,
        'sections': {'': ['SAREE_BODY', 'PALLU', 'BORDER', 'FALL', 'BACKING_FABRIC']},
    },
    'blouse': {
        'label': 'Blouse',
        'section_label': None,
        'sections': {'': _BLOUSE},
    },
    'lehenga': {
        'label': 'Lehenga',
        'section_label': 'Lehenga Section',
        'sections': {
            'BLOUSE': _BLOUSE,
            'SKIRT': ['MAIN_FABRIC', 'LINING', 'BACKING_FABRIC', 'BORDER',
                      'FLAIR', 'WAISTBAND', 'CAN_CAN', 'ZIPPER_HOOKS'],
            'DUPATTA': _DUPATTA,
        },
        'section_labels': {'BLOUSE': 'Blouse', 'SKIRT': 'Skirt',
                           'DUPATTA': 'Dupatta'},
    },
    'lehenga_blouse': {
        'label': 'Lehenga Blouse',
        'section_label': None,
        'sections': {'': _BLOUSE},
    },
    'dupatta': {
        'label': 'Dupatta',
        'section_label': None,
        'sections': {'': _DUPATTA},
    },
    'kurti': {
        'label': 'Kurti',
        'section_label': None,
        'sections': {'': ['MAIN_FABRIC', 'BACKING_FABRIC', 'BORDER']},
    },
    'anarkali': {
        'label': 'Anarkali',
        'section_label': None,
        'sections': {'': ['MAIN_FABRIC', 'LINING', 'BACKING_FABRIC', 'BORDER', 'WAISTBAND']},
    },
    'petticoat': {
        'label': 'Petticoat',
        'section_label': None,
        'sections': {'': ['MAIN_FABRIC', 'LINING', 'BACKING_FABRIC', 'WAISTBAND', 'BORDER']},
    },
    'bottom_wear': {
        'label': 'Bottom Wear',
        'section_label': None,
        'sections': {'': ['MAIN_FABRIC', 'LINING', 'BACKING_FABRIC', 'WAISTBAND', 'BORDER']},
    },
    'gown': {
        'label': 'Gown',
        'section_label': None,
        'sections': {'': ['MAIN_FABRIC', 'BACKING_FABRIC', 'BORDER']},
    },
    'suit': {
        'label': 'Suit (Kameez)',
        'section_label': None,
        'sections': {'': ['MAIN_FABRIC', 'LINING', 'BACKING_FABRIC', 'BORDER', 'WAISTBAND']},
    },
    'sherwani': {
        'label': 'Sherwani',
        'section_label': None,
        'sections': {'': ['MAIN_FABRIC', 'LINING', 'BACKING_FABRIC', 'BORDER', 'WAISTBAND']},
    },
}


class TaxonomyError(ValueError):
    """An identifier the taxonomy does not contain."""


def kind_label(kind):
    spec = KINDS.get(kind or '')
    return spec['label'] if spec else ''


def variant_label(kind, variant):
    return (KINDS.get(kind or '', {}).get('variants') or {}).get(variant or '', '')


def is_accessory(kind):
    return bool(KINDS.get(kind or '', {}).get('accessory'))


def validate_kind(kind, variant):
    """Return the cleaned (kind, variant). Blank kind means unclassified."""
    kind = (kind or '').strip()
    variant = (variant or '').strip()

    if not kind:
        if variant:
            raise TaxonomyError('A material type is required before a variant.')
        return '', ''

    spec = KINDS.get(kind)
    if spec is None:
        raise TaxonomyError(f"'{kind}' is not a material type.")

    variants = spec.get('variants') or {}
    if variant and variant not in variants:
        raise TaxonomyError(
            f"'{variant}' is not a {spec['label'].lower()} type."
            if variants else
            f"{spec['label']} has no variants.")
    return kind, variant


def validate_placement(garment, section, slot):
    """Return the cleaned (garment, section, slot).

    A blank section or slot widens the placement rather than narrowing it:
    garment alone means the material may be used anywhere on that garment.
    The slot is checked against the section it is claimed for, so a Skirt
    component cannot be filed under the Blouse -- but no rule here compares
    the material's own kind against the slot, because the same roll is
    legitimately a main fabric on one garment and a backing on another.
    """
    garment = (garment or '').strip()
    section = (section or '').strip()
    slot = (slot or '').strip()

    spec = GARMENTS.get(garment)
    if spec is None:
        raise TaxonomyError(f"'{garment}' is not a garment.")

    sections = spec['sections']
    if section and section not in sections:
        raise TaxonomyError(f"'{section}' is not a section of {spec['label']}.")
    if not section and spec['section_label'] and slot:
        raise TaxonomyError(
            f"{spec['label']} needs a section before a component.")

    if slot:
        allowed = sections.get(section) if section else {
            key for keys in sections.values() for key in keys}
        if slot not in allowed:
            where = f"{spec['label']} {section.title()}" if section else spec['label']
            raise TaxonomyError(f"'{slot}' is not a component of {where}.")

    return garment, section, slot


def placement_path(garment, section, slot):
    spec = GARMENTS.get(garment or '')
    if spec is None:
        return ' / '.join(p for p in (garment, section, slot) if p)
    parts = [spec['label']]
    if section:
        parts.append((spec.get('section_labels') or {}).get(section, section.title()))
    if slot:
        parts.append(SLOTS.get(slot, slot))
    return ' / '.join(parts)


def tree():
    return {
        'kinds': [
            {
                'key': key,
                'label': spec['label'],
                'accessory': spec['accessory'],
                'variant_label': spec.get('variant_label', ''),
                'variants': [{'key': v, 'label': label}
                             for v, label in (spec.get('variants') or {}).items()],
            }
            for key, spec in KINDS.items()
        ],
        'slots': [{'key': key, 'label': label} for key, label in SLOTS.items()],
        'garments': [
            {
                'key': key,
                'label': spec['label'],
                'section_label': spec['section_label'] or '',
                'sections': [
                    {
                        'key': section,
                        'label': (spec.get('section_labels') or {}).get(
                            section, section.title()),
                        'slots': [{'key': s, 'label': SLOTS.get(s, s)} for s in slots],
                    }
                    for section, slots in spec['sections'].items()
                ],
            }
            for key, spec in GARMENTS.items()
        ],
    }
