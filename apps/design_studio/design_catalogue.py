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

# --------------------------------------------------------------------------
# BLOUSE -- cutting and pattern construction, not necklines
# --------------------------------------------------------------------------
#
# What the tailor cuts: darts, katori, princess seams, panels, yokes, the back,
# the armhole. Neckline styles are a different dimension of a blouse and are
# deliberately not here. The Blouse Cut Master at the end is the simplified
# family view for the workroom; the nine detailed categories are the full
# catalogue. A name appearing in both ("Shoulder Princess") is two positions,
# addressed by their paths, as everywhere else in this file.

_BLOUSE_CATEGORIES = [
    _category(
        'Main Blouse Cutting / Pattern Types', short='Main Cutting / Pattern',
        options=[
            'Katori Cutting', 'Princess Cutting', 'Princess Dart', 'Waist Dart', 'Side Dart',
            'Shoulder Dart', 'Bust Dart', 'French Dart', 'Armhole Dart', 'Centre Front Dart',
            'Centre Back Dart', 'Double Dart', 'Single Dart', 'Panel Cutting', '4-Panel Cutting',
            '6-Panel Cutting', '8-Panel Cutting', 'Centre Panel Cutting', 'Side Panel Cutting',
            'Vertical Panel Cutting', 'Horizontal Panel Cutting',
        ]),
    _category(
        'Traditional Blouse Construction Cuts', short='Traditional Construction',
        options=[
            'Katori Blouse', 'Katori Panel Cutting', 'Katori + Princess Combination',
            'Princess Panel Blouse', 'Princess Seam Blouse', 'Princess Cut from Armhole',
            'Princess Cut from Shoulder', 'Princess Cut from Neck',
            'Princess Cut from Armhole to Waist', 'Side Panel Blouse', 'Centre Panel Blouse',
            'Multi-Panel Blouse', 'Darted Blouse', 'Panel-and-Dart Blouse',
        ]),
    _category(
        'Bust-Fitting Cuts', short='Bust-Fitting',
        options=[
            'Single Bust Dart', 'Double Bust Dart', 'Vertical Bust Dart', 'Horizontal Bust Dart',
            'Diagonal Bust Dart', 'Under-Bust Dart', 'Side Bust Dart', 'Shoulder Bust Dart',
            'Waist Bust Dart', 'French Dart',
        ]),
    _category(
        'Designer / Advanced Cuts', short='Designer / Advanced',
        options=[
            'Princess Seam', 'Princess Panel', 'Empire Cut', 'Empire Waist Blouse', 'Yoke Cutting',
            'Yoke + Panel Cutting', 'Yoke + Katori Cutting', 'Peplum Cut', 'Corset Panel Cutting',
            'Corset Seam', 'Bustier Panel Cutting', 'Contour Cutting', 'Curved Panel Cutting',
            'Asymmetric Panel Cutting', 'Diagonal Panel Cutting', 'Cross Panel Cutting',
            'V-Panel Cutting', 'U-Panel Cutting', 'Geometric Panel Cutting', 'Cut-and-Join Blouse',
        ]),
    _category(
        'Katori Variations', short='Katori',
        options=[
            'Single Katori', 'Double Katori', '2-Piece Katori', '3-Piece Katori', '4-Piece Katori',
            'Full Katori', 'Half Katori', 'Round Katori', 'Curved Katori', 'Pointed Katori',
            'Deep Katori', 'Katori with Princess Seam', 'Katori with Waist Dart',
            'Katori with Side Panel', 'Katori with Yoke', 'Katori Corset',
        ]),
    _category(
        'Princess-Cut Variations', short='Princess-Cut',
        options=[
            'Shoulder Princess', 'Armhole Princess', 'Neck Princess', 'Centre Princess',
            'Side Princess', 'Full Princess', 'Half Princess', 'Princess with Katori',
            'Princess with Yoke', 'Princess with Panel', 'Princess with Dart', 'Princess Corset',
            'Princess Peplum',
        ]),
    _category(
        'Blouse Back Construction Cuts', short='Back Construction',
        options=[
            'Back Princess', 'Back Dart', 'Back Panel', 'Centre Back Seam', 'Centre Back Opening',
            'Back Yoke', 'Back Katori', 'Back V-Panel', 'Back U-Panel', 'Back Keyhole Panel',
            'Back Corset Panel', 'Back Lace-Up Panel', 'Back Cut-Out Panel',
        ]),
    _category(
        'Sleeve Attachment / Armhole Cuts', short='Sleeve / Armhole',
        options=[
            'Normal Armhole', 'Deep Armhole', 'High Armhole', 'Round Armhole', 'Square Armhole',
            'Princess Armhole', 'Cut-In Armhole', 'Raglan Sleeve Cut', 'Kimono Sleeve Cut',
            'Dolman Sleeve Cut', 'Extended Shoulder Cut', 'Cap Sleeve Cut', 'Puff Sleeve Cut',
            'Petal Sleeve Cut', 'Bell Sleeve Cut',
        ]),
    _category(
        'Yoke Cuts', short='Yoke',
        options=[
            'Round Yoke', 'Square Yoke', 'V-Yoke', 'U-Yoke', 'Straight Yoke', 'Curved Yoke',
            'Deep Yoke', 'High Yoke', 'Front Yoke', 'Back Yoke', 'Full Yoke', 'Half Yoke',
            'Shoulder Yoke', 'Neck Yoke', 'Embroidered Yoke', 'Transparent Yoke',
        ]),
    _category(
        'Blouse Cut Master', short='Cut Master',
        note='The primary cutting families, simplified for the workroom.',
        subcategories=[
            ('Dart Cut', ['Single Dart', 'Double Dart', 'French Dart', 'Bust Dart', 'Waist Dart',
                          'Shoulder Dart']),
            ('Katori Cut', ['2-Piece', '3-Piece', '4-Piece', 'Katori + Dart', 'Katori + Princess']),
            ('Princess Cut', ['Shoulder Princess', 'Armhole Princess', 'Neck Princess',
                              'Centre Princess', 'Princess Panel']),
            ('Panel Cut', ['2 Panel', '4 Panel', '6 Panel', '8 Panel', 'Centre Panel', 'Side Panel',
                           'Diagonal Panel']),
            ('Yoke Cut', ['Round', 'Square', 'V', 'U', 'Curved', 'Deep']),
            ('Designer Construction', ['Corset', 'Bustier', 'Empire', 'Peplum', 'Asymmetric',
                                       'Geometric', 'Draped']),
        ]),
]

# --------------------------------------------------------------------------
# LEHENGA -- silhouette and construction
# --------------------------------------------------------------------------
#
# Eleven dimensions of how a lehenga is built and looks, then the Lehenga
# Design Master: the structured attributes a cutting master reads (silhouette,
# kali count, pleat type, flare, waist, hem...). The detailed categories are
# for filing design photographs; the master is the attribute vocabulary. The
# same idea appears in both ("16-Kali Lehenga" and Kali Count > "16 Kali") and
# in more than one detail category ("Dhoti Lehenga" is both a draped style and
# a designer cut) -- every one is its own position, by its path.
#
# Kali counts are separate options on purpose: the number of panels is the
# construction, and "Kali Lehenga" alone would lose it.

_LEHENGA_CATEGORIES = [
    _category(
        'Basic Lehenga Silhouettes', short='Basic Silhouettes',
        options=[
            'Flared Lehenga', 'A-Line Lehenga', 'Straight-Cut Lehenga', 'Circular Lehenga',
            'Semi-Circular Lehenga', 'Full-Circular Lehenga', 'Kali Lehenga', 'Panelled Lehenga',
            'Mermaid Lehenga', 'Fish-Cut Lehenga', 'Trumpet Lehenga', 'Fishtail Lehenga',
            'Tiered Lehenga', 'Layered Lehenga', 'Umbrella Lehenga', 'Sharara-Style Lehenga',
            'Skirt-Style Lehenga', 'Maxi Lehenga', 'Floor-Length Lehenga', 'Short Lehenga',
            'Knee-Length Lehenga',
        ]),
    _category(
        'Pleated Lehenga Styles', short='Pleated',
        options=[
            'Pattu Pleated Lehenga', 'Knife-Pleated Lehenga', 'Box-Pleated Lehenga',
            'Accordion-Pleated Lehenga', 'Sunray Pleated Lehenga', 'Fine-Pleated Lehenga',
            'Broad-Pleated Lehenga', 'Front Pleated Lehenga', 'Side Pleated Lehenga',
            'All-Around Pleated Lehenga', 'Structured Pleated Lehenga', 'Draped Pleated Lehenga',
            'Layered Pleated Lehenga', 'Pleated Panel Lehenga',
        ]),
    _category(
        'Kali / Panel Construction', short='Kali / Panel',
        options=[
            '4-Kali Lehenga', '6-Kali Lehenga', '8-Kali Lehenga', '10-Kali Lehenga',
            '12-Kali Lehenga', '16-Kali Lehenga', '20-Kali Lehenga', '24-Kali Lehenga',
            '32-Kali Lehenga', 'Multi-Kali Lehenga', 'Broad-Kali Lehenga', 'Narrow-Kali Lehenga',
            'Alternating-Kali Lehenga', 'Contrast-Kali Lehenga', 'Embroidered-Kali Lehenga',
        ]),
    _category(
        'Ruffle & Layered Styles', short='Ruffle & Layered',
        options=[
            'Ruffled Lehenga', 'Single-Ruffle Lehenga', 'Double-Ruffle Lehenga',
            'Multi-Ruffle Lehenga', 'Tiered Ruffle Lehenga', 'Cascading Ruffle Lehenga',
            'Asymmetric Ruffle Lehenga', 'Ruffle-Panel Lehenga', 'Layered Lehenga',
            'Double-Layer Lehenga', 'Triple-Layer Lehenga', 'Multi-Tier Lehenga', 'Tiered Lehenga',
            'Frill Lehenga', 'Flounce Lehenga', 'Scalloped Layer Lehenga',
        ]),
    _category(
        'Draped Lehenga Styles', short='Draped',
        options=[
            'Draped Lehenga', 'Pre-Draped Lehenga', 'Saree-Style Lehenga', 'Dhoti Lehenga',
            'Draped Skirt Lehenga', 'Cowl Draped Lehenga', 'Front-Draped Lehenga',
            'Side-Draped Lehenga', 'Asymmetric Draped Lehenga', 'Wrap Lehenga',
            'Wrap-Around Lehenga', 'Panel-Draped Lehenga',
        ]),
    _category(
        'Modern / Designer Lehenga Cuts', short='Modern / Designer',
        options=[
            'Asymmetric Lehenga', 'High-Low Lehenga', 'Slit Lehenga', 'Front-Slit Lehenga',
            'Side-Slit Lehenga', 'Double-Slit Lehenga', 'Cut-Out Lehenga', 'Peplum Lehenga',
            'Corset Lehenga', 'Bustier Lehenga', 'Jacket Lehenga', 'Cape Lehenga', 'Pant Lehenga',
            'Dhoti Lehenga', 'Skirt Lehenga', 'Lehenga Gown', 'Lehenga Saree',
            'Indo-Western Lehenga', 'Fusion Lehenga', 'Co-Ord Lehenga', 'Layered Skirt Lehenga',
        ]),
    _category(
        'Traditional / Bridal Lehenga Styles', short='Traditional / Bridal',
        options=[
            'Bridal Lehenga', 'Bridal Circular Lehenga', 'Bridal Kali Lehenga',
            'Bridal A-Line Lehenga', 'Bridal Flared Lehenga', 'Pattu Lehenga',
            'Pattu Pavadai-Style Lehenga', 'Banarasi Lehenga', 'Brocade Lehenga', 'Zari Lehenga',
            'Gota Patti Lehenga', 'Rajasthani Lehenga', 'Gujarati Lehenga', 'Rajputi Lehenga',
            'Punjabi Lehenga', 'Mughal-Style Lehenga', 'Temple-Style Lehenga', 'Heritage Lehenga',
        ]),
    _category(
        'Fabric-Based Lehenga Styles', short='Fabric-Based',
        options=[
            'Pattu / Silk Lehenga', 'Kanjeevaram Silk Lehenga', 'Banarasi Silk Lehenga',
            'Raw Silk Lehenga', 'Tussar Silk Lehenga', 'Velvet Lehenga', 'Organza Lehenga',
            'Georgette Lehenga', 'Chiffon Lehenga', 'Net Lehenga', 'Tissue Lehenga',
            'Satin Lehenga', 'Crepe Lehenga', 'Brocade Lehenga', 'Chanderi Lehenga',
            'Linen Lehenga', 'Cotton Lehenga', 'Jacquard Lehenga',
        ]),
    _category(
        'Volume / Flare Classification', short='Volume / Flare',
        options=[
            'Low-Flare Lehenga', 'Medium-Flare Lehenga', 'High-Flare Lehenga',
            'Extra-Flare Lehenga', 'Circular Flare', 'Umbrella Flare', 'Structured Flare',
            'Soft Flare', 'Stiff Flare', 'Layered Flare', 'Panelled Flare', 'Graduated Flare',
            'Mermaid Flare', 'Trumpet Flare',
        ]),
    _category(
        'Waist Construction', short='Waist',
        options=[
            'Normal Waist Lehenga', 'High-Waist Lehenga', 'Mid-Waist Lehenga', 'Low-Waist Lehenga',
            'Elastic Waist', 'Hook Waist', 'Zip Waist', 'Side-Zip Waist', 'Front-Opening Waist',
            'Lace-Up Waist', 'Tie-Up Waist', 'Corset Waist', 'Belted Waist', 'Drawstring Waist',
        ]),
    _category(
        'Lehenga Border / Hem Styles', short='Border / Hem',
        options=[
            'Plain Hem', 'Zari Border', 'Contrast Border', 'Broad Border', 'Narrow Border',
            'Double Border', 'Triple Border', 'Embroidered Border', 'Scalloped Hem', 'Wave Hem',
            'Lace Hem', 'Ruffle Hem', 'Fringe Hem', 'Tassel Hem', 'Cutwork Hem', 'Gota Border',
            'Piping Hem',
        ]),
    _category(
        'Lehenga Design Master', short='Design Master',
        note='The structured construction attributes a cutting master reads.',
        subcategories=[
            ('Silhouette', ['A-Line', 'Flared', 'Mermaid', 'Straight', 'Circular', 'Semi-Circular',
                            'Full-Circular', 'Trumpet', 'Fishtail', 'Tiered', 'Layered', 'Umbrella']),
            ('Construction', ['Kali', 'Panelled', 'Circular', 'Tiered', 'Layered']),
            ('Kali Count', ['4 Kali', '6 Kali', '8 Kali', '10 Kali', '12 Kali', '16 Kali', '20 Kali',
                            '24 Kali', '32 Kali', 'Multi-Kali']),
            ('Pleat Type', ['Pattu', 'Knife', 'Box', 'Accordion', 'Sunray', 'Fine', 'Broad', 'Front',
                            'Side', 'All-Around', 'Structured', 'Draped', 'Layered', 'Pleated Panel']),
            ('Flare', ['Low', 'Medium', 'High', 'Extra', 'Circular', 'Umbrella', 'Structured', 'Soft',
                       'Stiff', 'Layered', 'Panelled', 'Graduated', 'Mermaid', 'Trumpet']),
            ('Layer', ['Single', 'Double', 'Triple', 'Multi']),
            ('Ruffle', ['None', 'Single', 'Double', 'Multi', 'Tiered', 'Cascading', 'Asymmetric',
                        'Panel']),
            ('Drape', ['Normal', 'Draped', 'Pre-Draped', 'Saree-Style', 'Dhoti', 'Cowl',
                       'Front-Draped', 'Side-Draped', 'Wrap', 'Panel-Draped']),
            ('Waist', ['Normal', 'High', 'Mid', 'Low', 'Elastic', 'Hook', 'Zip', 'Side-Zip',
                       'Front-Opening', 'Lace-Up', 'Tie-Up', 'Corset', 'Belted', 'Drawstring']),
            ('Length', ['Short', 'Knee-Length', 'Ankle-Length', 'Floor-Length', 'Maxi']),
            ('Hem', ['Plain', 'Zari', 'Contrast', 'Broad', 'Narrow', 'Double', 'Triple', 'Embroidered',
                     'Scalloped', 'Wave', 'Lace', 'Ruffle', 'Fringe', 'Tassel', 'Cutwork', 'Gota',
                     'Piping']),
            ('Fabric', ['Pattu / Silk', 'Kanjeevaram Silk', 'Banarasi Silk', 'Raw Silk', 'Tussar Silk',
                        'Velvet', 'Organza', 'Georgette', 'Chiffon', 'Net', 'Tissue', 'Satin', 'Crepe',
                        'Brocade', 'Chanderi', 'Linen', 'Cotton', 'Jacquard']),
        ]),
]

CATALOGUE = {
    'saree': {'key': 'saree', 'label': 'Saree', 'categories': _SAREE_CATEGORIES},
    'blouse': {'key': 'blouse', 'label': 'Blouse', 'categories': _BLOUSE_CATEGORIES},
    'lehenga': {'key': 'lehenga', 'label': 'Lehenga', 'categories': _LEHENGA_CATEGORIES},
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
