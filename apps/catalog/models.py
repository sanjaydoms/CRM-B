
import uuid

from django.db import models

from crm_api.models import Order
from apps.inventory.models import Category as InventoryCategory


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


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    sequence = models.IntegerField(default=0)

    tenant = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence', 'name']
        unique_together = [('key', 'tenant')]

    def __str__(self):
        return f"{self.name} v{self.version}"

    @classmethod
    def resolve(cls, key, tenant=None):

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

    visible_when = models.JSONField(blank=True, null=True)

    validation = models.JSONField(default=dict, blank=True)

    inventory_category = models.CharField(
        max_length=30, choices=InventoryCategory.choices, blank=True, null=True
    )

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.section.template.key}.{self.key}"


class TemplateFieldOption(models.Model):

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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='garment_jobs')
    template = models.ForeignKey(
        GarmentTemplate, on_delete=models.PROTECT, related_name='jobs'
    )
    template_version = models.IntegerField()

    spec = models.JSONField(default=dict, blank=True)

    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fabric_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    embroidery_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    customization_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tailoring_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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
