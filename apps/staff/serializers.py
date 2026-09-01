from rest_framework import serializers

from .models import StaffProfile


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
