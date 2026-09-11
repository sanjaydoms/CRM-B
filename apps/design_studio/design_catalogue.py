"""The design catalogue: garment -> category -> (sub-category ->) design option.

One source of truth, the way `crm_api.fabric_taxonomy` is for fabrics: the API
serves this tree to the browser, and the serializer validates an upload's
catalogue path against it. Garment keys are GarmentTemplate.key values, so the
catalogue for a garment is found the same way everything else about it is.

A category is one DIMENSION of the garment -- what it is, what it is made of,
where it comes from, what is worked on it, the occasion, how it is draped --
and the dimensions are deliberately kept apart. The same name recurring in two
of them ("Ruffle Saree" as a fashion design and as a party saree) is two
positions, addressed by their full path, not one entry to be de-duplicated.

Keys are slugs of the labels, unique within their own category or
sub-category. They are what an uploaded design stores; the labels are what
the boutique reads.

Adding a garment is adding a top-level entry here. Nothing else changes.
"""

import re


def _slug(label):
    return re.sub(r'[^a-z0-9]+', '_', str(label).lower()).strip('_')


def _options(*labels):
    """Labels in, [{"key", "label"}] out, in the order given. A label that
    repeats within one list would collide on key; the catalogue is written so
    that never happens, and this makes it an error rather than a silent loss."""
    out, seen = [], set()
    for label in labels:
        key = _slug(label)
        if key in seen:
            raise ValueError(f'duplicate design option in one list: {label!r}')
        seen.add(key)
        out.append({'key': key, 'label': label})
    return out


def _category(label, short=None, options=None, subcategories=None, note=''):
    cat = {'key': _slug(label), 'label': label, 'short': short or label}
    if note:
        cat['note'] = note
    if subcategories is not None:
        cat['subcategories'] = [
            {'key': _slug(sub_label), 'label': sub_label, 'options': _options(*sub_options)}
            for sub_label, sub_options in subcategories
        ]
    else:
        cat['options'] = _options(*(options or ()))
    return cat


# --------------------------------------------------------------------------
# SAREE
# --------------------------------------------------------------------------

_SAREE_CATEGORIES = [
    _category(
        'Contemporary / Fashion Saree Designs', short='Contemporary / Fashion',
        options=[
            'Ruffle Saree', 'Dhoti Saree', 'Pre-Draped Saree', 'Pant Saree', 'Saree Gown',
            'Lehenga Saree', 'Half-Saree Style', 'Concept Saree', 'Belted Saree', 'Cape Saree',
            'Jacket Saree', 'Co-ord Saree', 'Skirt Saree', 'Trouser Saree', 'Dhoti-Pant Saree',
            'Draped Saree', 'Layered Saree', 'Double-Drape Saree', 'Front-Pallu Saree',
            'Side-Drape Saree', 'Scarf-Style Saree', 'Cowl-Drape Saree', 'Mermaid Saree',
            'Fish-Cut Saree', 'Tulip Saree', 'Asymmetric Saree', 'Pre-Pleated Saree',
            'Ready-to-Wear Saree', 'Easy-Drape Saree', 'Saree with Attached Pallu',
            'Saree with Attached Petticoat',
        ]),
    _category(
        'Traditional Indian Saree Types', short='Traditional Indian',
        subcategories=[
            ('Silk / Pattu', [
                'Kanjeevaram / Kanchipuram Pattu', 'Banarasi Silk', 'Mysore Silk', 'Uppada Silk',
                'Gadwal Silk', 'Dharmavaram Silk', 'Pochampally Silk', 'Chettinad Silk',
                'Konrad Silk', 'Tussar Silk', 'Matka Silk', 'Raw Silk', 'Organza Silk',
                'Chanderi Silk', 'Maheshwari Silk', 'Paithani', 'Ilkal Saree', 'Muga Silk',
                'Assam Silk', 'Baluchari', 'Murshidabad Silk',
            ]),
            ('Cotton', [
                'Mangalagiri Cotton', 'Kalamkari Cotton', 'Chettinad Cotton', 'Bengal Cotton',
                'Tant Saree', 'Kota Cotton', 'Kota Doria', 'Chanderi Cotton', 'Maheshwari Cotton',
                'Mulmul Cotton', 'Handloom Cotton', 'Venkatagiri Cotton', 'Narayanpet Cotton',
                'Sambalpuri Cotton',
            ]),
        ]),
    _category(
        'Regional / Heritage Sarees', short='Regional / Heritage',
        subcategories=[
            ('Telangana & Andhra', [
                'Pochampally Ikat', 'Gadwal', 'Narayanpet', 'Uppada', 'Dharmavaram', 'Mangalagiri',
                'Venkatagiri', 'Kalamkari Saree', 'Siddipet Gollabhama Saree',
            ]),
            ('Tamil Nadu', [
                'Kanjeevaram', 'Chettinad', 'Madurai Sungudi', 'Coimbatore Cotton', 'Arani Silk',
                'Dharmavaram-style Silk',
            ]),
            ('Karnataka', ['Mysore Silk', 'Ilkal', 'Molakalmuru', 'Karnataka Cotton']),
            ('Maharashtra', ['Paithani', 'Narayan Peth', 'Kolhapuri Saree']),
            ('Gujarat', ['Patola', 'Bandhani', 'Gharchola', 'Ajrakh Saree', 'Mashru-inspired Sarees']),
            ('Rajasthan', ['Bandhani', 'Leheriya', 'Kota Doria', 'Bagru-inspired Sarees']),
            ('West Bengal', [
                'Tant', 'Jamdani', 'Garad', 'Baluchari', 'Dhakai Jamdani', 'Tussar', 'Kantha Saree',
            ]),
            ('Odisha', ['Sambalpuri', 'Bomkai', 'Berhampuri', 'Khandua', 'Pasapalli']),
            ('Kerala', ['Kasavu', 'Kerala Cotton', 'Set Mundu-inspired Saree']),
            ('Assam', ['Muga Silk', 'Mekhela Chador', 'Assam Silk']),
        ]),
    _category(
        'Fabric-Based Saree Designs', short='Fabric-Based',
        options=[
            'Silk Saree', 'Cotton Saree', 'Linen Saree', 'Chiffon Saree', 'Georgette Saree',
            'Crepe Saree', 'Organza Saree', 'Net Saree', 'Satin Saree', 'Velvet Saree',
            'Tissue Saree', 'Modal Silk Saree', 'Art Silk Saree', 'Raw Silk Saree', 'Tussar Saree',
            'Muslin Saree', 'Rayon Saree', 'Viscose Saree', 'Chanderi Saree', 'Kota Doria',
            'Handloom Saree', 'Khadi Saree', 'Denim Saree', 'Faux Georgette',
        ]),
    _category(
        'Embroidery / Surface Design Sarees', short='Embroidery / Surface Design',
        options=[
            'Zari Saree', 'Zardozi Saree', 'Aari Work Saree', 'Chikankari Saree', 'Kantha Saree',
            'Phulkari Saree', 'Mirror Work Saree', 'Sequin Saree', 'Cutdana Saree',
            'Beadwork Saree', 'Pearl Work Saree', 'Resham Work Saree', 'Thread Embroidery Saree',
            'Appliqué Saree', 'Patchwork Saree', 'Stone Work Saree', 'Crystal Work Saree',
            'Gota Patti Saree', 'Dabka Work Saree', 'Kasab Work Saree', 'Mukaish Saree',
        ]),
    _category(
        'Print / Weave-Based Designs', short='Print / Weave',
        options=[
            'Floral Print Saree', 'Digital Print Saree', 'Abstract Print Saree',
            'Geometric Print Saree', 'Animal Print Saree', 'Paisley Print Saree',
            'Kalamkari Saree', 'Ajrakh Saree', 'Block Print Saree', 'Bagru Print Saree',
            'Dabu Print Saree', 'Ikat Saree', 'Bandhani Saree', 'Leheriya Saree', 'Shibori Saree',
            'Tie-Dye Saree', 'Jamdani Saree', 'Chikankari Saree', 'Woven Saree', 'Brocade Saree',
            'Jacquard Saree', 'Striped Saree', 'Checked Saree', 'Polka Dot Saree',
        ]),
    _category(
        'Occasion-Based Sarees', short='Occasion',
        subcategories=[
            ('Wedding', [
                'Bridal Silk Saree', 'Kanjeevaram Bridal Saree', 'Banarasi Bridal Saree',
                'Paithani Bridal Saree', 'Bridal Designer Saree', 'Heavy Zari Saree',
            ]),
            ('Party', [
                'Sequin Saree', 'Shimmer Saree', 'Metallic Saree', 'Pre-Draped Saree',
                'Ruffle Saree', 'Organza Saree', 'Satin Saree', 'Crystal Saree',
            ]),
            ('Office', [
                'Linen Saree', 'Cotton Saree', 'Handloom Saree', 'Chanderi Saree',
                'Minimal Silk Saree',
            ]),
            ('Festive', [
                'Pattu Saree', 'Banarasi', 'Paithani', 'Gadwal', 'Pochampally', 'Bandhani', 'Kasavu',
            ]),
            ('Cocktail / Modern', [
                'Pant Saree', 'Dhoti Saree', 'Saree Gown', 'Ruffle Saree', 'Belted Saree',
                'Cape Saree', 'Jacket Saree',
            ]),
        ]),
    _category(
        'Draping Styles', short='Draping Styles',
        note='Ways of draping a saree, not separate saree products.',
        options=[
            'Nivi Draping', 'Bengali Draping', 'Gujarati Draping', 'Maharashtrian / Nauvari Draping',
            'Tamilian Draping', 'Kodagu Draping', 'Kerala Draping', 'Madisaru Draping',
            'Coorgi Draping', 'Assamese Draping', 'Atpourey Draping', 'Nauvari Dhoti Draping',
            'Seedha Pallu', 'Ulta Pallu', 'Front Pallu', 'Open Pallu', 'Pleated Pallu',
            'Belted Draping', 'Dhoti Draping', 'Pant Draping',
        ]),
    _category(
        'Special / Modern Saree Constructions', short='Special / Modern',
        options=[
            'Pre-Pleated Saree', 'Pre-Stitched Saree', 'Pre-Draped Saree', 'Ready-to-Wear Saree',
            'Saree with Skirt', 'Saree with Pants', 'Saree with Petticoat', 'Saree with Shapewear',
            'Saree with Built-in Shapewear', 'Saree with Belt', 'Saree with Jacket',
            'Saree with Cape', 'Saree with Blazer', 'Saree with Corset Blouse',
            'Saree with Crop Top', 'Saree with Peplum Blouse', 'Saree with Shirt',
            'Saree with Long Jacket', 'Saree with Detachable Pallu',
        ]),
    # The blouse is a component of the saree catalogue, not another garment.
    # Its dimensions are declared so the shape is settled and a design can
    # already be filed under one; the options within each arrive with the
    # blouse catalogue and are added here, nothing else changing.
    _category(
        'Blouse', short='Blouse',
        note='Blouse design options will be added per dimension.',
        subcategories=[
            ('Neck design', []), ('Sleeve design', []), ('Back design', []), ('Front design', []),
            ('Collar', []), ('Cuff', []), ('Blouse silhouette', []), ('Blouse construction', []),
            ('Blouse embellishment', []),
        ]),
    _category(
        'Petticoat', short='Petticoat',
        options=[
            'Regular Petticoat', 'Mermaid Petticoat', 'Fish-Cut Petticoat', 'Shapewear Petticoat',
            'Can-Can Petticoat',
        ]),
]

CATALOGUE = {
    'saree': {'key': 'saree', 'label': 'Saree', 'categories': _SAREE_CATEGORIES},
}


# --------------------------------------------------------------------------
# reading and checking
# --------------------------------------------------------------------------

class CatalogueError(ValueError):
    pass


def tree(garment_key=None):
    """The catalogue for one garment, or every garment that has one."""
    if garment_key is None:
        return list(CATALOGUE.values())
    return CATALOGUE.get(garment_key)


def resolve_path(garment_key, category, subcategory='', option=''):
    """Check a path exists and return it with its labels filled in.

    An option is required wherever the category (or sub-category) declares
    any; where none are declared yet -- the blouse dimensions, until their
    catalogue arrives -- a design may be filed at that level.
    """
    garment = CATALOGUE.get(garment_key or '')
    if garment is None:
        raise CatalogueError(f'No design catalogue is defined for garment {garment_key!r}.')
    cat = next((c for c in garment['categories'] if c['key'] == category), None)
    if cat is None:
        raise CatalogueError(f'{garment["label"]} has no catalogue category {category!r}.')

    path = {'garment': garment_key, 'category': cat['key'], 'category_label': cat['label'],
            'subcategory': '', 'subcategory_label': '', 'option': '', 'option_label': ''}

    if 'subcategories' in cat:
        sub = next((s for s in cat['subcategories'] if s['key'] == subcategory), None)
        if sub is None:
            raise CatalogueError(f'{cat["label"]} needs one of its sub-categories.')
        path.update(subcategory=sub['key'], subcategory_label=sub['label'])
        options = sub['options']
    else:
        if subcategory:
            raise CatalogueError(f'{cat["label"]} has no sub-categories.')
        options = cat['options']

    if options:
        opt = next((o for o in options if o['key'] == option), None)
        if opt is None:
            raise CatalogueError('Choose a design option from the list.')
        path.update(option=opt['key'], option_label=opt['label'])
    elif option:
        raise CatalogueError('This section has no design options yet.')

    path['path'] = ' › '.join(p for p in (
        path['category_label'], path['subcategory_label'], path['option_label']) if p)
    return path
