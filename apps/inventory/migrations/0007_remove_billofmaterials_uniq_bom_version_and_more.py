
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_add_gown_suit_sherwani'),
        ('design_studio', '0012_designer_email_alter_designer_user'),
        ('inventory', '0006_billofmaterials_bomline_unitconversion_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='billofmaterials',
            name='uniq_bom_version',
        ),
        migrations.AddConstraint(
            model_name='billofmaterials',
            constraint=models.UniqueConstraint(condition=models.Q(('design__isnull', False), ('template__isnull', False)), fields=('template', 'design', 'version'), name='uniq_bom_version_template_design'),
        ),
        migrations.AddConstraint(
            model_name='billofmaterials',
            constraint=models.UniqueConstraint(condition=models.Q(('design__isnull', True), ('template__isnull', False)), fields=('template', 'version'), name='uniq_bom_version_template'),
        ),
        migrations.AddConstraint(
            model_name='billofmaterials',
            constraint=models.UniqueConstraint(condition=models.Q(('design__isnull', False), ('template__isnull', True)), fields=('design', 'version'), name='uniq_bom_version_design'),
        ),
        migrations.AddConstraint(
            model_name='billofmaterials',
            constraint=models.UniqueConstraint(condition=models.Q(('design__isnull', True), ('template__isnull', True)), fields=('name', 'version'), name='uniq_bom_version_standalone'),
        ),
    ]
