
import re

from apps.inventory.models import Category as Inv


def _slug(label):
    return re.sub(r'[^a-z0-9]+', '_', str(label).lower()).strip('_')


def field(key, label, field_type, **kw):

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


def parts(*labels):
    """The parts of a garment a design photograph can be of.

    Labels in, [{"key": ..., "label": ...}] out, slugged the same way option
    values are so the two vocabularies cannot drift apart. Order is the order
    the upload form shows them in, so the overall shot comes first.
    """
    seen, out = set(), []
    for label in labels:
        key = _slug(label)
        if key in seen:      # a list written by hand repeats itself eventually
            continue
        seen.add(key)
        out.append({'key': key, 'label': label})
    return out


# --- the garments ----------------------------------------------------------

TEMPLATES = [
    {
        'key': 'saree', 'name': 'Saree', 'sequence': 10,
        'design_parts': parts('Overall Saree Design', 'Pallu Design', 'Border Design',
              'Body Design', 'Pleat Design', 'Print Design', 'Embroidery Design',
              'Zari / Work Design'),
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
                material('tassels_material', 'Tassels', Inv.EMBELLISHMENT,
                         when=all_of(one_of('services', ['tassel_work']),
                                     neq('tassels', 'no_tassels'))),
                material('thread_colour', 'Thread Colour', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'blouse', 'name': 'Blouse', 'sequence': 20,
        'design_parts': parts('Overall Blouse Design', 'Front Design', 'Back Design',
              'Neck Design', 'Sleeve Design', 'Hand Design'),
        'sections': {
            'basic': [
                # Lehenga Blouse was retired into this garment, so its styles
                # live here now. Keeping them on `blouse_type` rather than
                # reviving a second `blouse_style` field means one question
                # decides the cut, and the conditional fields below hang off
                # the same answer the counter staff already give.
                field('blouse_type', 'Blouse Type', 'select', required=True, options=[
                    'Plain', 'Princess', 'One-Tuck', 'Three Point', 'Katori',
                    'Portable Katori', 'Peplum', 'Ruffled', ('jacket', 'Jacket Style'),
                    ('cape', 'Cape Style'), 'Long Waist', 'Corset']),
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
                # Carried over from Lehenga Blouse with the retirement. Each is
                # invisible unless its own cut is chosen, so a Plain blouse asks
                # exactly what it asked before.
                measurement('flare_length', 'Flare Length', when=eq('blouse_type', 'peplum')),
                field('flare_type', 'Flare Type', 'select',
                      options=['A-Line', 'Pleats', 'Box Pleats'],
                      when=eq('blouse_type', 'peplum')),
                field('layer_count', 'Number of Layers', 'number',
                      validation={'min': 1, 'max': 10, 'step': 1},
                      when=eq('blouse_type', 'ruffled')),
                field('collar_style', 'Collar Style', 'text', when=eq('blouse_type', 'jacket')),
                measurement('cape_length', 'Cape Length', when=eq('blouse_type', 'cape')),
                field('cape_neck_shape', 'Cape Neck Shape', 'text',
                      when=eq('blouse_type', 'cape')),
                field('cape_fastening', 'Buttons / Hooks', 'select',
                      options=['Buttons', 'Hooks', 'None'], when=eq('blouse_type', 'cape')),
                field('corset_cups', 'Corset Cups', 'select',
                      options=['Soft', 'Moulded', 'None'], when=eq('blouse_type', 'corset')),
                field('boning_required', 'Boning Required', 'boolean',
                      when=eq('blouse_type', 'corset')),
            ],
            'materials': [
                material('main_fabric', 'Main Fabric', Inv.FABRIC),
                material('lining', 'Lining', Inv.LINING),
                material('cups', 'Cups', Inv.EMBELLISHMENT, when=eq('padding', 'padded')),
                material('boning', 'Boning', Inv.EMBELLISHMENT,
                         when=eq('boning_required', True)),
                material('hooks', 'Hooks', Inv.STITCHING),
                material('zip', 'Zip', Inv.STITCHING),
                material('thread', 'Thread', Inv.STITCHING),
            ],
        },
    },
    {
        'key': 'lehenga', 'name': 'Lehenga', 'sequence': 30,
        'design_parts': parts('Overall Lehenga Design', 'Lehenga / Skirt Design', 'Border Design',
              'Waistband Design', 'Embroidery / Work Design', 'Print Design'),
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
        'key': 'dupatta', 'name': 'Dupatta', 'sequence': 50,
        'design_parts': parts('Overall Dupatta Design', 'Border Design', 'Pallu / End Design',
              'Body Design', 'Corner Design', 'Print Design',
              'Embroidery / Work Design', 'Tassel / Latkan Design'),
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
        'design_parts': parts('Overall Kurti Design', 'Front Design', 'Back Design', 'Neck Design',
              'Sleeve Design', 'Hemline / Bottom Design', 'Side Design',
              'Embroidery / Work Design', 'Print Design', 'Pocket Design'),
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
        'design_parts': parts('Overall Anarkali Design', 'Front Design', 'Back Design',
              'Neck Design', 'Sleeve Design', 'Flare / Ghera Design',
              'Border Design', 'Dupatta Design', 'Embroidery Design',
              'Print Design', 'Waist / Belt Design'),
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
        'design_parts': parts('Overall Petticoat Design', 'Waist Design', 'Flare / Ghera Design',
              'Bottom / Border Design', 'Side Design'),
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
        'key': 'bottom_wear', 'name': 'Bottom Wear', 'sequence': 90,
        'design_parts': parts('Overall Design', 'Waist Design', 'Upper / Thigh Design',
              'Leg Design', 'Bottom / Ankle Design', 'Flare / Ghera Design',
              'Border Design', 'Pocket Design', 'Embroidery Design', 'Print Design'),
        'sections': {
            'basic': [
                field('bottom_type', 'Bottom Type', 'select', required=True, options=[
                    'Salwar', 'Churidar', 'Palazzo', 'Sharara', 'Patiala',
                    'Cigarette Pant', 'Dhoti', 'Other']),
                field('bottom_type_other', 'Specify Type', 'text',
                      when=eq('bottom_type', 'other')),
            ],
            'measurements': [
                measurement('full_length', 'Full Length', required=True),
                measurement('waist', 'Waist', required=True),
                measurement('hip', 'Hip'),
                measurement('thigh', 'Thigh'),
                measurement('upper_thigh', 'Upper Thigh'),
                measurement('knee', 'Knee'),
                measurement('calf', 'Calf'),
                measurement('ankle', 'Ankle'),
                measurement('crotch', 'Crotch'),
            ],
            'style': [
                field('waist_finish', 'Waist Finish', 'select', options=WAIST_FINISH),
                field('bottom_finish', 'Bottom Finish', 'select',
                      options=['Round', 'Flared', 'Ankle', 'Straight']),
                field('bottom_width', 'Bottom Width', 'select', options=[
                    ('11', '11"'), ('15', '15"'), ('17', '17"'),
                    ('20', '20"'), ('24', '24"')]),
                field('pocket_required', 'Pockets', 'boolean'),
            ],
            'materials': bottom_materials(extra=[
                material('can_can', 'Can Can', Inv.LINING,
                         when=one_of('bottom_type', ['sharara'])),
                material('zip', 'Zip', Inv.STITCHING),
            ]),
        },
    },
    {
        'key': 'gown', 'name': 'Gown', 'sequence': 130,
        'design_parts': parts('Front Design', 'Back Design', 'Neck Design', 'Sleeve Design',
              'Waist Design', 'Skirt / Flare Design', 'Border / Hem Design',
              'Side Design', 'Embroidery Design', 'Print Design'),
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
        'key': 'suit', 'name': 'Suit (Kameez)', 'sequence': 140,
        'design_parts': parts('Front Design', 'Back Design', 'Neck Design', 'Sleeve Design',
              'Side Design', 'Bottom / Salwar Design', 'Border Design',
              'Embroidery Design', 'Print Design'),
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
        'key': 'sherwani', 'name': 'Sherwani', 'sequence': 150,
        'design_parts': parts('Front Design', 'Back Design', 'Collar / Neck Design',
              'Sleeve Design', 'Button Design', 'Pocket Design',
              'Hem / Bottom Design', 'Side Design', 'Embroidery Design',
              'Print / Pattern Design'),
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
        'design_parts': definition.get('design_parts', []),
        'sections': sections,
    }


def all_templates():
    return [build(d) for d in TEMPLATES]
