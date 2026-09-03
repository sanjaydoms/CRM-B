from django.db import models
import re
import uuid
from urllib.parse import quote
from django.conf import settings
from django.contrib.auth.models import User


NATIONAL_NUMBER_LENGTH = 10


# 500, not the ImageField default of 100.
#
# What is stored is the name the STORAGE BACKEND returns, not the path
# upload_to proposed. `completed_garments/<32-hex>/<original filename>` is
# already 96 characters for an ordinary phone filename, and Cloudinary returns
# its public id -- the same path under a `media/` prefix with a random suffix
# appended -- which puts it past 100 and made Postgres reject the row with
# "value too long for type character varying(100)". A tailor submitting a
# completed garment photograph got a 500 and the order kept its old status.
#
# Wide enough for a 255-character filename, which is what a filesystem allows,
# so the limit stops depending on how the customer named the picture.
IMAGE_PATH_MAX_LENGTH = 500


def _unguessable_path(directory, filename):
    return f"{directory}/{uuid.uuid4().hex}/{filename}"


def upload_to_customer_profiles(instance, filename):
    return _unguessable_path('customer_profiles', filename)


def upload_to_completed_garments(instance, filename):
    return _unguessable_path('completed_garments', filename)


def upload_to_stage_images(instance, filename):
    return _unguessable_path('stage_images', filename)


def upload_to_finished_garments(instance, filename):
    return _unguessable_path('finished_garments', filename)


def upload_to_fabrics(instance, filename):
    return _unguessable_path('fabrics', filename)


def whatsapp_number(raw):
    digits = re.sub(r'\D', '', raw or '')
    country_code = getattr(settings, 'WHATSAPP_COUNTRY_CODE', '91')

    if digits.startswith('00'):
        digits = digits[2:]

    if len(digits) > NATIONAL_NUMBER_LENGTH and digits.startswith(country_code):
        national = digits[len(country_code):]
    else:
        national = digits
    national = national.lstrip('0')

    if len(national) == NATIONAL_NUMBER_LENGTH:
        return country_code + national
    return digits if 11 <= len(digits) <= 15 else ''

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
    
    date_of_birth = models.DateField(blank=True, null=True)
    occupation = models.CharField(max_length=100, blank=True, null=True)
    preferred_communication = models.CharField(max_length=50, default="WhatsApp") # WhatsApp, Call, Email
    notes = models.TextField(blank=True, null=True)
    
    profile_photo = models.ImageField(upload_to=upload_to_customer_profiles, blank=True, null=True,
                                      max_length=IMAGE_PATH_MAX_LENGTH)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.mobile_number})"

    def save(self, *args, **kwargs):
        if self.mobile_number:
            self.mobile_number = whatsapp_number(self.mobile_number) or self.mobile_number
        super().save(*args, **kwargs)

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
    SOURCE_CHOICES = [
        ('BOUTIQUE_CATALOG', 'Boutique Catalog'),
        ('CUSTOM_DESIGN', 'Custom Design'),
        ('PREVIOUS_DESIGN', 'Previous Design'),
        ('PINTEREST', 'Pinterest Inspiration'),
        ('GOOGLE', 'Google Images'),
        ('CUSTOMER_SKETCH', 'Customer Sketch'),
        ('DESIGNER_SKETCH', 'Designer Sketch'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='design_preferences')
    notes = models.TextField(blank=True, null=True)
    reference_images = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='BOUTIQUE_CATALOG', db_index=True)
    reference_links = models.JSONField(default=list, blank=True)
    approved_image = models.CharField(max_length=500, blank=True, null=True)
    is_approved = models.BooleanField(default=False, db_index=True)
    approved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Design Prefs for {self.customer.first_name}"

class FabricSelection(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='fabric_selections')
    is_boutique_fabric = models.BooleanField(default=True)
    fabric_name = models.CharField(max_length=150)
    fabric_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
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
    ROLE_CHOICES = [
        ('Master', 'Master (generalist)'),
        ('Tailor', 'Tailor'),
        ('Measurement Master', 'Measurement Master'),
        ('Pattern Master', 'Pattern Master'),
        ('Cutting Master', 'Cutting Master'),
        ('Maggam Master', 'Maggam Master'),
        ('Finishing Master', 'Finishing Master'),
        ('Pressing Staff', 'Pressing Staff'),
        ('QC Master', 'QC Master'),
    ]

    name = models.CharField(max_length=100)
    specialty = models.CharField(max_length=100)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    status = models.CharField(max_length=50, default="Available") # Available, Busy
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="Tailor")
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
    
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fabric_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    embroidery_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    customization_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tailoring_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    packaging_handling = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    taxes = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    advance_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    order_date = models.DateTimeField(auto_now_add=True, db_index=True)
    estimated_delivery = models.DateField(blank=True, null=True)
    tailor_comments = models.TextField(blank=True, null=True)
    completed_garment_image = models.ImageField(upload_to=upload_to_completed_garments, blank=True, null=True,
                                                max_length=IMAGE_PATH_MAX_LENGTH)
    master_verification = models.JSONField(default=dict, blank=True)
    
    garment_images_published = models.BooleanField(default=False)

    special_instructions = models.TextField(blank=True, default='')
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
    assigned_to = models.ForeignKey(
        Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_stages'
    )
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
    image = models.ImageField(upload_to=upload_to_stage_images, blank=True, null=True,
                              max_length=IMAGE_PATH_MAX_LENGTH)
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

class GarmentImage(models.Model):

    VIEW_CHOICES = [
        ('FRONT', 'Front view'),
        ('BACK', 'Back view'),
        ('LEFT', 'Left side'),
        ('RIGHT', 'Right side'),
        ('DETAIL', 'Close-up detail'),
        ('FABRIC', 'Fabric texture'),
        ('SLEEVE', 'Sleeve detail'),
        ('BLOUSE', 'Blouse detail'),
        ('DUPATTA', 'Dupatta styling'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='garment_images')
    view = models.CharField(max_length=20, choices=VIEW_CHOICES, default='FRONT')
    image = models.ImageField(upload_to=upload_to_finished_garments,
                              max_length=IMAGE_PATH_MAX_LENGTH)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['view', 'uploaded_at']

    def __str__(self):
        return f"{self.order.order_id} - {self.get_view_display()}"


class CustomerMessage(models.Model):

    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('SENT', 'Sent'),
        ('DELIVERED', 'Delivered'),
        ('READ', 'Read'),
        ('FAILED', 'Failed'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='customer_messages')
    channel = models.CharField(max_length=30, default='whatsapp')
    template_key = models.CharField(max_length=100, db_index=True)
    to_number = models.CharField(max_length=20)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED', db_index=True)
    provider_message_id = models.CharField(max_length=255, blank=True, null=True)
    error = models.TextField(blank=True, null=True)
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def whatsapp_url(self):
        number = whatsapp_number(self.to_number)
        if not number:
            return ''
        return f"https://wa.me/{number}?text={quote(self.body)}"

    def __str__(self):
        return f"{self.order.order_id} - {self.template_key} ({self.status})"

def get_default_workflow():
    return [
        {"key": "created", "name": "Created", "sla_hours": 12, "roles": ["Owner", "Master"]},
        {"key": "measurements_completed", "name": "Measurements Completed", "sla_hours": 24, "roles": ["Owner", "Master", "Measurement Master"]},
        {"key": "fabric_confirmed", "name": "Fabric Confirmed", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "pattern_cutting", "name": "Pattern Cutting", "sla_hours": 24, "roles": ["Owner", "Master", "Pattern Master", "Cutting Master"]},
        {"key": "maggam_work", "name": "Maggam Work", "sla_hours": 96, "roles": ["Owner", "Master", "Maggam Master"], "optional": True},
        {"key": "assigned_to_tailor", "name": "Assigned to Tailor", "sla_hours": 12, "roles": ["Owner", "Master"]},
        {"key": "stitching_in_progress", "name": "Stitching In Progress", "sla_hours": 72, "roles": ["Owner", "Tailor"]},
        {"key": "stitching_completed", "name": "Stitching Completed", "sla_hours": 12, "roles": ["Owner", "Tailor"]},
        {"key": "finishing", "name": "Hemming & Finishing", "sla_hours": 24, "roles": ["Owner", "Master", "Finishing Master"]},
        {"key": "pressing", "name": "Pressing", "sla_hours": 12, "roles": ["Owner", "Master", "Pressing Staff"]},
        {"key": "master_quality_check", "name": "Master Quality Check", "sla_hours": 12, "roles": ["Owner", "Master", "QC Master"]},
        {"key": "trial_scheduled", "name": "Trial Scheduled", "sla_hours": 48, "roles": ["Owner", "Master"]},
        {"key": "trial_completed", "name": "Trial Completed", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "ready_for_delivery", "name": "Ready for Delivery", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "delivered", "name": "Delivered", "sla_hours": 12, "roles": ["Owner", "Master"]}
    ]

class BoutiqueSettings(models.Model):
    name = models.CharField(max_length=255, blank=True, default="")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    logo = models.ImageField(upload_to=upload_to_fabrics, blank=True, null=True,
                             max_length=IMAGE_PATH_MAX_LENGTH)
    workflow_config = models.JSONField(default=get_default_workflow, blank=True)
    design_approval_required = models.BooleanField(default=False)
    customer_messaging_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class OrderDraft(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='order_drafts')
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_drafts')
    payload = models.JSONField(default=dict, blank=True)
    current_step = models.PositiveSmallIntegerField(default=1)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        who = self.customer or self.payload.get('first_name') or 'unnamed'
        return f"Draft for {who} (step {self.current_step})"
