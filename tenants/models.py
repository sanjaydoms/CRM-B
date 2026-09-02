from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class BoutiqueTenant(TenantMixin):
    owner_email = models.EmailField(unique=True)
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    timezone = models.CharField(
        max_length=64, default='Asia/Kolkata',
        help_text="IANA name, e.g. Asia/Kolkata. Used to show this boutique "
                  "and its customers their own local time. Storage stays UTC.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Unticked, this boutique cannot sign in or use the API. Its data is kept.",
    )

    enabled_modules = models.JSONField(
        default=dict, blank=True,
        help_text="Module switches this boutique has had changed, as "
                  "{module_key: true/false}. A module that is not listed is on.",
    )

    auto_create_schema = True

    def __str__(self):
        return f"{self.name} ({self.owner_email})"

class Domain(DomainMixin):
    pass


class DemoRequest(models.Model):

    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('CONTACTED', 'Contacted'),
        ('QUALIFIED', 'Qualified'),
        ('CONVERTED', 'Converted'),
        ('DECLINED', 'Declined'),
    ]

    name = models.CharField(max_length=100)
    boutique = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=40)

    makes = models.CharField(max_length=200, blank=True)
    orders_per_month = models.CharField(max_length=40, blank=True)
    people = models.CharField(max_length=40, blank=True)
    problem = models.CharField(max_length=2000, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW', db_index=True)
    notes = models.TextField(blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.boutique} ({self.created_at:%Y-%m-%d})"
