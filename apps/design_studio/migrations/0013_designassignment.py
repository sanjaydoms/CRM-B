
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_add_gown_suit_sherwani'),
        ('design_studio', '0012_designer_email_alter_designer_user'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DesignAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('ASSIGNED', 'Assigned'), ('SUBMITTED', 'Submitted for review'), ('APPROVED', 'Approved'), ('CHANGES_REQUESTED', 'Changes requested')], db_index=True, default='ASSIGNED', max_length=20)),
                ('brief', models.TextField(blank=True, default='', help_text='What the owner is asking for, beyond what the spec already says.')),
                ('due_date', models.DateField(blank=True, null=True)),
                ('submission_note', models.TextField(blank=True, default='')),
                ('review_note', models.TextField(blank=True, default='')),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='design_assignments_made', to=settings.AUTH_USER_MODEL)),
                ('design', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='assignments', to='design_studio.designasset')),
                ('designer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assignments', to='design_studio.designer')),
                ('garment_job', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='design_assignment', to='catalog.garmentjob')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='design_assignments_reviewed', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-assigned_at'],
                'indexes': [models.Index(fields=['designer', 'status'], name='design_assignment_queue')],
            },
        ),
    ]
