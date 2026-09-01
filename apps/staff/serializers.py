from rest_framework import serializers

from core.roles import OWNER, resolve_user_role

from .models import StaffProfile

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
