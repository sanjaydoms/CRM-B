"""Validators shared by serializers in more than one app."""

from rest_framework import serializers

MOBILE_ERROR = 'Enter a 10-digit mobile number.'


def validate_mobile(value):
    """Blank, or exactly ten national digits -- normalised, not merely checked.

    Returns the number the way it will be stored, so "+91 98765 43210" and
    "9876543210" become one spelling of one person rather than two rows that
    fail to match. Anything that does not reduce to ten digits is refused with
    a sentence; a maxLength on the input is a courtesy to the typist, and this
    is the rule.

    crm_api.models is imported lazily: it is a tenant app, and this module has
    to stay importable before the app registry is ready.
    """
    if not value:
        return ''
    from crm_api.models import national_mobile
    national = national_mobile(value)
    if not national:
        raise serializers.ValidationError(MOBILE_ERROR)
    return national
