"""Profit & loss: the one place revenue and every cost meet.

Costs come from three sources, and only ONE of them is this app's own:

  * salaries  -- read from apps.payroll Payout rows (cash actually paid out)
  * inventory -- read from apps.inventory PurchaseOrder totals (committed POs)
  * manual    -- apps.finance Expense rows (rent, utilities, everything else)

Reading salaries and inventory from their own tables rather than copying them
into Expense is the whole point of "auto-feed": the number the owner sees here
is the same number payroll and purchasing already computed, so the three can
never drift, and nobody has to enter a cost twice.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

TWO_DP = Decimal('0.01')
ZERO = Decimal('0.00')

#: Purchase orders that represent real committed spend. A DRAFT is a basket
#: nobody has placed and a CANCELLED order never happened; counting either as
#: money spent would overstate what left the business.
_COMMITTED_PO = ('ORDERED', 'PARTIALLY_RECEIVED', 'RECEIVED')


def _money(value):
    return (Decimal(value or 0)).quantize(TWO_DP)


def _window(since, until):
    """Default to the current calendar month when nothing is asked for.

    A P&L with no period is not a useful number, and 'this month so far' is the
    figure an owner glances at most. Explicit since/until override it.
    """
    today = timezone.localdate()
    if since is None:
        since = today.replace(day=1)
    if until is None:
        until = today
    return since, until


def revenue_for(since, until):
    from crm_api.models import Order
    orders = Order.objects.filter(order_date__date__gte=since,
                                  order_date__date__lte=until)
    agg = orders.aggregate(
        paid=Sum('total_amount', filter=Q(payment_status='Paid')),
        partial=Sum('advance_paid', filter=Q(payment_status='Partially Paid')),
    )
    paid, partial = _money(agg['paid']), _money(agg['partial'])
    return {'total': paid + partial, 'paid_orders': paid,
            'partial_advances': partial}


def salaries_for(since, until):
    """Cash paid to staff in the window -- Payout rows, not accrued payroll.

    'Spent' means money that left, so this counts what was actually paid out,
    which is also what the owner watched happen on the payout screen. An
    approved-but-unpaid week has not been spent yet and is deliberately absent.
    """
    from apps.payroll.models import Payout
    total = Payout.objects.filter(paid_at__date__gte=since,
                                  paid_at__date__lte=until).aggregate(
        s=Sum('amount'))['s']
    return _money(total)


def inventory_for(since, until):
    """Committed purchase-order spend in the window.

    PurchaseOrder.total is a Python property (subtotal + tax, and subtotal sums
    a per-line property), so it cannot be a SQL Sum. The set of POs in a month
    is small, so iterating is fine; if purchasing volume ever makes this bite,
    the fix is a stored total column, not a cleverer query.
    """
    from apps.inventory.models import PurchaseOrder
    pos = PurchaseOrder.objects.filter(
        status__in=_COMMITTED_PO,
        # PurchaseOrder.order_date is a DateField (Order.order_date is a
        # DateTimeField -- same name, different type), so no __date transform.
        order_date__gte=since, order_date__lte=until,
    ).prefetch_related('lines')
    return _money(sum((Decimal(po.total) for po in pos), ZERO))


def manual_costs_for(since, until):
    from .models import Expense
    rows = (Expense.objects
            .filter(incurred_on__gte=since, incurred_on__lte=until)
            .values('category')
            .annotate(amount=Sum('amount'))
            .order_by('category'))
    labels = dict(Expense.Category.choices)
    breakdown = [{'category': r['category'],
                  'label': labels.get(r['category'], r['category']),
                  'amount': _money(r['amount'])} for r in rows]
    return breakdown, sum((b['amount'] for b in breakdown), ZERO)


def profit_and_loss(since=None, until=None):
    since, until = _window(since, until)
    revenue = revenue_for(since, until)
    salaries = salaries_for(since, until)
    inventory = inventory_for(since, until)
    manual, manual_total = manual_costs_for(since, until)

    total_costs = salaries + inventory + manual_total
    return {
        'window': {'since': since.isoformat(), 'until': until.isoformat()},
        'revenue': revenue,
        'costs': {
            'salaries': salaries,
            'inventory': inventory,
            'manual': manual,
            'manual_total': manual_total,
            'total': total_costs,
        },
        'profit': revenue['total'] - total_costs,
    }
