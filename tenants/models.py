from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class BoutiqueTenant(TenantMixin):
    owner_email = models.EmailField(unique=True)
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    # What "3 PM" means to this boutique and its customers.
    #
    # Datetimes are stored in UTC and stay that way -- this is a PRESENTATION
    # setting, read when output is rendered and never written into the data.
    # The alternative, moving settings.TIME_ZONE off UTC, would have been one
    # line and correct only until a boutique outside India opened: every tenant
    # would then share one clock and one of them would be wrong, with no way to
    # tell which timestamps had been rendered under which assumption.
    #
    # A plain CharField rather than a choices list: the zoneinfo database is
    # the authority on what a timezone is, it changes without Django, and
    # pinning a copy of it here would go stale. Validated on save instead.
    timezone = models.CharField(
        max_length=64, default='Asia/Kolkata',
        help_text="IANA name, e.g. Asia/Kolkata. Used to show this boutique "
                  "and its customers their own local time. Storage stays UTC.",
    )

    # The platform administrator's off switch: a boutique that has stopped
    # paying, or is being abused, is turned off here rather than deleted. The
    # schema and every row in it survive, so switching it back on restores the
    # boutique exactly as it was. Enforced at the two places a tenant is bound
    # to the connection -- TenantHeaderMiddleware and LoginView -- because those
    # are the only two ways in.
    is_active = models.BooleanField(
        default=True,
        help_text="Unticked, this boutique cannot sign in or use the API. Its data is kept.",
    )

    # Per-boutique feature switches: {module_key: bool}, keys from core.modules.
    # Enforced in TenantHeaderMiddleware, which is the only chokepoint every
    # request passes through.
    #
    # An ABSENT key means ENABLED (core.modules.is_enabled), and the default is
    # {} rather than default_enabled() on purpose. A tenant row written before a
    # module existed has no opinion about that module, and "no opinion" must not
    # read as "off" -- otherwise adding an entry to core/modules.py would switch
    # the new feature off for every existing boutique the moment it deployed,
    # and the only fix would be a data migration per module forever. Storing
    # only the explicit decisions also means this column records what an
    # administrator actually chose, not a snapshot of the module list on the day
    # the row was created.
    enabled_modules = models.JSONField(
        default=dict, blank=True,
        help_text="Module switches this boutique has had changed, as "
                  "{module_key: true/false}. A module that is not listed is on.",
    )

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
