
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin', '0003_alter_auditlog_action'),
    ]

    operations = [
        migrations.AlterField(
            model_name='auditlog',
            name='action',
            field=models.CharField(choices=[('boutique.suspend', 'Boutique suspended'), ('boutique.reactivate', 'Boutique reactivated'), ('boutique.modules', 'Boutique modules changed'), ('user.deactivate', 'User deactivated'), ('user.activate', 'User activated'), ('user.revoke_token', 'User sessions revoked'), ('user.password_reset', 'Password reset triggered'), ('user.access_link', 'Sign-in link issued'), ('lead.update', 'Lead updated'), ('flag.change', 'Feature flag changed'), ('setting.change', 'Platform setting changed'), ('error.acknowledge', 'Error acknowledged'), ('error.resolve', 'Error resolved'), ('data.view', 'Boutique data viewed'), ('console.login', 'Console sign-in'), ('console.logout', 'Console sign-out'), ('console.login_failed', 'Console sign-in failed')], db_index=True, max_length=40),
        ),
    ]
