"""Weekly gross pay, calculated from attendance and frozen once approved.

WHY THIS IS ITS OWN APP
=======================
Staff money and customer money are opposite directions of the same word, and
this codebase already keeps them apart everywhere else: an Order's columns are
what a customer OWES, and nothing here may touch them. Putting payroll beside
StaffProfile would also have put an Owner-only surface inside an app whose other
models are deliberately readable by the floor. A separate app makes that
boundary structural rather than a rule to remember, and gives payroll its own
migration set so a change here cannot disturb attendance.

There is no `boutique` column anywhere in this module. django-tenants gives each
boutique its own schema, so the tenant IS the table -- a boutique id on the row
would be a second, weaker answer to a question the connection already answers,
and a client-supplied one would be a way across the boundary.

WHAT A SNAPSHOT IS FOR
======================
An approved payroll must still explain itself in a year, after the rate has
changed twice, after attendance has been corrected, after the person has left.
So every number the calculation used is copied onto the record: the rate, the
minutes, the staff member's name, and a per-session breakdown of where the
minutes came from. Nothing here is re-derived from live data at read time. That
is the difference between a payroll record and a report.
"""

import uuid

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from crm_api.models import Tailor


class PayrollPeriod(models.Model):
    """One week of pay for the whole boutique.

    Monday to Sunday, in the boutique's own timezone -- the same week
    `apps.staff.attendance.week_start` already uses for timesheets. Sharing that
    definition is the point: a timesheet showing 42h and a payroll paying a
    different 42h would be the worst kind of bug, because both would look right
    on their own screen.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        APPROVED = 'APPROVED', 'Approved'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: The Monday. Unique, which is what makes generation idempotent: a second
    #: Generate for the same week finds this row rather than making another.
    period_start = models.DateField(db_index=True)
    period_end = models.DateField()

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_periods_created')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_periods_approved')

    class Meta:
        ordering = ['-period_start']
        constraints = [
            # One period per week, at the database. The service checks too, so
            # the normal path gets a sentence rather than an IntegrityError --
            # but two tabs pressing Generate together are decided here.
            models.UniqueConstraint(
                fields=['period_start'], name='payroll_period_unique_week'),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F('period_start')),
                name='payroll_period_ends_after_it_starts'),
        ]

    def __str__(self):
        return f"Payroll {self.period_start} to {self.period_end} ({self.status})"

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED


class PayrollRecord(models.Model):
    """What one staff member earned in one week, and how that was worked out.

    Every field below `staff` is a SNAPSHOT taken at generation. None of it is
    read back from StaffProfile or AttendanceSession when the record is
    displayed, which is what makes an approved row survive a later rate change
    or attendance correction with its arithmetic intact.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        APPROVED = 'APPROVED', 'Approved'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name='records')

    #: SET_NULL, not PROTECT. Deleting a roster member already works today
    #: (Order, OrderStage and ProductionTask all SET_NULL), and PROTECT here
    #: would newly break it -- a behaviour change this phase has no business
    #: making. The name and role are snapshotted beside it so a payroll run
    #: stays readable after the person is gone, which is the same trade
    #: superadmin.AuditLog and UniversalActivity already make.
    staff = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_records')
    staff_name_snapshot = models.CharField(max_length=150)
    staff_role_snapshot = models.CharField(max_length=50, blank=True, default='')

    #: NULL means the staff member had payable time but no usable rate. It is
    #: the flag as well as the value, deliberately: a separate `rate_missing`
    #: boolean would be a second fact about the same thing, and the two would
    #: eventually disagree. A null rate blocks approval of the whole period.
    hourly_rate_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])

    #: Completed attendance only. An open session contributes nothing.
    worked_minutes = models.PositiveIntegerField(default=0)
    #: Equal to worked_minutes for now. It exists because the moment overtime is
    #: a real concept the split has to be visible on historical records too, and
    #: adding the column later would leave every past row unable to say which
    #: half of its minutes were which.
    regular_minutes = models.PositiveIntegerField(default=0)

    gross_earnings = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])

    #: Sessions the person left open during this week. Not paid, and not
    #: silently ignored either -- the owner is shown the count and the days.
    open_session_count = models.PositiveIntegerField(default=0)
    #: Two completed sessions that overlap in time, which owner corrections can
    #: produce. Blocks approval rather than double-paying the overlap.
    has_overlap = models.BooleanField(default=False)

    #: Where the minutes came from: one entry per contributing session with the
    #: values as they were. This is what lets an approved record be explained
    #: after the underlying attendance has been corrected.
    session_breakdown = models.JSONField(default=list, blank=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_records_approved')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['staff_name_snapshot']
        constraints = [
            # One record per person per week. With staff SET_NULL this stops
            # constraining once a roster row is deleted, which is correct: a
            # deleted person is never regenerated, and the historical rows must
            # survive rather than collide.
            models.UniqueConstraint(
                fields=['period', 'staff'], name='payroll_record_unique_per_period'),
            models.CheckConstraint(
                condition=models.Q(gross_earnings__isnull=True)
                | models.Q(gross_earnings__gte=0),
                name='payroll_record_gross_not_negative'),
            models.CheckConstraint(
                condition=models.Q(hourly_rate_snapshot__isnull=True)
                | models.Q(hourly_rate_snapshot__gte=0),
                name='payroll_record_rate_not_negative'),
        ]

    def __str__(self):
        return f"{self.staff_name_snapshot} · {self.period.period_start} · {self.gross_earnings}"

    @property
    def rate_missing(self):
        return self.hourly_rate_snapshot is None

    @property
    def blocks_approval(self):
        """Why this record cannot be signed off, if it cannot.

        Both conditions are financial rather than cosmetic: paying a null rate
        means paying nothing to somebody who worked, and paying overlapping
        sessions means paying twice for one hour.
        """
        return self.rate_missing or self.has_overlap
