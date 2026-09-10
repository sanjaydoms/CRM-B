
from django import template

from core.formatting import format_date, format_datetime, format_money, format_time

register = template.Library()


@register.filter(name='inr')
def inr(value):

    return format_money(value)


@register.simple_tag(takes_context=True)
def boutique_date(context, value):

    return format_date(value, context.get('tenant'))


@register.simple_tag(takes_context=True)
def boutique_time(context, value):

    return format_time(value, context.get('tenant'))


@register.simple_tag(takes_context=True)
def boutique_datetime(context, value):

    return format_datetime(value, context.get('tenant'))
