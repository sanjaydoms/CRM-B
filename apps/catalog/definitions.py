"""The garments the boutique stitches, as data.

This is the source the seed migration loads. Editing a template here and bumping
its version updates every boutique still on the global default; a boutique that
has customised the garment keeps its own row (see GarmentTemplate.resolve).

Options are written as plain labels and slugged into values, except where a tuple
gives the value explicitly -- sizes like 11" cannot be slugged sensibly.
"""

import re

from apps.inventory.models import Category as Inv


def _slug(label):
    return re.sub(r'[^a-z0-9]+', '_', str(label).lower()).strip('_')


def field(key, label, field_type, **kw):
    """One template field. `options` accepts labels or (value, label) pairs."""
    options = kw.pop('options', None)
    return {
        'key': key,
        'label': label,
        'field_type': field_type,
        'unit': kw.pop('unit', None),
        'is_required': kw.pop('required', False),
        'is_repeatable': kw.pop('repeatable', False),
        'default': kw.pop('default', None),
        'help_text': kw.pop('help_text', None),
        'visible_when': kw.pop('when', None),
        'validation': kw.pop('validation', {}),
        'inventory_category': kw.pop('inventory', None),
        'options': [
            o if isinstance(o, tuple) else (_slug(o), o) for o in (options or [])
        ],
    }


def measurement(key, label, **kw):
    """Body and garment dimensions share one range: 0-120 inches, quarter inch."""
    kw.setdefault('validation', {'min': 0, 'max': 120, 'step': 0.25})
    return field(key, label, 'number', unit='in', **kw)


def material(key, label, category, **kw):
    return field(key, label, 'inventory_ref', inventory=category, **kw)


def eq(f, v):
    return {'field': f, 'op': 'eq', 'value': v}


def neq(f, v):
    return {'field': f, 'op': 'neq', 'value': v}


def one_of(f, values):
    return {'field': f, 'op': 'in', 'value': values}


def all_of(*rules):
    return {'all': list(rules)}


def not_one_of(f, values):
    return {'field': f, 'op': 'not_in', 'value': values}


# --- fields shared by every garment ---------------------------------------
#
# Defined once and merged into every garment, so a change reaches every form
# at once. These keys are reserved: a garment cannot redefine them.

COMMON_BASIC = [
    field('occasion', 'Occasion', 'select', options=[
        'Wedding', 'Reception', 'Festive', 'Party', 'Daily', 'Other']),
    field('material_source', 'Material Source', 'select', options=[
        ('customer', 'Customer Provided Fabric'),
        ('store', 'Store Inventory Fabric'),
        ('mixed', 'Mixed')], default='store'),
    field('design_reference_source', 'Design Reference', 'select', options=[
        ('BOUTIQUE_CATALOG', 'Boutique Catalog'),
        ('PINTEREST', 'Pinterest Inspiration'),
        ('GOOGLE', 'Google Images'),
        ('CUSTOMER_SKETCH', 'Customer Sketch'),
        ('DESIGNER_SKETCH', 'Designer Sketch'),
        ('PREVIOUS_DESIGN', 'Previous Design')]),
    field('design_reference_links', 'Reference Links', 'text', repeatable=True),
    field('trial_required', 'Trial Required', 'boolean'),
    field('trial_date', 'Trial Date', 'date', when=eq('trial_required', True)),
    # Optional: a walk-in is often taken before a date is agreed, and blocking
    # the order on it pushed staff into typing a placeholder they never revisit.
    field('delivery_date', 'Delivery Date', 'date'),
    field('urgency', 'Urgency', 'select', options=['Normal', 'Express'], default='normal'),
    field('priority', 'Priority', 'select', options=['Low', 'Medium', 'High'], default='medium'),
]

COMMON_MATERIALS = [
    material('other_accessories', 'Other Accessories', Inv.OTHER, repeatable=True),
]

COMMON_PRODUCTION = [
    field('special_instructions', 'Special Instructions', 'textarea',
          validation={'max_length': 2000}),
    field('internal_notes', 'Internal Notes', 'textarea',
          help_text='Staff only — never shown on the customer copy.',
          validation={'max_length': 2000}),
    field('customer_notes', 'Customer Notes', 'textarea', validation={'max_length': 2000}),
    field('reference_images', 'Reference Images', 'file', repeatable=True),
    field('measurement_sheet', 'Measurement Sheet', 'file'),
    field('audio_note', 'Audio Note', 'file',
          help_text='Transcribed into the special instructions.'),
    field('final_approved_design', 'Final Approved Design', 'file'),
]


# --- reusable blocks -------------------------------------------------------
#
# Blouse and lehenga blouse deliberately share measurement and neck keys: the
# cutting sheet, the measurement history and "reuse last measurements" all work
# only because `armhole` means the same thing on both.

def blouse_measurements():
    return [
        measurement('blouse_length', 'Blouse Length'),
        measurement('shoulder', 'Shoulder'),
        measurement('upper_chest', 'Upper Chest'),
        measurement('chest', 'Chest'),
        measurement('waist', 'Waist'),
        measurement('armhole', 'Armhole'),
    ]


def sleeve_and_neck():
    return [
        field('sleeve_length', 'Sleeve Length', 'select', options=[
            'Sleeveless', 'Cap', 'Short', 'Elbow', ('three_quarter', '3/4'), 'Full']),
        field('hand_rounding', 'Hand Rounding', 'select',
              options=['HR1', 'HR2', 'HR3', 'HR4'],
              when=neq('sleeve_length', 'sleeveless')),
        field('front_neck', 'Front Neck', 'text'),
        field('back_neck', 'Back Neck', 'text'),
        field('collar', 'Collar', 'text'),
    ]


WAIST_FINISH = ['Belt', 'Elastic', 'Button', 'Dori']


def bottom_materials(extra=()):
    return [
        material('fabric', 'Fabric', Inv.FABRIC),
        *extra,
        material('elastic', 'Elastic', Inv.STITCHING, when=one_of('waist_finish', ['elastic'])),
        material('dori', 'Dori', Inv.STITCHING, when=one_of('waist_finish', ['dori'])),
    ]


# --- the garments ----------------------------------------------------------

TEMPLATES = [
    {
        'key': 'saree', 'name': 'Saree', 'sequence': 10,
        'sections': {
            'basic': [
                field('saree_type', 'Saree Type', 'select', required=True, options=[
                    'Silk', 'Cotton', 'Georgette', 'Chiffon', 'Linen', 'Organza',
                    'Tissue', 'Banarasi', 'Kanchipuram', 'Other']),
                field('saree_type_other', 'Specify Type', 'text',
                      when=eq('saree_type', 'other')),
                field('fabric_length', 'Fabric Length', 'number', unit='m',
                      validation={'min': 0, 'max': 20, 'step': 0.25}),
            ],
            'measurements': [
                measurement('petticoat_length', 'Petticoat Length',
                            when=eq('petticoat_required', True)),
                measurement('petticoat_waist', 'Petticoat Waist',
                            when=eq('petticoat_required', True)),
            ],
            'style': [
                field('services', 'Services Required', 'multiselect', required=True, options=[
                    'Stitching', 'Fall', 'Pico', ('fall_pico', 'Fall + Pico'),
                    'Tassel Work', 'Saree Finishing', ('polishing', 'Polishing / Steam')]),
                # Each option group belongs to a service. Asking about tassels
                # on a fall-and-pico job, or about the border when nothing is
                # being stitched, is a question with no answer -- so the group
                # appears only once the service that needs it is ticked.
                field('border', 'Border', 'select', options=[
                    ('with_border', 'With Border'), ('without_border', 'Without Border')],
                      when=one_of('services', ['stitching', 'saree_finishing'])),
                field('backing', 'Backing', 'select', options=[
                    ('with_backing', 'With Backing'), ('without_backing', 'Without Backing')],
                      when=one_of('services', ['stitching', 'saree_finishing'])),
                field('fall_type', 'Fall', 'select', options=['Big Fall', 'Small Fall'],
                      when=one_of('services', ['fall', 'fall_pico'])),
                field('pico_type', 'Pico', 'select', options=['Standard', 'Premium'],
                      when=one_of('services', ['pico', 'fall_pico'])),
                field('tassels', 'Tassels', 'select', options=[
                    'No Tassels', 'Hand Made', 'Readymade', 'Knot Style'],
                      when=one_of('services', ['tassel_work'])),
                field('petticoat_required', 'Petticoat Required', 'boolean',
                      when=one_of('services', ['stitching'])),
                field('petticoat_waist_finish', 'Petticoat Waist Finish', 'multiselect',
                      options=WAIST_FINISH, when=eq('petticoat_required', True)),
            ],
            'materials': [
                material('fabric_used', 'Fabric Used', Inv.FABRIC),
                material('border_used', 'Border Used', Inv.BORDER,
                         when=eq('border', 'with_border')),
                material('lining', 'Lining', Inv.LINING),
                material('fall_cloth', 'Fall Cloth', Inv.LINING,
                         when=one_of('services', ['fall', 'fall_pico'])),
                # neq is true for an unanswered field, so this needs the service
                # gate too -- otherwise the tassel material appeared on an order
                # with no tassel work on it at all.
                material('tassels_material', 'Tassels', Inv.EMBELLISHMENT,
                         when=all_of(one_of('services', ['tassel_work']),
                                     neq('tassels', 'no_tassels'))),
                material('thread_colour', 'Thread Colour', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'blouse', 'name': 'Blouse', 'sequence': 20,
        'sections': {
            'basic': [
                field('blouse_type', 'Blouse Type', 'select', required=True, options=[
                    'Plain', 'Princess', 'One-Tuck', 'Three Point', 'Katori',
                    'Portable Katori']),
            ],
            'measurements': blouse_measurements(),
            'style': [
                *sleeve_and_neck(),
                field('dot_point', 'Dot Point', 'text'),
                field('padding', 'Padding', 'select',
                      options=[('padded', 'Padded'), ('non_padded', 'Non-Padded')]),
                field('dori_required', 'Dori', 'boolean'),
                field('dori_colour', 'Dori Colour', 'text', when=eq('dori_required', True)),
                field('dori_tassel_type', 'Dori Tassel Type', 'select',
                      options=['Hand Made', 'Readymade', 'Knot'],
                      when=eq('dori_required', True)),
            ],
            'materials': [
                material('main_fabric', 'Main Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('cups', 'Cups', Inv.EMBELLISHMENT, when=eq('padding', 'padded')),
                material('hooks', 'Hooks', Inv.STITCHING),
                material('zip', 'Zip', Inv.STITCHING),
                material('thread', 'Thread', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'lehenga', 'name': 'Lehenga', 'sequence': 30,
        'sections': {
            'basic': [
                field('lehenga_type', 'Lehenga Type', 'select', required=True, options=[
                    'A-Line', 'Circular', 'Mermaid', 'Straight Cut',
                    ('panelled', 'Panelled (Khalis)')]),
            ],
            'measurements': [
                measurement('waist', 'Waist', required=True),
                measurement('floor_length', 'Floor Length', required=True),
            ],
            'style': [
                field('waist_finish', 'Waist Finish', 'select',
                      options=['Dori', 'Belt', 'Elastic']),
                field('border', 'Border', 'boolean'),
                field('backing', 'Backing', 'boolean'),
                field('lining_type', 'Lining', 'select',
                      options=['Cotton', 'Crepe', 'Catman']),
            ],
            'materials': [
                material('main_fabric', 'Main Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('can_can', 'Can Can', Inv.LINING),
                material('canvas', 'Canvas', Inv.LINING),
                material('border_material', 'Border', Inv.BORDER, when=eq('border', True)),
                material('zip', 'Zip', Inv.STITCHING),
                material('hooks', 'Hooks', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'lehenga_blouse', 'name': 'Lehenga Blouse', 'sequence': 40,
        'sections': {
            'basic': [
                field('blouse_style', 'Style', 'select', required=True, options=[
                    'Standard', 'Peplum', 'Ruffled', ('jacket', 'Jacket Style'),
                    ('cape', 'Cape Style'), 'Long Waist', 'Corset']),
            ],
            'measurements': blouse_measurements(),
            'style': [
                *sleeve_and_neck(),
                field('padding', 'Padding', 'boolean'),
                measurement('flare_length', 'Flare Length', when=eq('blouse_style', 'peplum')),
                field('flare_type', 'Flare Type', 'select',
                      options=['A-Line', 'Pleats', 'Box Pleats'],
                      when=eq('blouse_style', 'peplum')),
                field('layer_count', 'Number of Layers', 'number',
                      validation={'min': 1, 'max': 10, 'step': 1},
                      when=eq('blouse_style', 'ruffled')),
                field('collar_style', 'Collar Style', 'text', when=eq('blouse_style', 'jacket')),
                measurement('cape_length', 'Cape Length', when=eq('blouse_style', 'cape')),
                field('cape_neck_shape', 'Cape Neck Shape', 'text',
                      when=eq('blouse_style', 'cape')),
                field('cape_fastening', 'Buttons / Hooks', 'select',
                      options=['Buttons', 'Hooks', 'None'], when=eq('blouse_style', 'cape')),
                field('corset_cups', 'Corset Cups', 'select',
                      options=['Soft', 'Moulded', 'None'], when=eq('blouse_style', 'corset')),
                field('boning_required', 'Boning Required', 'boolean',
                      when=eq('blouse_style', 'corset')),
            ],
            'materials': [
                material('main_fabric', 'Main Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('cups', 'Cups', Inv.EMBELLISHMENT, when=eq('padding', True)),
                material('boning', 'Boning', Inv.EMBELLISHMENT,
                         when=eq('boning_required', True)),
                material('hooks', 'Hooks', Inv.STITCHING),
                material('zip', 'Zip', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'dupatta', 'name': 'Dupatta', 'sequence': 50,
        'sections': {
            'measurements': [
                measurement('length', 'Length', required=True),
                measurement('width', 'Width', required=True),
            ],
            'style': [
                field('border', 'Border', 'boolean'),
                field('backing', 'Backing', 'boolean'),
                field('embroidery_finish', 'Embroidery Finish', 'select',
                      options=['None', 'Machine', 'Hand', 'Maggam']),
            ],
            'materials': [
                material('fabric', 'Fabric', Inv.FABRIC),
                material('border_material', 'Border', Inv.BORDER, when=eq('border', True)),
                material('lace', 'Lace', Inv.BORDER),
                material('thread', 'Thread', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'kurti', 'name': 'Kurti', 'sequence': 60,
        'sections': {
            'basic': [
                field('kurti_type', 'Kurti Type', 'select', required=True,
                      options=['Plain', 'A-Line', '3 Piece', 'Khalis']),
            ],
            'measurements': [
                measurement('full_length', 'Full Length'),
                measurement('bodice_length', 'Bodice Length'),
                measurement('shoulder', 'Shoulder'),
                measurement('upper_chest', 'Upper Chest'),
                measurement('chest', 'Chest'),
                measurement('waist', 'Waist'),
                measurement('hip', 'Hip'),
            ],
            'style': [
                field('front_neck', 'Front Neck', 'text'),
                field('back_neck', 'Back Neck', 'text'),
                field('collar', 'Collar', 'text'),
                field('slit', 'Slit', 'select', options=['Left', 'Right', 'Both', 'None']),
                field('zip_position', 'Zip', 'select',
                      options=['Side', 'Front', 'Back', 'None']),
                field('pocket', 'Pocket', 'boolean'),
                field('padding', 'Padding', 'boolean'),
            ],
            'materials': [
                material('fabric', 'Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('zip', 'Zip', Inv.STITCHING, when=neq('zip_position', 'none')),
                material('buttons', 'Buttons', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'anarkali', 'name': 'Anarkali', 'sequence': 70,
        'sections': {
            'basic': [
                field('anarkali_type', 'Anarkali Type', 'select', required=True,
                      options=['A-Line', 'Khalis']),
                field('bodice', 'Bodice', 'select', options=[
                    ('with_bodice', 'With Bodice'), ('without_bodice', 'Without Bodice')]),
            ],
            'measurements': [
                measurement('top_length', 'Top Length'),
                measurement('bodice_length', 'Bodice Length',
                            when=eq('bodice', 'with_bodice')),
                measurement('shoulder', 'Shoulder'),
                measurement('upper_chest', 'Upper Chest'),
                measurement('chest', 'Chest'),
                measurement('waist', 'Waist'),
                measurement('hip', 'Hip'),
            ],
            'style': [
                field('front_neck', 'Front Neck', 'text'),
                field('back_neck', 'Back Neck', 'text'),
                field('collar', 'Collar', 'text'),
                field('padding', 'Padding', 'boolean'),
                field('zip', 'Zip', 'boolean'),
                field('pocket', 'Pocket', 'boolean'),
                field('border', 'Border', 'boolean'),
                field('backing', 'Backing', 'boolean'),
            ],
            'materials': [
                material('fabric', 'Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('can_can', 'Can Can', Inv.LINING),
                material('border_material', 'Border', Inv.BORDER, when=eq('border', True)),
            ],
        },
    },
    {
        'key': 'petticoat', 'name': 'Petticoat', 'sequence': 80,
        'sections': {
            'measurements': [
                measurement('length', 'Length', required=True),
                measurement('waist', 'Waist', required=True),
            ],
            'style': [
                field('waist_finish', 'Waist Finish', 'multiselect', options=WAIST_FINISH),
            ],
            'materials': bottom_materials(),
        },
    },
    {
        'key': 'salwar', 'name': 'Salwar', 'sequence': 90,
        'sections': {
            'measurements': [
                measurement('full_length', 'Full Length', required=True),
                measurement('waist', 'Waist', required=True),
            ],
            'style': [
                field('bottom_finish', 'Bottom Finish', 'select',
                      options=['Round', 'Flared', 'Ankle']),
                field('waist_finish', 'Waist Finish', 'select',
                      options=['Belt', 'Elastic', 'Dori']),
            ],
            'materials': bottom_materials(),
        },
    },
    {
        'key': 'churidar', 'name': 'Churidar', 'sequence': 100,
        'sections': {
            'measurements': [
                measurement('full_length', 'Full Length', required=True),
                measurement('waist', 'Waist', required=True),
                measurement('thigh', 'Thigh'),
                measurement('upper_thigh', 'Upper Thigh'),
                measurement('knee', 'Knee'),
                measurement('calf', 'Calf'),
                measurement('crotch', 'Crotch'),
            ],
            'style': [
                field('waist_finish', 'Waist Finish', 'select',
                      options=['Belt', 'Elastic', 'Dori']),
            ],
            'materials': bottom_materials(),
        },
    },
    {
        'key': 'palazzo', 'name': 'Palazzo', 'sequence': 110,
        'sections': {
            'measurements': [
                measurement('length', 'Length', required=True),
                measurement('waist', 'Waist', required=True),
            ],
            'style': [
                field('bottom_width', 'Bottom Width', 'select', options=[
                    ('11', '11"'), ('15', '15"'), ('17', '17"'), ('20', '20"')]),
            ],
            'materials': [
                material('fabric', 'Fabric', Inv.FABRIC),
                material('elastic', 'Elastic', Inv.STITCHING),
                material('zip', 'Zip', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'sharara', 'name': 'Sharara', 'sequence': 120,
        'sections': {
            'measurements': [
                measurement('length', 'Length', required=True),
                measurement('waist', 'Waist', required=True),
                measurement('thigh', 'Thigh'),
            ],
            'style': [
                field('bottom_width', 'Bottom Width', 'select', options=[
                    ('17', '17"'), ('20', '20"'), ('24', '24"')]),
            ],
            'materials': [
                material('fabric', 'Fabric', Inv.FABRIC),
                material('can_can', 'Can Can', Inv.LINING),
                material('elastic', 'Elastic', Inv.STITCHING),
                material('zip', 'Zip', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'gown', 'name': 'Gown', 'sequence': 130,
        'sections': {
            'basic': [
                field('gown_type', 'Gown Type', 'select', required=True, options=[
                    'A-Line', 'Mermaid', 'Ball Gown', 'Sheath', 'Empire',
                    ('cape_gown', 'Cape Gown'), 'Indo-Western']),
            ],
            'measurements': [
                measurement('floor_length', 'Floor Length', required=True),
                measurement('shoulder', 'Shoulder'),
                measurement('upper_chest', 'Upper Chest'),
                measurement('chest', 'Chest'),
                measurement('waist', 'Waist'),
                measurement('hip', 'Hip'),
                measurement('armhole', 'Armhole'),
            ],
            'style': [
                *sleeve_and_neck(),
                field('back_style', 'Back Style', 'select', options=[
                    ('deep_u', 'Deep U'), 'Keyhole', 'Backless', 'Standard']),
                field('padding', 'Padding', 'boolean'),
                field('slit', 'Slit', 'select', options=['Left', 'Right', 'Both', 'None']),
                field('train', 'Train', 'select', options=['None', 'Sweep', 'Chapel', 'Cathedral']),
                field('zip_position', 'Zip', 'select', options=['Side', 'Back', 'None']),
            ],
            'materials': [
                material('main_fabric', 'Main Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('can_can', 'Can Can', Inv.LINING),
                material('cups', 'Cups', Inv.EMBELLISHMENT, when=eq('padding', True)),
                material('boning', 'Boning', Inv.EMBELLISHMENT),
                material('zip', 'Zip', Inv.STITCHING, when=neq('zip_position', 'none')),
                material('hooks', 'Hooks', Inv.STITCHING),
            ],
        },
    },
    {
        # The kameez only. Its salwar or churidar and its dupatta are their own
        # dresses on the order, which is what lets each carry its own
        # measurements and go to a different tailor.
        'key': 'suit', 'name': 'Suit (Kameez)', 'sequence': 140,
        'sections': {
            'basic': [
                field('suit_type', 'Suit Type', 'select', required=True, options=[
                    'Straight Cut', 'A-Line', 'Anarkali Cut', 'Angrakha', 'Kalidar']),
            ],
            'measurements': [
                measurement('full_length', 'Full Length', required=True),
                measurement('shoulder', 'Shoulder'),
                measurement('upper_chest', 'Upper Chest'),
                measurement('chest', 'Chest'),
                measurement('waist', 'Waist'),
                measurement('hip', 'Hip'),
                measurement('armhole', 'Armhole'),
                measurement('arm_length', 'Arm Length'),
            ],
            'style': [
                *sleeve_and_neck(),
                field('slit', 'Side Slit', 'select', options=['Left', 'Right', 'Both', 'None']),
                field('zip_position', 'Zip', 'select', options=['Side', 'Front', 'Back', 'None']),
                field('pocket', 'Pocket', 'boolean'),
                field('padding', 'Padding', 'boolean'),
                field('border', 'Border', 'boolean'),
            ],
            'materials': [
                material('main_fabric', 'Main Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('border_material', 'Border', Inv.BORDER, when=eq('border', True)),
                material('cups', 'Cups', Inv.EMBELLISHMENT, when=eq('padding', True)),
                material('zip', 'Zip', Inv.STITCHING, when=neq('zip_position', 'none')),
                material('buttons', 'Buttons', Inv.STITCHING),
                material('thread', 'Thread', Inv.STITCHING),
            ],
        },
    },
    {
        # Menswear. The pants or churidar worn with it are a separate dress.
        'key': 'sherwani', 'name': 'Sherwani', 'sequence': 150,
        'sections': {
            'basic': [
                field('sherwani_type', 'Sherwani Type', 'select', required=True, options=[
                    'Classic', 'Angrakha', 'Indo-Western', 'Jodhpuri', 'Achkan']),
            ],
            'measurements': [
                measurement('full_length', 'Full Length', required=True),
                measurement('shoulder', 'Shoulder'),
                measurement('chest', 'Chest'),
                measurement('waist', 'Waist'),
                measurement('hip', 'Hip'),
                measurement('arm_length', 'Arm Length'),
                measurement('neck', 'Neck'),
            ],
            'style': [
                field('collar_style', 'Collar Style', 'select', options=[
                    'Bandhgala', 'Mandarin', 'Nehru', 'Shawl', 'Notch']),
                field('front_closure', 'Front Closure', 'select', options=[
                    'Buttons', 'Hooks', 'Concealed Zip', 'Open Front']),
                field('vent', 'Vent', 'select', options=['Centre', 'Side', 'None']),
                field('pocket', 'Pocket', 'boolean'),
                field('embroidery_finish', 'Embroidery Finish', 'select',
                      options=['None', 'Machine', 'Hand', 'Maggam', 'Zardozi']),
            ],
            'materials': [
                material('main_fabric', 'Main Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('canvas', 'Canvas', Inv.LINING),
                material('buttons', 'Buttons', Inv.STITCHING),
                material('thread', 'Thread', Inv.STITCHING),
                material('embroidery_material', 'Embroidery Material', Inv.MAGGAM,
                         when=not_one_of('embroidery_finish', ['none'])),
            ],
        },
    },
]

SECTION_TITLES = [
    ('basic', 'Basic Information'),
    ('measurements', 'Measurements'),
    ('style', 'Style & Design Options'),
    ('materials', 'Materials & Accessories'),
    ('production', 'Production Notes'),
]

COMMON_BY_SECTION = {
    'basic': COMMON_BASIC,
    'materials': COMMON_MATERIALS,
    'production': COMMON_PRODUCTION,
}


def build(definition):
    """Expand one definition into the five sections, common fields merged in.

    Garment fields come first within a section, common fields after, so the
    garment-specific question is what the counter staff answer first.
    """
    sections = []
    for index, (key, title) in enumerate(SECTION_TITLES):
        fields = list(definition['sections'].get(key, [])) + COMMON_BY_SECTION.get(key, [])
        sections.append({
            'key': key,
            'title': title,
            'sequence': index,
            'fields': fields,
        })
    return {
        'key': definition['key'],
        'name': definition['name'],
        'sequence': definition['sequence'],
        'sections': sections,
    }


def all_templates():
    return [build(d) for d in TEMPLATES]
