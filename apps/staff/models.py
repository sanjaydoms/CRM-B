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

    #: SET_NULL, and the snapshot below is why it can be.
    #:
    #: This was CASCADE, so removing somebody from the roster deleted every
    #: shift they had ever worked -- including the shifts an APPROVED, PAID
    #: payslip was computed from. The payslip survived (PayrollRecord is
    #: SET_NULL with its own snapshots, as is every other Phase 4-7 record) and
    #: the hours behind it did not, so the boutique kept the money and lost the
    #: evidence. Dismissing somebody destroyed the answer to "why was this
    #: amount paid".
    #:
    #: Nulling instead keeps the row and detaches it, which is also what makes
    #: an orphaned session unpayable for ever: every payroll query selects by
    #: `staff=<profile>`, and a null matches no profile -- so a deleted-then-
    #: rehired person cannot have their old hours swept into a new week.
    staff = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attendance_sessions')

    #: Who this shift belonged to, as at the moment it was recorded.
    #:
    #: The same trade PayrollRecord, StaffLedgerEntry, StaffAdvance, Payout and
    #: StaffPerformanceReview all make: a nullable FK for the live link and a
    #: frozen copy of the identity beside it, so the row still explains itself
    #: once the roster row is gone. Written once, at creation, and never
    #: rewritten -- a promotion or a change of name must not silently rewrite
    #: what last March's timesheet says.
    staff_name_snapshot = models.CharField(max_length=150, blank=True, default='')
    staff_role_snapshot = models.CharField(max_length=50, blank=True, default='')

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
        return f"{self.staff_label} on {self.date}"

    @property
    def staff_label(self):
        """The live name while the roster row exists, the frozen one after.

        Operational screens should say who somebody is NOW -- a rename should
        show up on this week's timesheet -- so the live row wins while there is
        one. The snapshot is the fallback that keeps a detached row readable,
        and it is the column that must never change; which of the two is
        DISPLAYED is a separate question from which is STORED.
        """
        if self.staff is not None:
            return self.staff.name
        return self.staff_name_snapshot or 'Former staff member'

    def save(self, *args, **kwargs):
        """Freeze the identity on the way in, once.

        Only when it is not already set: re-saving a corrected session years
        later must not restamp it with today's roster, which would quietly
        rewrite history every time somebody edited a note.
        """
        if self.staff_id and not self.staff_name_snapshot:
            self.staff_name_snapshot = self.staff.name
            self.staff_role_snapshot = self.staff.role or ''
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {
                    'staff_name_snapshot', 'staff_role_snapshot'}
        super().save(*args, **kwargs)

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


class StaffPerformanceReview(models.Model):
    """One periodic assessment of one staff member, and the numbers behind it.

    WHY A REVIEW IS NOT A REPORT
    ============================
    The dashboard's figures are live -- ask it today and it answers about today.
    A review is the opposite: it is what somebody assessed, for a stated period,
    on a stated date, and it must still say that in a year. So finalising one
    FREEZES the metrics into `kpi_snapshot`, and nothing recomputes them
    afterwards. Change a rate, correct attendance, reassign a stage, promote the
    person, delete them from the roster -- a finalised January review still
    reads as it did in January.

    That is also why `role_snapshot` exists. A Tailor promoted to Master must
    not have last quarter's review silently re-labelled: the review was of their
    work as a Tailor, and the role it was written against is part of the record.

    RATINGS
    =======
    Five components, each 1-5, stored separately. There is no hidden weighted
    average: `overall_rating` is the plain mean of the components that were
    actually rated, rounded to one place, and a component left unrated is left
    out of the mean rather than counted as zero. A score with invented precision
    is worse than no score.

      1  Needs significant improvement
      2  Needs improvement
      3  Meets expectations
      4  Exceeds expectations
      5  Outstanding

    LIFECYCLE
    =========
    DRAFT -> FINAL -> ACKNOWLEDGED. A draft is editable; FINAL is not, and
    acknowledgement is an explicit act by the staff member, never inferred from
    them having opened the page. A finalised review found to be wrong is
    superseded by a new review for the same period, not edited -- the mistake
    stays legible, which is the same rule the ledger follows.
    """

    class ReviewType(models.TextChoices):
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'
        QUARTERLY = 'QUARTERLY', 'Quarterly'
        CUSTOM = 'CUSTOM', 'Custom period'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        FINAL = 'FINAL', 'Finalised'
        ACKNOWLEDGED = 'ACKNOWLEDGED', 'Acknowledged by staff'

    #: 1-5, and the same scale for every component so they can be averaged.
    RATING_CHOICES = [
        (1, 'Needs significant improvement'),
        (2, 'Needs improvement'),
        (3, 'Meets expectations'),
        (4, 'Exceeds expectations'),
        (5, 'Outstanding'),
    ]
    #: The components that make up `overall_rating`. Named once so the mean and
    #: the serializer cannot disagree about what is being averaged.
    COMPONENTS = ('productivity_rating', 'quality_rating', 'timeliness_rating',
                  'attendance_rating', 'reliability_rating')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: SET_NULL with snapshots, matching PayrollRecord and StaffLedgerEntry: a
    #: person can leave the roster and their assessment history must remain
    #: readable and attributable.
    staff = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='performance_reviews')
    staff_name_snapshot = models.CharField(max_length=150)
    #: The role AS AT the review. Not a copy of today's role.
    role_snapshot = models.CharField(max_length=50, blank=True, default='')

    review_type = models.CharField(
        max_length=12, choices=ReviewType.choices,
        default=ReviewType.MONTHLY, db_index=True)
    period_start = models.DateField(db_index=True)
    period_end = models.DateField()

    productivity_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=RATING_CHOICES)
    quality_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=RATING_CHOICES)
    timeliness_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=RATING_CHOICES)
    attendance_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=RATING_CHOICES)
    reliability_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=RATING_CHOICES)
    #: Derived from the components above, never typed. One decimal place is all
    #: the precision five whole numbers can honestly carry.
    overall_rating = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True)

    strengths = models.TextField(blank=True, default='')
    improvement_areas = models.TextField(blank=True, default='')
    goals = models.TextField(blank=True, default='')
    manager_notes = models.TextField(blank=True, default='')

    #: The operational metrics as they stood when this was finalised. Empty
    #: while the review is a draft, because a draft's figures are still live.
    #: Deliberately holds NO financial value -- see performance.py.
    kpi_snapshot = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=14, choices=Status.choices, default=Status.DRAFT, db_index=True)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='performance_reviews_written')
    reviewer_name_snapshot = models.CharField(max_length=150, blank=True, default='')
    finalised_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start', 'staff_name_snapshot']
        indexes = [
            models.Index(fields=['staff', '-period_start'],
                         name='review_staff_period'),
            models.Index(fields=['status', '-period_start'],
                         name='review_status_period'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F('period_start')),
                name='review_period_ends_after_it_starts'),
            # One review per person per period per type. A second assessment of
            # the same window is a correction, and a correction supersedes by
            # replacing the draft -- not by quietly existing twice.
            models.UniqueConstraint(
                fields=['staff', 'period_start', 'period_end', 'review_type'],
                name='review_unique_per_staff_period'),
        ]

    def __str__(self):
        return (f"{self.staff_name_snapshot} · {self.get_review_type_display()} "
                f"{self.period_start} ({self.status})")

    @property
    def is_final(self):
        return self.status in (self.Status.FINAL, self.Status.ACKNOWLEDGED)

    def computed_overall(self):
        """The mean of the components that were actually rated, or None.

        Unrated components are omitted, not treated as zero: a review that
        assessed only productivity and attendance should not be dragged to 1.4
        by three blanks.
        """
        from decimal import Decimal, ROUND_HALF_UP
        given = [getattr(self, name) for name in self.COMPONENTS]
        given = [value for value in given if value is not None]
        if not given:
            return None
        return (Decimal(sum(given)) / Decimal(len(given))).quantize(
            Decimal('0.1'), rounding=ROUND_HALF_UP)
