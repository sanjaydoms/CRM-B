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

from django.contrib.auth.models import User
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


class AttendanceSession(models.Model):
    """One stretch of time a staff member was actually at work.

    WHY THIS EXISTS AT ALL
    ======================
    Nothing in this product measured attended time before it, and the two
    columns that look like they might are both traps:

      * `OrderStage.duration_seconds` is wall-clock elapsed between a stage
        starting and finishing. A stage begun on Friday and finished on Monday
        reads as 72 hours. It is a throughput metric and paying it would pay
        people for the weekend.
      * `ProductionTask.actual_hours` exists and nothing has ever written to it.

    A login is not attendance either. A DRF token has no expiry in this product,
    so "signed in" can mean "signed in three weeks ago on a phone in a drawer".
    Attendance is a thing somebody DOES, so it gets its own record.

    WHAT ONE ROW MEANS
    ==================
    Check-in to check-out, and nothing else. Breaks are deliberately not
    modelled: a boutique with one tea break does not need a break subsystem, and
    when one is wanted it arrives as its own rows pointing at this session
    rather than as a redesign of it -- `minutes` stays "time between the two
    stamps" either way, and a break table would subtract from it downstream.

    `date` IS NOT `check_in.date()`
    ==============================
    It is the boutique's OWN date for the shift, derived through
    core.formatting.to_local, because timestamps are stored in UTC and a
    boutique in Asia/Kolkata checking in at 09:05 local is 03:35 UTC on the same
    day -- but one checking in at 23:30 local is 18:00 UTC, and an 05:30 start
    in Kolkata is 00:00 UTC of the day BEFORE. Grouping a timesheet by the UTC
    date would file a morning shift under yesterday for every boutique east of
    Greenwich. Stored rather than computed on read so that a week's aggregation
    is an indexed column, not fifteen timezone conversions.

    An overnight session keeps the date it STARTED on. Somebody who begins at
    23:00 on Sunday and leaves at 07:00 on Monday worked Sunday night's shift,
    and `minutes` spans the boundary without caring.
    """

    class Source(models.TextChoices):
        SELF = 'SELF', 'Recorded by the staff member'
        OWNER = 'OWNER', 'Recorded by the boutique owner'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    staff = models.ForeignKey(
        Tailor, on_delete=models.CASCADE, related_name='attendance_sessions')

    #: The boutique-local day this shift belongs to. See the class docstring.
    date = models.DateField(db_index=True)

    check_in = models.DateTimeField()
    #: Null while the session is open. That is also what "currently working"
    #: means, and what the partial unique constraint below keys on.
    check_out = models.DateTimeField(null=True, blank=True)

    #: Whole minutes, written once at check-out. An integer rather than a float
    #: or a DurationField because this is what Phase 4 multiplies by a rate, and
    #: 8.4 hours cannot be represented exactly in binary floating point. Null
    #: while the session is open -- an unfinished shift has no duration yet, and
    #: storing 0 would make it look like somebody worked none.
    minutes = models.PositiveIntegerField(null=True, blank=True)

    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.SELF, db_index=True)
    note = models.TextField(blank=True, default='')

    #: Who actually wrote the row -- the staff member themselves, or the owner
    #: entering it on their behalf. SET_NULL so a departed manager's corrections
    #: stay readable.
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attendance_recorded')

    #: The stamps as they were BEFORE anybody corrected them. Written once, on
    #: the first correction, and never overwritten -- so "what did this say
    #: originally" survives a second and third correction. The step-by-step
    #: history of repeated corrections lives in UniversalActivity, which already
    #: carries old_value/new_value for exactly this; these two columns are the
    #: part that must not depend on an activity row still existing.
    original_check_in = models.DateTimeField(null=True, blank=True)
    original_check_out = models.DateTimeField(null=True, blank=True)
    corrected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attendance_corrected')
    corrected_at = models.DateTimeField(null=True, blank=True)
    correction_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-check_in']
        indexes = [
            # The two queries this table exists to serve: one person's week,
            # and the whole boutique's day.
            models.Index(fields=['staff', '-date'], name='attendance_staff_day'),
            models.Index(fields=['date'], name='attendance_day'),
        ]
        constraints = [
            # ONE open session per person, enforced by Postgres rather than by
            # remembering to check. A double check-in is not a validation
            # nicety: two open sessions make "how many hours today" ambiguous,
            # and the answer feeds wages. The view checks too, so the normal
            # path gets a sentence instead of an IntegrityError -- but the
            # constraint is what holds when two taps race.
            models.UniqueConstraint(
                fields=['staff'], condition=models.Q(check_out__isnull=True),
                name='attendance_one_open_session_per_staff'),
            # A shift cannot end before it starts. Guards the owner-entered and
            # corrected paths, where the times are typed rather than stamped.
            models.CheckConstraint(
                condition=models.Q(check_out__isnull=True)
                | models.Q(check_out__gte=models.F('check_in')),
                name='attendance_ends_after_it_starts'),
            models.CheckConstraint(
                condition=models.Q(minutes__isnull=True) | models.Q(minutes__gte=0),
                name='attendance_minutes_not_negative'),
        ]

    def __str__(self):
        return f"{self.staff.name} on {self.date}"

    @property
    def is_open(self):
        return self.check_out is None

    def duration_minutes(self):
        """Whole minutes between the stamps, or None while still open.

        Spans midnight without special-casing it, because subtracting two aware
        datetimes already does: this is the whole reason check_out is a full
        timestamp rather than a time-of-day.
        """
        if self.check_out is None:
            return None
        seconds = (self.check_out - self.check_in).total_seconds()
        return max(0, int(seconds // 60))
