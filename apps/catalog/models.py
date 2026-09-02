"""Garment product templates.

A template describes one garment as data -- sections, fields, options and the
rules that decide which fields apply -- so the order form is rendered from the
database rather than written twice, once in JSX and once in a serializer.

Adding a garment, a regional variation or a boutique's own option list is a row,
not a deploy. See docs/garment-product-templates.md for the full specification.
"""

import uuid

from django.db import models

from crm_api.models import Order
from apps.inventory.models import Category as InventoryCategory


# The five sections every garment renders, in this order. A garment with nothing
# to put in a section simply has no fields there -- the section itself never
# disappears, so the counter staff see the same shape for a saree and a churidar.
class SectionKey(models.TextChoices):
    BASIC = 'basic', 'Basic Information'
    MEASUREMENTS = 'measurements', 'Measurements'
    STYLE = 'style', 'Style & Design Options'
    MATERIALS = 'materials', 'Materials & Accessories'
    PRODUCTION = 'production', 'Production Notes'


class FieldType(models.TextChoices):
    TEXT = 'text', 'Text'
    TEXTAREA = 'textarea', 'Long text'
    NUMBER = 'number', 'Number'
    SELECT = 'select', 'Single choice'
    MULTISELECT = 'multiselect', 'Multiple choice'
    BOOLEAN = 'boolean', 'Yes / No'
    DATE = 'date', 'Date'
    FILE = 'file', 'File'
    INVENTORY_REF = 'inventory_ref', 'Inventory item'


class GarmentTemplate(models.Model):
    """One garment type. `key` is permanent; everything else may be edited."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    # Bumped whenever a field or option changes in a way that would alter how an
    # existing spec validates. Jobs freeze the version they were created under,
    # so a template edited in April cannot retroactively invalidate March's work.
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    sequence = models.IntegerField(default=0)

    # Null = the global default shipped with the product. A boutique that
    # customises a garment gets its own row, and resolution is "tenant if
    # present, else global" -- so boutiques inherit improvements to the defaults
    # right up until the moment they override one.
    tenant = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # The parts of this garment a design photograph can be *of* -- a saree has a
    # pallu, a border, a body; a blouse has a neck, a sleeve, a back. Stored as
    # [{"key": "pallu", "label": "Pallu Design"}, ...] and read by the design
    # library so an upload is filed under the right part of the garment.
    #
    # A column here rather than a table of its own, and not a TemplateField
    # either: this is not something the counter staff answer on an order, it is
    # the vocabulary the design library files photographs under. Living on the
    # template means it inherits resolve()'s tenant override for free, so a
    # boutique can name its own parts without a deploy.
    design_parts = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence', 'name']
        unique_together = [('key', 'tenant')]

    def __str__(self):
        return f"{self.name} v{self.version}"

    @classmethod
    def resolve(cls, key, tenant=None):
        """The template a given boutique should see for `key`."""
        if tenant:
            override = cls.objects.filter(key=key, tenant=tenant, is_active=True).first()
            if override:
                return override
        return cls.objects.filter(key=key, tenant__isnull=True, is_active=True).first()


class TemplateSection(models.Model):
    template = models.ForeignKey(
        GarmentTemplate, on_delete=models.CASCADE, related_name='sections'
    )
    key = models.CharField(max_length=30, choices=SectionKey.choices)
    title = models.CharField(max_length=100)
    sequence = models.IntegerField(default=0)

    class Meta:
        ordering = ['sequence']
        unique_together = [('template', 'key')]

    def __str__(self):
        return f"{self.template.key} · {self.title}"


class TemplateField(models.Model):
    section = models.ForeignKey(
        TemplateSection, on_delete=models.CASCADE, related_name='fields'
    )
    key = models.CharField(max_length=60, db_index=True)
    label = models.CharField(max_length=150)
    field_type = models.CharField(max_length=20, choices=FieldType.choices)
    unit = models.CharField(max_length=10, blank=True, null=True)  # 'in', 'm'
    is_required = models.BooleanField(default=False)
    is_repeatable = models.BooleanField(default=False)
    default = models.JSONField(blank=True, null=True)
    help_text = models.CharField(max_length=300, blank=True, null=True)
    sequence = models.IntegerField(default=0)

    # {"field": "petticoat_required", "op": "eq", "value": true}, nested under
    # "all"/"any". Evaluated by core.templates.is_visible and its JS twin.
    visible_when = models.JSONField(blank=True, null=True)

    # {"min": 0, "max": 120, "step": 0.25, "max_length": 500}
    validation = models.JSONField(default=dict, blank=True)

    # inventory_ref only: restricts the picker, and is enforced on write.
    inventory_category = models.CharField(
        max_length=30, choices=InventoryCategory.choices, blank=True, null=True
    )

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.section.template.key}.{self.key}"


class TemplateFieldOption(models.Model):
    """A dropdown value.

    A table rather than a Python enum so the owner can add "Paithani" to saree
    types from the admin without waiting for a release.
    """

    field = models.ForeignKey(
        TemplateField, on_delete=models.CASCADE, related_name='options'
    )
    value = models.CharField(max_length=60)
    label = models.CharField(max_length=150)
    sequence = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sequence']
        unique_together = [('field', 'value')]

    def __str__(self):
        return f"{self.field.key}={self.value}"


class GarmentJob(models.Model):
    """One dress on an order.

    An order is a commercial envelope and may hold several of these -- a lehenga,
    its blouse and a dupatta are three jobs, each with its own template, spec and
    measurement snapshot.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='garment_jobs')
    template = models.ForeignKey(
        GarmentTemplate, on_delete=models.PROTECT, related_name='jobs'
    )
    # Frozen at creation: this job renders and validates against the template as
    # it was the day it was taken, not as it is today.
    template_version = models.IntegerField()

    # Categorical answers keyed by TemplateField.key.
    spec = models.JSONField(default=dict, blank=True)

    # What THIS dress costs, component by component. Money used to live only on
    # the Order as one flat set, so a Blouse + Lehenga order was priced as
    # whichever garment the customer's profile named. The order's columns still
    # exist -- as the SUM of these, written by domains.orders.pricing, which is
    # the only arithmetic path. Names deliberately mirror Order's columns so
    # the rollup is a loop, not a mapping. All-zero components on an old job
    # mean "priced before this existed"; such orders keep their entered totals
    # and are never recomputed. Packaging is not here: one parcel per order.
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fabric_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    embroidery_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    customization_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tailoring_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Numeric dimensions, kept apart from `spec` because they are versioned,
    # printed on the cutting sheet and compared across a customer's orders.
    measurements = models.JSONField(default=dict, blank=True)

    sequence = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence', 'created_at']

    def save(self, *args, **kwargs):
        if not self.template_version:
            self.template_version = self.template.version
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_id} · {self.template.name}"


class JobMaterial(models.Model):
    """A material line resolving one inventory_ref field on a job.

    Store material points at an InventoryItem so issuing it can write a
    StockMovement; customer-supplied material is recorded as free text and never
    touches stock.
    """

    class Source(models.TextChoices):
        STORE = 'STORE', 'Store inventory'
        CUSTOMER = 'CUSTOMER', 'Customer provided'

    job = models.ForeignKey(GarmentJob, on_delete=models.CASCADE, related_name='materials')
    field_key = models.CharField(max_length=60)
    inventory_item = models.ForeignKey(
        'inventory.InventoryItem', on_delete=models.PROTECT,
        null=True, blank=True, related_name='job_materials',
    )
    free_text = models.CharField(max_length=200, blank=True, null=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unit = models.CharField(max_length=20, blank=True, null=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.STORE)
    notes = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        ordering = ['field_key']

    def __str__(self):
        name = self.inventory_item.name if self.inventory_item else (self.free_text or '—')
        return f"{self.field_key}: {name}"
