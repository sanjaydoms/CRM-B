"""Employment terms for someone already on the boutique's roster.

The roster itself is `crm_api.Tailor` and stays there. That model is the
operational identity -- it is what an order is assigned to, what a stage is
performed by, what a stock movement is credited to -- and seven other models
point at it. Nothing here replaces it.

WHY THIS IS A SEPARATE TABLE
============================
Employment terms could have been columns on Tailor, and that would have been the
smaller change. It would also have leaked every colleague's wage.

TailorSerializer is `fields = '__all__'` and TailorViewSet has no queryset
scoping, so the roster is readable by every signed-in staff member; the
serializer pops `email` and `user` for non-owners and nothing else. An
`hourly_rate` column on Tailor is therefore readable by the whole floor from the
day it is added, and stays readable until somebody remembers to extend that pop
list -- which is a thing to remember rather than a thing the code enforces.

Kept here, with its own Owner-scoped serializer and queryset, that leak is not
something to remember. There is no path from TailorSerializer to these columns.

WHAT IS DELIBERATELY ABSENT
===========================
`deposit_balance`. The remaining deposit is the sum of a staff member's ledger
entries and is derived from them, never stored here -- the same rule
StockMovement already applies to stock. A mutable balance column would become a
second answer to "how much is left", and the two would drift the first time a
deduction was written without updating it. The ledger arrives in its own phase;
until then `deposit_total` and `deposit_weekly` are terms, not balances.
"""

import uuid

from django.core.validators import MinValueValidator
from django.db import models

from crm_api.models import Tailor


class StaffProfile(models.Model):
    """One roster member's employment terms. Optional, and created on request.

    A Tailor without one of these is a perfectly normal staff member who has not
    had their employment details filled in -- they keep working exactly as
    before. Nothing here is auto-created, because conjuring an employment record
    with a zero rate for everybody would put twenty people into a future payroll
    run that nobody agreed to.
    """

    class EmploymentType(models.TextChoices):
        FULL_TIME = 'FULL_TIME', 'Full time'
        PART_TIME = 'PART_TIME', 'Part time'
        CONTRACT = 'CONTRACT', 'Contract'
        APPRENTICE = 'APPRENTICE', 'Apprentice'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: The roster member these terms belong to. CASCADE because employment terms
    #: for a deleted staff member are not a thing anyone can use, and OneToOne
    #: because a person has one set of terms at a time.
    staff = models.OneToOneField(
        Tailor, on_delete=models.CASCADE, related_name='staff_profile')

    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME, db_index=True)
    joined_at = models.DateField(null=True, blank=True)
    #: Set when someone leaves. The row stays: their payroll history has to
    #: remain readable, and deleting the terms would orphan it.
    exit_date = models.DateField(null=True, blank=True)

    #: Money is Decimal everywhere in this module. `domains/orders/pricing.py`
    #: is the house rule and the reason for it -- float cannot hold 0.05
    #: exactly, and wages are not a place to discover that.
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Pay per hour. Payroll skips anyone whose rate is unset.")
    weekly_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Expected hours a week. Reference only; payroll pays "
                  "attendance, not this.")

    #: The agreed deposit and what comes off each week. Per staff member, not a
    #: global constant: two tailors hired in different months have different
    #: terms, and a single setting would rewrite history for both.
    deposit_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Security deposit agreed with this staff member.")
    deposit_weekly = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Scheduled weekly recovery. Never recovers more than the "
                  "balance outstanding or the week's earnings.")

    phone = models.CharField(max_length=20, blank=True, default='')
    emergency_contact = models.CharField(max_length=150, blank=True, default='')
    address = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['staff__name']
        constraints = [
            # At the database, not only in the serializer. A negative rate or a
            # negative deposit is not a validation preference -- it is a value
            # that would invert a payroll calculation, and the ORM is not the
            # only thing that writes rows (seed scripts, the admin, a shell).
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gte=0),
                name='staff_profile_hourly_rate_not_negative'),
            models.CheckConstraint(
                condition=models.Q(deposit_total__gte=0),
                name='staff_profile_deposit_total_not_negative'),
            models.CheckConstraint(
                condition=models.Q(deposit_weekly__gte=0),
                name='staff_profile_deposit_weekly_not_negative'),
            models.CheckConstraint(
                condition=models.Q(weekly_hours__gte=0),
                name='staff_profile_weekly_hours_not_negative'),
        ]

    def __str__(self):
        return f"Employment terms for {self.staff.name}"
