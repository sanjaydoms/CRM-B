from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class BoutiqueTenant(TenantMixin):
    owner_email = models.EmailField(unique=True)
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)
    
    # default true means schema is automatically created on save
    auto_create_schema = True

    def __str__(self):
        return f"{self.name} ({self.owner_email})"

class Domain(DomainMixin):
    pass


class DemoRequest(models.Model):
    """A demo request from the public marketing site.

    Lives in the `tenants` app because a demo request is a prospective tenant,
    and because `tenants` is in SHARED_APPS only -- so this table exists in the
    public schema and nowhere else. That is what lets the intake view write it
    without caring which tenant the middleware happened to resolve.

    Every field is length-bounded. The ModelForm in views.py derives its
    validation from these, and DATA_UPLOAD_MAX_MEMORY_SIZE is unset, so an
    unbounded TextField here would accept 2.5MB per submission from a stranger.
    """

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

    # The same four questions the mailto: fallback asks, so a lead that arrives
    # by email and a lead that arrives by form carry the same information.
    makes = models.CharField(max_length=200, blank=True)
    orders_per_month = models.CharField(max_length=40, blank=True)
    people = models.CharField(max_length=40, blank=True)
    problem = models.CharField(max_length=2000, blank=True)

    # Worked by hand in the admin until the superadmin portal exists; both read
    # the same rows, so that portal needs no migration on its first day.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW', db_index=True)
    notes = models.TextField(blank=True)

    # Only used to rate-limit intake. Indexed because that check is a query.
    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.boutique} ({self.created_at:%Y-%m-%d})"
