import uuid
from django.db import models
from django.contrib.auth.models import User

class UniversalActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activities')
    user_name_snapshot = models.CharField(max_length=150, blank=True, null=True)
    module = models.CharField(max_length=50, db_index=True) # e.g. orders, production, customers, finance
    entity_type = models.CharField(max_length=50, db_index=True) # e.g. Order, ProductionTask, Customer
    entity_id = models.CharField(max_length=100, db_index=True)
    action = models.CharField(max_length=50, db_index=True) # e.g. CREATED, UPDATED, TASK_COMPLETED
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    old_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Universal Activities'

    def __str__(self):
        return f"[{self.module.upper()}] {self.title} by {self.user_name_snapshot or 'System'} at {self.timestamp}"
