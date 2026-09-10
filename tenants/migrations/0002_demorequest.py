
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DemoRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('boutique', models.CharField(max_length=100)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(max_length=40)),
                ('makes', models.CharField(blank=True, max_length=200)),
                ('orders_per_month', models.CharField(blank=True, max_length=40)),
                ('people', models.CharField(blank=True, max_length=40)),
                ('problem', models.CharField(blank=True, max_length=2000)),
                ('status', models.CharField(choices=[('NEW', 'New'), ('CONTACTED', 'Contacted'), ('QUALIFIED', 'Qualified'), ('CONVERTED', 'Converted'), ('DECLINED', 'Declined')], db_index=True, default='NEW', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('ip', models.GenericIPAddressField(blank=True, db_index=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
