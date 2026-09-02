
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date
from decimal import Decimal

from crm_api.models import Customer

_BODY_TYPE_RULES = [
    (Decimal('12'), 'Hourglass'),
    (Decimal('8'), 'Balanced'),
    (Decimal('4'), 'Straight'),
]


def _as_decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _age_group(dob):
    if not dob:
        return ''
    today = date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if years < 18:
        return 'Teen'
    if years < 30:
        return 'Young Adult'
    if years < 45:
        return 'Adult'
    return 'Mature'


@dataclass
class Subject:

    customer_id: str = ''
    first_name: str = ''
    last_name: str = ''
    customer_type: str = ''
    source: str = ''
    date_of_birth: object = None

    measurements: dict = field(default_factory=dict)

    neckline_style: str = ''
    sleeve_style: str = ''
    back_style: str = ''
    length_preference: str = ''
    silhouette: str = ''
    embellishments: str = ''
    pattern_style: str = ''

    garment_type: str = ''
    occasion: str = ''
    custom_requirements: str = ''

    colours: object = field(default_factory=Counter)
    fabrics: object = field(default_factory=Counter)
    designs: object = field(default_factory=Counter)
    previous_order_count: int = 0

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip()


def subject_from_customer(customer):

    measurement = getattr(customer, 'measurements', None)
    measurements = {}
    if measurement is not None:
        for name in ('bust', 'waist', 'hips', 'shoulder', 'arm_length', 'neck', 'length'):
            value = getattr(measurement, name, None)
            if value is not None:
                measurements[name] = float(value)
        measurements.update(measurement.additional_measurements or {})

    colours, fabrics, designs = _history_signals(customer)
    return Subject(
        customer_id=str(customer.id),
        first_name=customer.first_name or '',
        last_name=customer.last_name or '',
        customer_type=customer.customer_type or '',
        source=customer.source or '',
        date_of_birth=customer.date_of_birth,
        measurements=measurements,
        neckline_style=customer.neckline_style or '',
        sleeve_style=customer.sleeve_style or '',
        back_style=customer.back_style or '',
        length_preference=customer.length_preference or '',
        silhouette=customer.silhouette or '',
        embellishments=customer.embellishments or '',
        pattern_style=customer.pattern_style or '',
        garment_type=customer.garment_type or '',
        occasion=customer.occasion or '',
        custom_requirements=customer.custom_requirements or '',
        colours=colours, fabrics=fabrics, designs=designs,
        previous_order_count=customer.orders.count(),
    )


def subject_from_draft(payload):
    payload = payload or {}
    measurements = {
        key: value for key, value in (payload.get('measurements') or {}).items()
        if value not in (None, '')
    }
    return Subject(
        customer_id='',
        first_name=payload.get('first_name') or '',
        last_name=payload.get('last_name') or '',
        customer_type=payload.get('customer_type') or '',
        source=payload.get('source') or '',
        date_of_birth=None,
        measurements=measurements,
        neckline_style=payload.get('neckline_style') or '',
        sleeve_style=payload.get('sleeve_style') or '',
        back_style=payload.get('back_style') or '',
        length_preference=payload.get('length_preference') or '',
        silhouette=payload.get('silhouette') or '',
        embellishments=payload.get('embellishments') or '',
        pattern_style=payload.get('pattern_style') or '',
        garment_type=payload.get('garment_type') or '',
        occasion=payload.get('occasion') or '',
        custom_requirements=(payload.get('custom_requirements')
                             or payload.get('special_instructions') or ''),
        previous_order_count=0,
    )


@dataclass
class CustomerContext:
    customer_id: str = ''
    customer_name: str = ''
    gender: str = ''
    customer_category: str = ''
    age_group: str = ''

    measurements: dict = field(default_factory=dict)
    body_type: str = ''
    fit_preference: str = ''

    garment_type: str = ''
    occasion: str = ''
    budget: Decimal = Decimal('0')
    delivery_timeline: str = ''

    style_preferences: dict = field(default_factory=dict)
    favourite_colours: list = field(default_factory=list)
    preferred_fabrics: list = field(default_factory=list)
    frequent_designs: list = field(default_factory=list)
    previous_order_count: int = 0
    custom_requirements: str = ''

    def to_dict(self):
        data = asdict(self)
        data['budget'] = float(self.budget or 0)
        return data


def _body_type(measurements):
    bust = _as_decimal(measurements.get('bust'))
    waist = _as_decimal(measurements.get('waist'))
    hips = _as_decimal(measurements.get('hips'))
    if bust is None or waist is None:
        return ''
    drop = max(bust - waist, (hips - waist) if hips is not None else Decimal('0'))
    for threshold, label in _BODY_TYPE_RULES:
        if drop >= threshold:
            return label
    return 'Straight'


def _history_signals(customer):

    colours, fabrics, designs = Counter(), Counter(), Counter()

    for selection in customer.fabric_selections.all():
        if selection.fabric_name:
            fabrics[selection.fabric_name.strip()] += 1

    if customer.embellishments:
        designs[customer.embellishments.strip()] += 1
    if customer.pattern_style:
        designs[customer.pattern_style.strip()] += 1
    if customer.silhouette:
        designs[customer.silhouette.strip()] += 1

    for fabric_name in list(fabrics):
        for token in fabric_name.split():
            token = token.strip().lower()
            if token in _COLOUR_WORDS:
                colours[token.title()] += 1

    return colours, fabrics, designs


_COLOUR_WORDS = {
    'maroon', 'red', 'blue', 'navy', 'green', 'emerald', 'gold', 'golden',
    'ivory', 'white', 'black', 'pink', 'peach', 'beige', 'mustard', 'teal',
    'lavender', 'purple', 'silver', 'rust', 'coral', 'wine', 'cream',
}


_SPEC_TO_STYLE = {
    'neckline': ('front_neck', 'neck_type', 'neckline_style'),
    'sleeve': ('sleeve_length', 'sleeve_style'),
    'back': ('back_neck', 'back_style'),
    'length': ('length_preference', 'flare_length'),
    'silhouette': ('blouse_style', 'lehenga_type', 'blouse_type', 'silhouette'),
    'embellishments': ('embellishments', 'tassels'),
    'pattern': ('pattern_style',),
}


def build_context(subject, order_input=None):
    order_input = order_input or {}
    measurements = dict(subject.measurements or {})
    budget = _as_decimal(order_input.get('budget')) or Decimal('0')

    style_preferences = {
        'neckline': subject.neckline_style,
        'sleeve': subject.sleeve_style,
        'back': subject.back_style,
        'length': subject.length_preference,
        'silhouette': subject.silhouette,
        'embellishments': subject.embellishments,
        'pattern': subject.pattern_style,
    }
    spec = order_input.get('spec') or {}
    for style_key, spec_keys in _SPEC_TO_STYLE.items():
        for spec_key in spec_keys:
            value = spec.get(spec_key)
            if isinstance(value, bool):
                continue
            if value not in (None, '', [], {}):
                style_preferences[style_key] = (
                    ', '.join(str(v) for v in value) if isinstance(value, list)
                    else str(value))
                break

    measurements.update({
        key: value for key, value in (order_input.get('measurements') or {}).items()
        if value not in (None, '')
    })

    return CustomerContext(
        customer_id=subject.customer_id,
        customer_name=subject.name,
        gender=subject.customer_type,
        customer_category=subject.source,
        age_group=_age_group(subject.date_of_birth),
        measurements=measurements,
        body_type=_body_type(measurements),
        fit_preference=style_preferences['silhouette'],
        garment_type=(order_input.get('garment_type') or subject.garment_type or '').strip(),
        occasion=(order_input.get('occasion') or subject.occasion or '').strip(),
        budget=budget,
        delivery_timeline=order_input.get('delivery_timeline', '') or '',
        style_preferences=style_preferences,
        favourite_colours=[name for name, _ in subject.colours.most_common(5)],
        preferred_fabrics=[name for name, _ in subject.fabrics.most_common(5)],
        frequent_designs=[name for name, _ in subject.designs.most_common(5)],
        previous_order_count=subject.previous_order_count,
        custom_requirements=subject.custom_requirements,
    )


def load_context(customer_id, order_input=None):
    customer = (Customer.objects
                .select_related('measurements')
                .prefetch_related('orders', 'fabric_selections', 'design_preferences')
                .get(pk=customer_id))
    return customer, build_context(subject_from_customer(customer), order_input)
