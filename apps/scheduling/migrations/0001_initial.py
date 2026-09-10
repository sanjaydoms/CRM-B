
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('crm_api', '0016_alter_customer_created_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Appointment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('appointment_type', models.CharField(choices=[('CONSULTATION', 'Design Consultation'), ('MEASUREMENT', 'Measurement Fitting'), ('TRIAL', 'Garment Trial'), ('DELIVERY', 'Final Delivery')], db_index=True, default='TRIAL', max_length=50)),
                ('status', models.CharField(choices=[('SCHEDULED', 'Scheduled'), ('CONFIRMED', 'Confirmed'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled'), ('RESCHEDULED', 'Rescheduled')], db_index=True, default='SCHEDULED', max_length=50)),
                ('scheduled_time', models.DateTimeField(db_index=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('reminder_sent', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_staff', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='scheduled_appointments', to='crm_api.tailor')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='appointments', to='crm_api.customer')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='appointments', to='crm_api.order')),
            ],
            options={
                'ordering': ['scheduled_time'],
            },
        ),
    ]
