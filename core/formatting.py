
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone as dj_timezone

DEFAULT_TIMEZONE = 'Asia/Kolkata'

DATE_FORMAT = '%d %b %Y'      # 24 Aug 2026
TIME_FORMAT = '%-I:%M %p'     # 3:00 PM


def tenant_timezone(tenant=None):
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
    if value is None:
        return None
    if isinstance(value, datetime):
        if dj_timezone.is_naive(value):
            value = value.replace(tzinfo=dt_timezone.utc)
        return value.astimezone(tenant_timezone(tenant))
    return value


def format_date(value, tenant=None):
    value = to_local(value, tenant)
    if value is None:
        return ''
    if isinstance(value, datetime) or isinstance(value, date):
        return value.strftime(DATE_FORMAT).lstrip('0')
    return str(value)


def format_time(value, tenant=None):
    value = to_local(value, tenant)
    if not isinstance(value, datetime):
        return ''
    return value.strftime(TIME_FORMAT)


def format_datetime(value, tenant=None):
    value = to_local(value, tenant)
    if not isinstance(value, datetime):
        return ''
    return f"{format_date(value, tenant)}, {format_time(value, tenant)}"


def group_indian(digits):
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
