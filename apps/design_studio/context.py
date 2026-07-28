"""Customer Context Engine.

Assembles everything the studio knows about a customer before a single design
is fetched: profile, measurements, the order being created, and what they have
bought before. Every downstream step -- query generation, ranking, the match
reasons shown on a card -- reads from this one structure, so the gallery can
always explain itself.
"""

from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date
from decimal import Decimal

from crm_api.models import Customer

# Bust-to-waist drop is the cheap, reliable signal available from the
# measurements already captured in step 2. It is a styling hint for ranking,
# never a judgement shown to the customer.
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
    """Colours, fabrics and designs this customer has actually chosen before."""
    colours, fabrics, designs = Counter(), Counter(), Counter()

    for selection in customer.fabric_selections.all():
        if selection.fabric_name:
            fabrics[selection.fabric_name.strip()] += 1

    # Colour is not a first-class field on an order; it is carried on the
    # customer's profile and inside the names of the fabrics they picked, which
    # is why colours are derived from fabric names below.
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


def build_context(customer, order_input=None):
    """Build the context for a customer, overlaid with the in-flight order.

    ``order_input`` carries what the wizard has collected but not yet saved --
    garment type, occasion, budget, timeline. It wins over the customer's
    stored defaults, because it describes the order being placed right now.
    """
    order_input = order_input or {}

    measurement = getattr(customer, 'measurements', None)
    measurements = {}
    if measurement is not None:
        for name in ('bust', 'waist', 'hips', 'shoulder', 'arm_length', 'neck', 'length'):
            value = getattr(measurement, name, None)
            if value is not None:
                measurements[name] = float(value)
        measurements.update(measurement.additional_measurements or {})

    colours, fabrics, designs = _history_signals(customer)

    budget = _as_decimal(order_input.get('budget')) or Decimal('0')

    return CustomerContext(
        customer_id=str(customer.id),
        customer_name=f"{customer.first_name} {customer.last_name}".strip(),
        gender=customer.customer_type or '',
        customer_category=customer.source or '',
        age_group=_age_group(customer.date_of_birth),
        measurements=measurements,
        body_type=_body_type(measurements),
        fit_preference=customer.silhouette or '',
        garment_type=(order_input.get('garment_type') or customer.garment_type or '').strip(),
        occasion=(order_input.get('occasion') or customer.occasion or '').strip(),
        budget=budget,
        delivery_timeline=order_input.get('delivery_timeline', '') or '',
        style_preferences={
            'neckline': customer.neckline_style or '',
            'sleeve': customer.sleeve_style or '',
            'back': customer.back_style or '',
            'length': customer.length_preference or '',
            'silhouette': customer.silhouette or '',
            'embellishments': customer.embellishments or '',
            'pattern': customer.pattern_style or '',
        },
        favourite_colours=[name for name, _ in colours.most_common(5)],
        preferred_fabrics=[name for name, _ in fabrics.most_common(5)],
        frequent_designs=[name for name, _ in designs.most_common(5)],
        previous_order_count=customer.orders.count(),
        custom_requirements=customer.custom_requirements or '',
    )


def load_context(customer_id, order_input=None):
    customer = (Customer.objects
                .select_related('measurements')
                .prefetch_related('orders', 'fabric_selections', 'design_preferences')
                .get(pk=customer_id))
    return customer, build_context(customer, order_input)
