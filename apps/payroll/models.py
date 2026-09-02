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

    # ---- Security deposit, snapshotted the same way the gross figures are ----
    #
    # Four numbers rather than one, because "we took 300" does not answer the
    # question an owner asks three months later. Together these say: this is what
    # the terms called for, this is what the week could actually bear, this is
    # what was therefore missed, and this is where the obligation stood on either
    # side of it. Deriving any of them from StaffProfile at read time would break
    # the moment the terms changed.
    deposit_scheduled = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="What this week was due to recover -- the weekly terms, "
                  "already limited to what is still owed.")
    deposit_recovered = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="What was actually taken -- never more than the obligation "
                  "outstanding, and never more than the week's gross.")
    #: Scheduled minus recovered. Kept as its own column rather than recomputed,
    #: because it is the number nobody must be allowed to lose: a week that could
    #: only bear 300 of a 500 recovery has missed 200, and quietly rewriting the
    #: schedule to 300 would erase that fact from the record.
    deposit_unrecovered = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Scheduled recovery this week could not collect.")
    deposit_balance_before = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    deposit_balance_after = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)

    #: Gross less the deposit recovery. Deliberately NOT called net pay: advances,
    #: bonuses and other deductions are later phases, and a column named for a
    #: payout it does not yet represent is a column somebody will pay from.
    net_before_other_deductions = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])

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
            # Wages cannot go negative. The service clamps the recovery to the
            # week's gross, and this is the database refusing to store the
            # result if that clamp is ever wrong.
            models.CheckConstraint(
                condition=models.Q(net_before_other_deductions__isnull=True)
                | models.Q(net_before_other_deductions__gte=0),
                name='payroll_record_net_not_negative'),
            models.CheckConstraint(
                condition=models.Q(deposit_recovered__gte=0),
                name='payroll_record_deposit_recovered_not_negative'),
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


class StaffLedgerEntry(models.Model):
    """One immutable line of a staff member's financial history.

    Modelled on the PRINCIPLES of inventory's StockMovement -- append-only, a
    balance either side of the movement, an actor, a provenance reference -- and
    on none of its stock-specific fields. What both share is the property that
    matters: the current position is the sum of the history, never a column
    somebody can edit.

    WHY THE OBLIGATION IS NOT A COLUMN
    ==================================
    `StaffProfile.deposit_total` is the AGREEMENT -- what was promised. It is
    emphatically not the balance. A boutique that stored "remaining" as a
    mutable number would have two answers to "how much is still owed" the first
    time a recovery was written without updating it, and no way to tell which
    was right. Here the remaining obligation is `agreed - recovered`, both
    derived from rows nobody edits.

    HOW A CHANGE OF TERMS WORKS
    ===========================
    Every DEPOSIT_AGREED row carries the total as it stood FROM THAT MOMENT, and
    the newest one wins. Changing 5,000 to 3,000 writes a second row; it does not
    touch the first, and it does not touch a single recovery already taken. So a
    staff member who had 2,000 recovered against a 5,000 agreement and is moved
    to a 3,000 agreement now owes 1,000, and the ledger still shows exactly why.

    Storing the new TOTAL rather than a delta is what keeps `amount` a magnitude
    and lets the database refuse negatives outright. A delta would have to be
    signed, and a signed amount column is one typo away from a recovery that
    increases somebody's debt.

    BUILT TO GROW
    =============
    Advances, bonuses, refunds and payouts are later phases and are deliberately
    absent -- but they are all the same shape as these two rows, so they arrive
    as new `entry_type` values against the same table rather than as a redesign.
    """

    class EntryType(models.TextChoices):
        #: "The agreed deposit is now X." The newest one is the live agreement.
        DEPOSIT_AGREED = 'DEPOSIT_AGREED', 'Security deposit agreed'
        #: "X was actually recovered from this payroll." Always tied to the
        #: approved payroll record that caused it.
        DEPOSIT_RECOVERY = 'DEPOSIT_RECOVERY', 'Security deposit recovered'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: SET_NULL plus a name snapshot, matching PayrollRecord: deleting a roster
    #: member already works everywhere else in this product, and financial
    #: history must outlive the person it concerns.
    staff = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ledger_entries')
    staff_name_snapshot = models.CharField(max_length=150)

    entry_type = models.CharField(
        max_length=24, choices=EntryType.choices, db_index=True)

    #: Always a magnitude, never signed. The type says which direction it moves
    #: the obligation, and the database refuses anything below zero.
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    #: The outstanding obligation either side of this row, so the history can be
    #: read without re-deriving every earlier line -- and so a mistake in the
    #: derivation is visible rather than silent.
    balance_before = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    #: The approved payroll this recovery came out of. Null for an agreement
    #: row, which is not caused by a payroll. The unique constraint below hangs
    #: off this: it is what makes one payroll able to recover exactly once.
    payroll_record = models.ForeignKey(
        'PayrollRecord', on_delete=models.PROTECT, null=True, blank=True,
        related_name='ledger_entries')

    note = models.CharField(max_length=255, blank=True, default='')
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff_ledger_entries')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['staff', 'entry_type', 'created_at'],
                         name='ledger_staff_type_time'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name='ledger_amount_not_negative'),
            # ONE recovery per payroll record, at the database. Generation is
            # repeatable and approval can be retried from two tabs, so "do not
            # recover twice" cannot be a rule the service merely remembers.
            # Agreement rows have a null payroll_record and are unaffected,
            # because Postgres does not treat two nulls as equal.
            models.UniqueConstraint(
                fields=['payroll_record'],
                condition=models.Q(entry_type='DEPOSIT_RECOVERY'),
                name='ledger_one_recovery_per_payroll'),
            # A recovery must name the payroll that caused it; an agreement must
            # not pretend one did.
            models.CheckConstraint(
                condition=(
                    models.Q(entry_type='DEPOSIT_RECOVERY',
                             payroll_record__isnull=False)
                    | ~models.Q(entry_type='DEPOSIT_RECOVERY')),
                name='ledger_recovery_names_its_payroll'),
        ]

    def __str__(self):
        return (f"{self.staff_name_snapshot} · {self.get_entry_type_display()} "
                f"· {self.amount}")
