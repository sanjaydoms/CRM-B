from django.db import models
import uuid
from django.contrib.auth.models import User

class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    mobile_number = models.CharField(max_length=20, unique=True, db_index=True)
    email_address = models.EmailField(max_length=254, blank=True, null=True, db_index=True)
    address = models.TextField(blank=True, null=True)
    city_region = models.CharField(max_length=100, blank=True, null=True)
    source = models.CharField(max_length=50, default="Walk In") # Walk In, Instagram, Referral, etc.
    customer_type = models.CharField(max_length=50, default="Women", db_index=True) # Women, Men, Kids
    garment_type = models.CharField(max_length=100, default="Lehenga")
    neckline_style = models.CharField(max_length=100, blank=True, null=True)
    sleeve_style = models.CharField(max_length=100, blank=True, null=True)
    back_style = models.CharField(max_length=100, blank=True, null=True)
    length_preference = models.CharField(max_length=100, blank=True, null=True)
    silhouette = models.CharField(max_length=100, blank=True, null=True)
    embellishments = models.CharField(max_length=100, blank=True, null=True)
    pattern_style = models.CharField(max_length=100, blank=True, null=True)
    occasion = models.CharField(max_length=100, blank=True, null=True)
    custom_requirements = models.TextField(blank=True, null=True)
    
    # Additional Info
    date_of_birth = models.DateField(blank=True, null=True)
    occupation = models.CharField(max_length=100, blank=True, null=True)
    preferred_communication = models.CharField(max_length=50, default="WhatsApp") # WhatsApp, Call, Email
    notes = models.TextField(blank=True, null=True)
    
    # Files
    profile_photo = models.ImageField(upload_to='customer_profiles/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.mobile_number})"

class Measurement(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='measurements')
    bust = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    waist = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    hips = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    shoulder = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    arm_length = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    neck = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    length = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    additional_measurements = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Measurements for {self.customer.first_name} {self.customer.last_name}"

    def save(self, *args, **kwargs):
        # Determine if values changed relative to the latest history entry
        last_history = MeasurementHistory.objects.filter(customer=self.customer).order_by('-changed_at').first()
        changed = False
        if not last_history:
            changed = True
        else:
            if (last_history.bust != self.bust or
                last_history.waist != self.waist or
                last_history.hips != self.hips or
                last_history.shoulder != self.shoulder or
                last_history.arm_length != self.arm_length or
                last_history.neck != self.neck or
                last_history.length != self.length or
                last_history.additional_measurements != self.additional_measurements):
                changed = True
        
        super().save(*args, **kwargs)
        if changed:
            MeasurementHistory.objects.create(
                customer=self.customer,
                bust=self.bust,
                waist=self.waist,
                hips=self.hips,
                shoulder=self.shoulder,
                arm_length=self.arm_length,
                neck=self.neck,
                length=self.length,
                additional_measurements=self.additional_measurements
            )

class MeasurementHistory(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='measurement_history')
    bust = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    waist = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    hips = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    shoulder = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    arm_length = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    neck = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    length = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    additional_measurements = models.JSONField(default=dict, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Measurement history for {self.customer.first_name} {self.customer.last_name} at {self.changed_at}"

class DesignPreference(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='design_preferences')
    notes = models.TextField(blank=True, null=True)
    # JSON list of image paths/URLs
    reference_images = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Design Prefs for {self.customer.first_name}"

class FabricSelection(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='fabric_selections')
    is_boutique_fabric = models.BooleanField(default=True)
    fabric_name = models.CharField(max_length=150)
    fabric_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # JSON list of image paths/URLs
    uploaded_fabric_images = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Fabric ({self.fabric_name}) for {self.customer.first_name}"

class BoutiqueFabric(models.Model):
    name = models.CharField(max_length=100)
    material = models.CharField(max_length=100)
    color = models.CharField(max_length=50)
    price_per_meter = models.DecimalField(max_digits=10, decimal_places=2)
    image_url = models.CharField(max_length=255, blank=True, null=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.material}) - ₹{self.price_per_meter}/mtr"

class BoutiqueDesign(models.Model):
    name = models.CharField(max_length=150)
    garment_type = models.CharField(max_length=100) # e.g. Lehenga, Gown, Saree, Kurti, Sherwani
    neckline_style = models.CharField(max_length=100, blank=True, null=True) # V-Neck, Sweetheart, etc.
    sleeve_style = models.CharField(max_length=100, blank=True, null=True) # Sleeveless, Full Sleeve, etc.
    image_url = models.CharField(max_length=255)
    is_boutique = models.BooleanField(default=True) # True = Boutique Catalog, False = AI Suggestion Template
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.name} ({self.garment_type}) - {'Boutique' if self.is_boutique else 'AI suggestion'}"

class Tailor(models.Model):
    name = models.CharField(max_length=100)
    specialty = models.CharField(max_length=100)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    status = models.CharField(max_length=50, default="Available") # Available, Busy
    role = models.CharField(max_length=50, default="Tailor") # Master, Tailor
    email = models.EmailField(blank=True, null=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tailor_profile')

    def __str__(self):
        return f"{self.name} - {self.role} ({self.status})"

class Order(models.Model):
    order_id = models.CharField(max_length=50, unique=True, db_index=True) # e.g. T2B-240529-7856
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    tailor = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    master = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_orders')
    payment_status = models.CharField(max_length=50, default="Pending", db_index=True) # Pending, Paid
    order_status = models.CharField(max_length=50, default="Received", db_index=True) # Received, Confirmed, Stylist Review, Design & Creation, Quality Check, Ready for Dispatch, Shipped, Delivered
    delivery_method = models.CharField(max_length=50, default="Direct Pickup") # Direct Pickup, Courier
    courier_service = models.CharField(max_length=100, blank=True, null=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    delivery_address = models.TextField(blank=True, null=True)
    
    # Financial breakdown
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fabric_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    embroidery_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    customization_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tailoring_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    packaging_handling = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    taxes = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    advance_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    order_date = models.DateTimeField(auto_now_add=True, db_index=True)
    estimated_delivery = models.DateField(blank=True, null=True)
    tailor_comments = models.TextField(blank=True, null=True)
    completed_garment_image = models.ImageField(upload_to='completed_garments/', blank=True, null=True)
    master_verification = models.JSONField(default=dict, blank=True)
    
    # Workflow integration
    current_stage_key = models.CharField(max_length=100, default="created", db_index=True)
    production_status = models.CharField(max_length=50, default="NOT_STARTED", db_index=True) # NOT_STARTED, IN_PROGRESS, COMPLETED, PAUSED, SKIPPED

    def __str__(self):
        return f"Order {self.order_id} - {self.customer.first_name} {self.customer.last_name}"

class OrderStage(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='stages')
    stage_key = models.CharField(max_length=100)
    stage_name = models.CharField(max_length=100)
    status = models.CharField(max_length=50, default="NOT_STARTED") # NOT_STARTED, IN_PROGRESS, COMPLETED, SKIPPED
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(default=0) # Total tracking duration in seconds
    performed_by = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True)
    comments = models.TextField(blank=True, null=True)
    attachments = models.JSONField(default=list, blank=True) # list of image URLs
    sequence = models.IntegerField(default=0)
    sla_hours = models.IntegerField(default=24)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.order.order_id} - {self.stage_name} ({self.status})"

class OrderActivity(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='activities')
    event_type = models.CharField(max_length=100) # e.g. STAGE_TRANSITION, ASSIGNMENT, ALTERATION
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True) # e.g., {"old_stage": "...", "new_stage": "...", "comments": "..."}

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.order.order_id} - {self.event_type} at {self.timestamp}"

class OrderStageHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='stage_histories')
    stage = models.CharField(max_length=100)
    comments = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='stage_images/', blank=True, null=True)
    completed_by_name = models.CharField(max_length=255, blank=True, null=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order.order_id} - {self.stage}"

class Notification(models.Model):
    title = models.CharField(max_length=255)
    message = models.TextField()
    recipient_role = models.CharField(max_length=50) # Owner, Master, Tailor, Customer
    recipient_email = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.recipient_role} - {self.title}"

def get_default_workflow():
    return [
        {"key": "created", "name": "Created", "sla_hours": 12, "roles": ["Owner", "Master"]},
        {"key": "measurements_completed", "name": "Measurements Completed", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "fabric_confirmed", "name": "Fabric Confirmed", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "pattern_cutting", "name": "Pattern Cutting", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "assigned_to_tailor", "name": "Assigned to Tailor", "sla_hours": 12, "roles": ["Owner", "Master"]},
        {"key": "stitching_in_progress", "name": "Stitching In Progress", "sla_hours": 72, "roles": ["Owner", "Tailor"]},
        {"key": "stitching_completed", "name": "Stitching Completed", "sla_hours": 12, "roles": ["Owner", "Tailor"]},
        {"key": "master_quality_check", "name": "Master Quality Check", "sla_hours": 12, "roles": ["Owner", "Master"]},
        {"key": "trial_scheduled", "name": "Trial Scheduled", "sla_hours": 48, "roles": ["Owner", "Master"]},
        {"key": "trial_completed", "name": "Trial Completed", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "ready_for_delivery", "name": "Ready for Delivery", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "delivered", "name": "Delivered", "sla_hours": 12, "roles": ["Owner", "Master"]}
    ]

class BoutiqueSettings(models.Model):
    name = models.CharField(max_length=255, default="Scaleezy Atelier")
    address = models.TextField(default="123 Atelier Way, Fashion District")
    phone = models.CharField(max_length=50, default="+91 9999999999")
    email = models.EmailField(default="contact@scaleezy.com")
    logo = models.ImageField(upload_to='fabrics/', blank=True, null=True)
    workflow_config = models.JSONField(default=get_default_workflow, blank=True)

    def __str__(self):
        return self.name
