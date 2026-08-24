"""Template filters for customer-facing output.

Thin wrappers over core.formatting, which is also what the Python side of the
application calls directly. The template must not carry its own format strings:
`|date:"d M Y, g:i A"` in one place and `|floatformat:2` in another is how the
tracking page and the invoice came to describe the same order differently.
"""

from django import template

from core.formatting import format_date, format_datetime, format_money, format_time

register = template.Library()


@register.filter(name='inr')
def inr(value):
    """Rs49,875 -- lakh grouping, paise only when there are paise."""
    return format_money(value)


# Datetime tags take the tenant from the template context rather than the
# connection. The customer's tracking page runs inside schema_context, which
# binds a FakeTenant carrying only a schema name -- so a filter reading
# connection.tenant would find no timezone and quietly use the default. Passing
# it explicitly is what makes a non-Indian boutique render its own clock.
@register.simple_tag(takes_context=True)
def boutique_date(context, value):
    """24 Aug 2026, in the boutique's timezone."""
    return format_date(value, context.get('tenant'))


@register.simple_tag(takes_context=True)
def boutique_time(context, value):
    """3:00 PM, in the boutique's timezone."""
    return format_time(value, context.get('tenant'))


@register.simple_tag(takes_context=True)
def boutique_datetime(context, value):
    """24 Aug 2026, 3:00 PM, in the boutique's timezone."""
    return format_datetime(value, context.get('tenant'))
