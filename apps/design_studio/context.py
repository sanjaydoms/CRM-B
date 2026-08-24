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
class Subject:
    """Who a garment is being designed for, and what they have chosen before.

    The source-neutral middle of the personalisation path, and the reason this
    module has one context builder rather than two.

    A saved Customer and an unconfirmed OrderDraft hold the same facts under the
    same names -- the wizard's form is modelled on the Customer table -- so the
    difference between "this person exists" and "this person is still being
    typed" is resolved HERE, by two small constructors, and nowhere downstream.
    build_context, the query generator, the ranker and every provider see one
    shape and never learn which source it came from.

    Doing it any other way means an `if customer_id else draft` at every layer
    that touches personalisation, which is how the two paths start disagreeing
    about what a customer is.

    `history` is real for a saved customer and empty for a draft. Empty is the
    correct answer for someone who has not ordered before, not a degraded one:
    a first-time customer genuinely has no favourite colour.
    """

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
    """A saved customer: profile, measurements and real purchase history."""
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
    """An order still being written: the same facts, none of them saved yet.

    Reads the draft payload the wizard already stores -- the customer form is
    spread across its top level -- so nothing new has to be captured and no
    Customer row has to exist for the studio to personalise. That row is minted
    once, at Confirm, and until then this is the whole of what is known.

    History is deliberately empty. A draft for a returning customer carries the
    customer id, and callers resolve that to the saved subject instead; a draft
    with no customer is a person with no past, which is the truth.
    """
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


#: Which garment-spec answers override which stored style preference. The
#: garment's own spec is what distinguishes a blouse from the lehenga beside it
#: on the same order -- the customer's saved defaults are identical for both --
#: so where a job has answered, its answer wins. Keys are the template
#: vocabulary (see apps/catalog/definitions.py: sleeve_and_neck).
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
    """Build the personalisation context for one garment.

    Takes a Subject, not a Customer: see that class for why the source of the
    facts is resolved before this point rather than inside it.

    ``order_input`` is what is being made right now -- garment type, occasion,
    budget, timeline, and the garment's own ``spec``. It wins over the
    subject's stored defaults, because it describes this dress rather than this
    person's usual taste. The spec overlay is what keeps a two-garment order
    honest: both garments share one customer and therefore one set of saved
    preferences, and only the job's own answers tell the blouse from the
    lehenga.
    """
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
            # Booleans are excluded on purpose. Several template fields with
            # style-sounding names are yes/no questions -- a lehenga's `border`
            # is a checkbox, a saree's is a choice of border -- and folding one
            # in would hand the ranker "pattern: True", which is not a style
            # preference and matches nothing. The garment's real style signals
            # are its selects and free text.
            if isinstance(value, bool):
                continue
            if value not in (None, '', [], {}):
                style_preferences[style_key] = (
                    ', '.join(str(v) for v in value) if isinstance(value, list)
                    else str(value))
                break

    # Measurements taken for THIS garment beat the customer's standing ones for
    # the same reason: a blouse is measured at the chest it is being cut to.
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
