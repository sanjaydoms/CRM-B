from rest_framework import serializers

from crm_api.models import Tailor

from core.roles import OWNER, resolve_user_role

from .models import AttendanceSession, StaffPerformanceReview, StaffProfile

#: What only the owner may read on somebody ELSE's row.
#:
#: Everyone keeps these on their own record -- a tailor is entitled to know
#: their own rate and what is coming off it. The list is what a colleague must
#: never learn by asking, and it is `employment_type` as well as the money:
#: knowing a person is on a CONTRACT rather than FULL_TIME is a fact about
#: their terms, and terms are the thing being protected here.
#:
#: Deliberately NOT `phone`, `address` or `emergency_contact`. A Master
#: supervising the floor needs to be able to reach their team, and an emergency
#: contact that only the owner can see is an emergency contact nobody can use
#: at seven in the evening.
CONFIDENTIAL_FIELDS = (
    'hourly_rate', 'weekly_hours', 'deposit_total', 'deposit_weekly',
    'employment_type',
)


class StaffProfileSerializer(serializers.ModelSerializer):
    """Employment terms, with the roster fields needed to render a row.

    The field list is written out rather than `fields = '__all__'`, and that is
    deliberate on this model above all others. `__all__` is what made
    TailorSerializer leak the roster's email addresses, and every column here is
    more sensitive than an email address. A field added to the model in a later
    phase -- a bank account, a tax id -- must be published by someone choosing
    to publish it, not by having been added.
    """

    #: Read-only passengers from the roster, so a staff row renders without a
    #: second request. They are the Tailor's own public fields; nothing
    #: confidential travels this way.
    staff_name = serializers.CharField(source='staff.name', read_only=True)
    staff_role = serializers.CharField(source='staff.role', read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            'id', 'staff', 'staff_name', 'staff_role',
            'employment_type', 'joined_at', 'exit_date',
            'hourly_rate', 'weekly_hours',
            'deposit_total', 'deposit_weekly',
            'phone', 'emergency_contact', 'address', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """Strip another person's terms before they leave the building.

        The queryset already stops a tailor from reaching a colleague's row at
        all, so for them this is a second lock on a door that is already shut.
        It is the ONLY lock for a Master, who can legitimately list the team:
        supervising the floor is not the same as being told what the floor is
        paid, and the difference cannot be expressed by scoping rows.

        Owner-writes-only lives in StaffSelfOrOwner, so nothing here has to
        think about PATCH: a caller who could reach this with a write is the
        owner, and the owner sees everything anyway.

        No request in context -- a shell, a management command, a serializer
        used server-side -- returns the full record. Those callers are already
        inside the application and have the ORM; withholding here would break
        them without protecting anything.
        """
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request is None:
            return data
        if resolve_user_role(request.user) == OWNER:
            return data

        viewer = getattr(request.user, 'tailor_profile', None)
        if viewer is not None and instance.staff_id == viewer.id:
            return data

        for field in CONFIDENTIAL_FIELDS:
            data.pop(field, None)
        return data

    def validate(self, attrs):
        """Dates that describe an employment that could not have happened.

        Checked against the instance as well as the payload, so a PATCH that
        sends only `exit_date` is still compared with the joining date already
        stored -- validating the payload alone would let the two fields be made
        inconsistent one request at a time.
        """
        joined = attrs.get('joined_at', getattr(self.instance, 'joined_at', None))
        exited = attrs.get('exit_date', getattr(self.instance, 'exit_date', None))
        if joined and exited and exited < joined:
            raise serializers.ValidationError(
                {'exit_date': 'The leaving date cannot be before the joining date.'})
        return attrs

    def update(self, instance, validated_data):
        """Employment terms stay with the person they were agreed with.

        Moving a profile to another roster member would hand them somebody
        else's rate, deposit and -- once the ledger exists -- their payroll
        history, while silently leaving the original person with none. There is
        no reason to do it, so the field is simply not honoured on update.
        """
        validated_data.pop('staff', None)
        return super().update(instance, validated_data)


class AttendanceSessionSerializer(serializers.ModelSerializer):
    """One shift, as the interface needs to draw it.

    Every timestamp field is read-only. Attendance is stamped by the server on
    check-in and check-out, and the two paths where a human supplies a time --
    the owner entering a missed day, the owner correcting one -- go through
    their own actions with their own validation and their own audit trail. A
    writable `check_in` here would be a way round both.
    """

    # Read through the model rather than by traversing `staff.name`: the FK is
    # nullable from Phase 9 (a session outlives the roster row it belonged to),
    # and a source that walks into None is an AttributeError on a historical
    # row. `staff_label` gives the live name while there is one and the frozen
    # snapshot afterwards.
    staff_name = serializers.CharField(source='staff_label', read_only=True)
    staff_role = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(read_only=True)
    was_corrected = serializers.SerializerMethodField()

    def get_staff_role(self, session):
        """The role now if they are still on the roster, else the frozen one."""
        if session.staff is not None:
            return session.staff.role
        return session.staff_role_snapshot or ''

    class Meta:
        model = AttendanceSession
        fields = [
            'id', 'staff', 'staff_name', 'staff_role',
            'staff_name_snapshot', 'staff_role_snapshot', 'date',
            'check_in', 'check_out', 'minutes', 'source', 'note',
            'is_open', 'was_corrected',
            'original_check_in', 'original_check_out',
            'corrected_at', 'correction_reason',
            'created_at', 'updated_at',
        ]
        # The whole record. Writes happen through the named actions, never by
        # PUT/PATCHing a session directly.
        read_only_fields = fields

    def get_was_corrected(self, instance):
        """Shown in the timesheet so an edited row is never mistaken for a stamped one."""
        return instance.corrected_at is not None


class StaffPerformanceReviewSerializer(serializers.ModelSerializer):
    """A review, with an explicit field list and no financial field anywhere.

    Written out rather than `__all__` for the same reason StaffProfileSerializer
    is: a field added to the model later must be published by somebody choosing
    to publish it. This model holds no money today and the audit that keeps it
    that way is the list below.

    Nearly everything is read-only. A review's staff, period and type are set
    once at creation; its ratings and notes are editable only while it is a
    draft; its snapshot, status and timestamps are written by the service.
    """

    # Required despite the model's null=True. The FK is nullable so a review
    # SURVIVES the roster row being deleted (the snapshot fields carry the name
    # and role), not so one can be written about nobody -- and because `staff`
    # sits in a UniqueConstraint, DRF inferred default=None and happily created
    # a staff-less review that finalise then froze with an empty snapshot.
    staff = serializers.PrimaryKeyRelatedField(
        queryset=Tailor.objects.all(), required=True, allow_null=False)
    staff_role = serializers.CharField(source='staff.role', read_only=True)
    is_final = serializers.BooleanField(read_only=True)
    overall_rating = serializers.DecimalField(
        max_digits=3, decimal_places=1, read_only=True)

    class Meta:
        model = StaffPerformanceReview
        fields = [
            'id', 'staff', 'staff_name_snapshot', 'staff_role', 'role_snapshot',
            'review_type', 'period_start', 'period_end',
            'productivity_rating', 'quality_rating', 'timeliness_rating',
            'attendance_rating', 'reliability_rating', 'overall_rating',
            'strengths', 'improvement_areas', 'goals', 'manager_notes',
            'kpi_snapshot', 'status', 'is_final',
            'reviewer_name_snapshot', 'finalised_at', 'acknowledged_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'staff_name_snapshot', 'staff_role', 'role_snapshot',
            'overall_rating', 'kpi_snapshot', 'status', 'is_final',
            'reviewer_name_snapshot', 'finalised_at', 'acknowledged_at',
            'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        """Periods that could not have happened, and edits to frozen history."""
        instance = self.instance
        start = attrs.get('period_start',
                          getattr(instance, 'period_start', None))
        end = attrs.get('period_end', getattr(instance, 'period_end', None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {'period_end': 'The period cannot end before it starts.'})

        # Belt to the viewset's braces. A finalised review is history; the only
        # supported correction is a new review for the same period.
        if instance is not None and instance.is_final:
            raise serializers.ValidationError(
                'This review has been finalised and cannot be edited. Write a '
                'new review for the period instead.')
        return attrs

    def create(self, validated_data):
        staff = validated_data.get('staff')
        validated_data['staff_name_snapshot'] = staff.name if staff else ''
        # The role AS AT creation, so a later promotion cannot re-label it.
        validated_data['role_snapshot'] = (staff.role or '') if staff else ''
        review = super().create(validated_data)
        review.overall_rating = review.computed_overall()
        review.save(update_fields=['overall_rating'])
        return review

    def update(self, instance, validated_data):
        # `staff` and the period identify the review; changing them would make
        # it an assessment of a different thing under the same id.
        for pinned in ('staff', 'period_start', 'period_end', 'review_type'):
            validated_data.pop(pinned, None)
        review = super().update(instance, validated_data)
        review.overall_rating = review.computed_overall()
        review.save(update_fields=['overall_rating'])
        return review
