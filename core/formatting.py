"""How money and time are written down, in one place.

Two rules, and every customer-facing surface obeys both:

    money   INR, Indian (lakh) grouping, paise only when there are paise
    time    stored UTC, rendered in the boutique's own timezone

Neither is cosmetic. The tracking page printed a stage completed at 09:30 UTC
as "9:30 AM" to a customer in Chennai for whom it happened at 3:00 PM, and
printed the total as Rs49875.00 while the invoice for the same order said
Rs49,875. A customer comparing the two documents was looking at one order
described two ways.

The formatting lives here rather than in the templates because there is a
matching implementation in the browser (frontend/src/services/format.js) and
the two have to agree. Two conventions is the actual defect; one function per
side is the fix.
"""

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone as dj_timezone

#: What a boutique falls back to when its tenant row predates the timezone
#: field. Every boutique on the platform today is Indian, so this is the
#: honest default -- but it is a DEFAULT, read off the tenant, not a constant
#: baked into settings.TIME_ZONE where a second boutique could not override it.
DEFAULT_TIMEZONE = 'Asia/Kolkata'

DATE_FORMAT = '%d %b %Y'      # 24 Aug 2026
TIME_FORMAT = '%-I:%M %p'     # 3:00 PM


def tenant_timezone(tenant=None):
    """The ZoneInfo this boutique reads its clocks in.

    Falls back rather than raising: a bad or missing name must not take down
    the customer's tracking page, and UTC-shaped output is a smaller failure
    than no page at all.
    """
    name = DEFAULT_TIMEZONE
    if tenant is None:
        from django.db import connection
        tenant = getattr(connection, 'tenant', None)
    candidate = (getattr(tenant, 'timezone', '') or '').strip()
    if candidate:
        name = candidate
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        try:
            return ZoneInfo(DEFAULT_TIMEZONE)
        except Exception:
            return dt_timezone.utc


def to_local(value, tenant=None):
    """Move an aware datetime into the boutique's timezone. UTC stays stored."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if dj_timezone.is_naive(value):
            value = value.replace(tzinfo=dt_timezone.utc)
        return value.astimezone(tenant_timezone(tenant))
    return value


def format_date(value, tenant=None):
    """24 Aug 2026."""
    value = to_local(value, tenant)
    if value is None:
        return ''
    if isinstance(value, datetime) or isinstance(value, date):
        return value.strftime(DATE_FORMAT).lstrip('0')
    return str(value)


def format_time(value, tenant=None):
    """3:00 PM, in the boutique's timezone."""
    value = to_local(value, tenant)
    if not isinstance(value, datetime):
        return ''
    return value.strftime(TIME_FORMAT)


def format_datetime(value, tenant=None):
    """24 Aug 2026, 3:00 PM."""
    value = to_local(value, tenant)
    if not isinstance(value, datetime):
        return ''
    return f"{format_date(value, tenant)}, {format_time(value, tenant)}"


def group_indian(digits):
    """Indian digit grouping: last three, then twos. 1234567 -> 12,34,567.

    Written out rather than taken from a locale. Python's own thousands
    separator is Western (1,234,567) and Django's humanize follows the active
    locale, which is a setting a long way from here; meanwhile the browser side
    uses toLocaleString('en-IN') and produces lakh grouping unconditionally.
    The two halves of one invoice have to agree, so this is explicit.
    """
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ','.join(parts) + ',' + tail


def format_money(value, symbol='₹'):
    """Rs49,875 -- and Rs49,875.50 only when there are actually paise.

    Trailing .00 on every figure is what made the tracking page read like a
    machine and disagree with the invoice beside it. Paise are shown when they
    exist, because then they are part of what is owed.
    """
    try:
        amount = Decimal(str(value if value not in (None, '') else 0))
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal('0')

    negative = amount < 0
    amount = abs(amount).quantize(Decimal('0.01'))
    whole, _, paise = str(amount).partition('.')
    text = group_indian(whole)
    if paise and int(paise):
        text = f"{text}.{paise}"
    return f"{'-' if negative else ''}{symbol}{text}"
