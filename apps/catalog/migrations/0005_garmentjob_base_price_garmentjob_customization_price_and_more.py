
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_add_gown_suit_sherwani'),
    ]

    operations = [
        migrations.AddField(
            model_name='garmentjob',
            name='base_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='garmentjob',
            name='customization_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='garmentjob',
            name='embroidery_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='garmentjob',
            name='fabric_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='garmentjob',
            name='tailoring_charges',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
