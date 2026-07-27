import uuid
from django.db import models
from django.contrib.auth.models import User
from crm_api.models import Order, Tailor

class ProductionTask(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('BLOCKED', 'Blocked'),
        ('SKIPPED', 'Skipped'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='production_tasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    stage_key = models.CharField(max_length=100, db_index=True)
    assigned_to = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    priority = models.CharField(max_length=50, choices=PRIORITY_CHOICES, default='MEDIUM', db_index=True)
    sequence = models.IntegerField(default=0)
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, default=24.00)
    actual_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    due_date = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    proof_images = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence', 'created_at']

    def __str__(self):
        return f"{self.order.order_id} - {self.title} ({self.status})"

class QCRecord(models.Model):
    STATUS_CHOICES = [
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
        ('REWORK_REQUIRED', 'Rework Required'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='qc_records')
    task = models.ForeignKey(ProductionTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='qc_records')
    inspector = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='conducted_qcs')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PASSED')
    checklist_results = models.JSONField(default=dict, blank=True) # e.g. {"measurements_match": true, "stitching_clean": true}
    comments = models.TextField(blank=True, null=True)
    proof_images = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"QC for Order {self.order.order_id} - {self.status}"
