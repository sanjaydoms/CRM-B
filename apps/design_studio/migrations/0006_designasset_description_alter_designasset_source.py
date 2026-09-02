
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('design_studio', '0005_backfill_template_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='designasset',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='designasset',
            name='source',
            field=models.CharField(choices=[('upload', 'Team Upload'), ('favourite', 'Saved Favourite'), ('pinterest', 'Pinterest'), ('google', 'Google Images'), ('catalogue', 'Boutique Catalogue'), ('suggestion', 'Suggestion Template')], db_index=True, default='upload', max_length=32),
        ),
    ]
