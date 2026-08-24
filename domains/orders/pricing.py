"""The one calculation path for order money.

Every rupee figure the system shows -- step-5 summary, invoice, payments,
tracking, WhatsApp, analytics -- reads Order's financial columns. Those columns
used to be written straight from one flat set of client-side prices, which is
how a Blouse + Lehenga order came to be priced as whichever garment the
customer profile happened to name. Now each GarmentJob carries its own
components and this module is the only place that turns them into order totals:

    GarmentJob (base + fabric + embroidery + customization + tailoring)
        -> per-garment subtotal
    + Order.packaging_handling         (one parcel, order-level)
    - Order.discount                   (order-level)
    -> taxable subtotal
    * TAX_RATE
    -> Order.taxes, Order.total_amount

Order's component columns become the SUM across jobs -- a derived rollup, kept
because seven read surfaces already consume them and every one of them stays
correct without change. There is deliberately no second implementation of any
of this arithmetic: the wizard's preview may display its own sums, but nothing
the client sends for taxes or total is ever stored (create_order_for_customer
recomputes), and any future path that edits a job's price must end by calling
recompute_order_totals.

Legacy orders -- jobs created before pricing existed, carrying all-zero
components -- are left exactly as entered: recompute runs only where the
confirm path (or a future editor) invokes it, so history is never rewritten
and an old single-price order is never artificially split across garments.
"""

from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal('0.05')

#: Order.total_amount is DecimalField(max_digits=10, places=2); refuse anything
#: the column cannot hold with a message a human can act on.
MAX_TOTAL = Decimal('99999999')

#: The per-garment components, in the order the invoice prints them. The names
#: match both GarmentJob's and Order's columns, which is what lets the rollup
#: be a loop rather than a hand-maintained mapping.
JOB_COMPONENTS = (
    'base_price', 'fabric_price', 'embroidery_price',
    'customization_price', 'tailoring_charges',
)

TWO_PLACES = Decimal('0.01')


def to_money(value):
    """A Decimal at two places from whatever the payload held. Garbage is 0."""
    try:
        return Decimal(str(value if value not in (None, '') else 0)).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0.00')


def job_subtotal(job):
    return sum((getattr(job, f) or Decimal('0')) for f in JOB_COMPONENTS)


def validate_components(components, label=''):
    """Negative money is always a typo. Raise the same ValueError shape the
    order service already surfaces as a 400."""
    prefix = f'{label}: ' if label else ''
    for field, value in components.items():
        if value < 0:
            raise ValueError(f'{prefix}{field} cannot be negative.')


def totals_from_amounts(component_sums, packaging, discount):
    """The arithmetic, once: component sums -> (subtotal, taxes, total).

    `subtotal` is goods before tax and after discount. Discount larger than the
    goods is refused rather than clamped -- a negative bill is a typo, not a
    refund mechanism.
    """
    goods = sum(component_sums.values()) + packaging
    if discount > goods:
        raise ValueError('Discount cannot exceed the order subtotal.')
    subtotal = goods - discount
    taxes = (subtotal * TAX_RATE).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    total = subtotal + taxes
    if total > MAX_TOTAL:
        raise ValueError(
            'Order total exceeds the maximum this system can record '
            '(99,999,999). Check the prices entered.')
    return subtotal, taxes, total


def recompute_order_totals(order, jobs=None):
    """Write Order's financial columns from its garment jobs. Returns the order.

    The single point of truth for a priced order: whatever a job's components
    say, this is what makes them the bill. Payment fields are deliberately not
    touched -- money received is history, not arithmetic.
    """
    if jobs is None:
        jobs = list(order.garment_jobs.all())
    sums = {
        field: sum((to_money(getattr(job, field)) for job in jobs), Decimal('0.00'))
        for field in JOB_COMPONENTS
    }
    # to_money, not a bare read: an order created in this same transaction still
    # holds the float it was constructed with -- only a refetch would hold the
    # column's Decimal -- and float + Decimal is a TypeError.
    packaging = to_money(order.packaging_handling)
    discount = to_money(order.discount)
    _, taxes, total = totals_from_amounts(sums, packaging, discount)

    for field, value in sums.items():
        setattr(order, field, value)
    order.taxes = taxes
    order.total_amount = total
    order.save(update_fields=[*JOB_COMPONENTS, 'taxes', 'total_amount'])
    return order
