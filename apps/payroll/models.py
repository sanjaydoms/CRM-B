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
        #: Settled. Reached only from APPROVED, only by the owner, only through
        #: payouts.record_payout, and never left again.
        PAID = 'PAID', 'Paid'

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

    #: Gross less the deposit recovery. Kept under its Phase 5 name: the column
    #: means "what is left for the next deduction to draw on", which is exactly
    #: what advance recovery reads, and renaming a money column on approved
    #: history is not a thing this app does.
    net_before_other_deductions = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])

    # ---- Advance recovery, the second deduction, snapshotted like the first --
    #
    # Deduction order is fixed and documented in services.py: deposit first,
    # then advance, each drawing only on what the previous one left. These
    # columns record what THIS week did against ONE advance -- the oldest still
    # outstanding, by rule -- so a recovery can always say which advance it
    # reduced and what that advance's balance was on either side of it.
    advance_recovered_from = models.ForeignKey(
        'StaffAdvance', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_records')
    advance_scheduled = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="What the advance's weekly rule called for, limited to what "
                  "was still outstanding on it.")
    advance_recovered = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="What was actually taken -- never more than the advance "
                  "outstanding, never more than what the deposit left.")
    advance_unrecovered = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Scheduled advance recovery this week could not collect.")
    advance_balance_before = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    advance_balance_after = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)

    #: The figure that is actually paid. Gross, less deposit, less advance.
    #: This is the one column a payout may equal, and it may equal nothing else.
    net_payable = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])

    paid_at = models.DateTimeField(null=True, blank=True)

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
            models.CheckConstraint(
                condition=models.Q(advance_recovered__gte=0),
                name='payroll_record_advance_recovered_not_negative'),
            # The final invariant, at the database: net pay is never negative.
            models.CheckConstraint(
                condition=models.Q(net_payable__isnull=True)
                | models.Q(net_payable__gte=0),
                name='payroll_record_net_payable_not_negative'),
        ]

    def __str__(self):
        return f"{self.staff_name_snapshot} · {self.period.period_start} · {self.gross_earnings}"

    @property
    def rate_missing(self):
        return self.hourly_rate_snapshot is None

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

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
        #: "The boutique gave this person X." Creates the obligation.
        ADVANCE_ISSUED = 'ADVANCE_ISSUED', 'Advance issued'
        #: "X of an advance was taken back from this payroll." Tied to both the
        #: payroll record and the advance it reduced.
        ADVANCE_RECOVERY = 'ADVANCE_RECOVERY', 'Advance recovered'
        #: A reversal of an ADVANCE_ISSUED entered in error, permitted only
        #: before anything has been recovered against it. An offset row rather
        #: than a deletion: the mistake and its correction both stay readable.
        ADVANCE_CANCELLED = 'ADVANCE_CANCELLED', 'Advance cancelled'

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
    #: The advance this row is about. Set on every ADVANCE_* row and on nothing
    #: else, so an advance's whole history is one filter and a recovery can
    #: never be ambiguous about which obligation it reduced.
    advance = models.ForeignKey(
        'StaffAdvance', on_delete=models.PROTECT, null=True, blank=True,
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
            # ONE advance recovery per payroll record. The deduction rule takes
            # from a single advance each week, so this is the whole double-
            # recovery guard for advances, enforced where retries cannot reach.
            models.UniqueConstraint(
                fields=['payroll_record'],
                condition=models.Q(entry_type='ADVANCE_RECOVERY'),
                name='ledger_one_advance_recovery_per_payroll'),
            # Every advance row names its advance; an advance recovery also
            # names its payroll. Neither can be inferred later.
            models.CheckConstraint(
                condition=(
                    ~models.Q(entry_type__in=['ADVANCE_ISSUED', 'ADVANCE_RECOVERY',
                                              'ADVANCE_CANCELLED'])
                    | models.Q(advance__isnull=False)),
                name='ledger_advance_rows_name_their_advance'),
            models.CheckConstraint(
                condition=(
                    ~models.Q(entry_type='ADVANCE_RECOVERY')
                    | models.Q(payroll_record__isnull=False)),
                name='ledger_advance_recovery_names_its_payroll'),
            # ONE reversal per advance. A double-tapped Cancel is decided here,
            # not by whichever request happened to read ACTIVE first.
            models.UniqueConstraint(
                fields=['advance'],
                condition=models.Q(entry_type='ADVANCE_CANCELLED'),
                name='ledger_one_cancel_per_advance'),
        ]

    def __str__(self):
        return (f"{self.staff_name_snapshot} · {self.get_entry_type_display()} "
                f"· {self.amount}")


class StaffAdvance(models.Model):
    """Money the boutique handed a staff member ahead of payroll.

    Not salary, not a bonus, not the security deposit. It is an obligation the
    OTHER way round from the deposit: the deposit is money the boutique holds
    for the person, an advance is money the person holds for the boutique.
    They are never netted against each other, and each has its own ledger rows,
    its own recovery rule and its own balance.

    The row here is the AGREEMENT -- amount, date, reason, weekly rule. What is
    still outstanding is derived from ledger rows (ADVANCE_ISSUED minus
    ADVANCE_RECOVERY minus ADVANCE_CANCELLED) and lives nowhere as a column.

    Each advance is its own obligation rather than a running "advance balance"
    per person, because the recovery rule is oldest-first and a single balance
    cannot say which loan a rupee paid back. `weekly_recovery` belongs to the
    advance, not the profile, for the same reason: two advances can carry two
    different repayment terms.

    `status` is deliberately only ACTIVE or CANCELLED. "Fully recovered" is a
    fact about the ledger, not a state somebody sets, and storing it would be a
    second answer that drifts.
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        CANCELLED = 'CANCELLED', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='advances')
    staff_name_snapshot = models.CharField(max_length=150)

    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    #: The rule, changeable prospectively. Zero means "recover nothing yet".
    weekly_recovery = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)])
    issued_on = models.DateField(db_index=True)
    reason = models.CharField(max_length=255, blank=True, default='')

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='advances_issued')
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='advances_cancelled')
    cancel_reason = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        # Oldest first is the recovery order, so it is the default order too.
        ordering = ['issued_on', 'created_at', 'pk']
        constraints = [
            # An advance of nothing is a data-entry error, not an obligation.
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='advance_amount_positive'),
            models.CheckConstraint(
                condition=models.Q(weekly_recovery__gte=0),
                name='advance_weekly_not_negative'),
        ]

    def __str__(self):
        return f"{self.staff_name_snapshot} · advance {self.amount} on {self.issued_on}"

    @property
    def is_cancelled(self):
        return self.status == self.Status.CANCELLED


class Payout(models.Model):
    """The record that an approved payroll was actually settled.

    This product moves no money. There is no bank, no gateway, no UPI -- the
    owner pays in cash or from their own banking app and records it here. The
    row says "paid, this much, this way, this reference, by me, at this time",
    and the interface says "payment recorded", never "transfer completed".

    OneToOne with the payroll record IS the idempotency: a second payout for the
    same payroll is a database error, not a rule the service remembers. And the
    amount is never typed -- it is copied from the record's net_payable inside
    the same transaction that marks it PAID, so what was paid and what was owed
    cannot disagree.
    """

    class Method(models.TextChoices):
        CASH = 'CASH', 'Cash'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank transfer'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_record = models.OneToOneField(
        PayrollRecord, on_delete=models.PROTECT, related_name='payout')
    staff = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payouts')
    staff_name_snapshot = models.CharField(max_length=150)

    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    method = models.CharField(max_length=20, choices=Method.choices)
    #: UTR, cash voucher number, or whatever the owner has. Free text, because
    #: the reference space is theirs, and never invented by this system.
    reference = models.CharField(max_length=120, blank=True, default='')
    note = models.CharField(max_length=255, blank=True, default='')

    paid_at = models.DateTimeField()
    paid_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payouts_recorded')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name='payout_amount_not_negative'),
        ]

    def __str__(self):
        return f"{self.staff_name_snapshot} · paid {self.amount} ({self.method})"
