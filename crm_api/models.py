from django.db import models
import re
import uuid
from urllib.parse import quote
from django.conf import settings
from django.contrib.auth.models import User


#: India. The one number this module needs to know to tell a national number
#: from an international one.
NATIONAL_NUMBER_LENGTH = 10


def whatsapp_number(raw):
    """Return ``raw`` as the digits wa.me needs, or '' if it cannot be one.

    wa.me only accepts a full international number with no trunk prefix, and
    mobile_number is free text -- no validator on the field, none in the
    serializer, none in the form. So whatever the boutique typed arrives here,
    and a link built from it verbatim opens a chat with nobody. Worse, it does
    so silently: a wrong number still renders as a working "Open WhatsApp"
    button, and the owner can mark it sent beside a link that never opened.

    Handled: a bare national number, a leading '+', the 00 international access
    code, and a national trunk zero wherever it sits -- '098765 43211',
    '0091 9876543211' and '+91 (0) 98765 43211' all reach the same person.

    Anything that cannot be made into a number of this country falls through:
    kept if it could still be a valid international number, and otherwise
    refused, so the interface says "no mobile number" rather than offering a
    link that cannot work.

    # ponytail: one national length and one default country code, which is
    # right while every customer is Indian -- a UK number typed in national
    # form would get +91 in front of it. A boutique serving more than one
    # country needs the country stored on the customer, not guessed here.
    """
    digits = re.sub(r'\D', '', raw or '')
    country_code = getattr(settings, 'WHATSAPP_COUNTRY_CODE', '91')

    if digits.startswith('00'):
        digits = digits[2:]

    # Only strip a leading country code from something too long to *be* a
    # national number: Indian mobiles legitimately start 91.
    if len(digits) > NATIONAL_NUMBER_LENGTH and digits.startswith(country_code):
        national = digits[len(country_code):]
    else:
        national = digits
    national = national.lstrip('0')

    if len(national) == NATIONAL_NUMBER_LENGTH:
        return country_code + national
    # E.164 allows at most 15 digits, and nothing shorter than 11 can carry a
    # country code plus a subscriber number.
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
    # JSON list of image paths/URLs
    reference_images = models.JSONField(default=list, blank=True)
    # Where the design came from, and any external inspiration links (Pinterest etc.)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='BOUTIQUE_CATALOG', db_index=True)
    reference_links = models.JSONField(default=list, blank=True)
    # The single design signed off for production, chosen from the references above.
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
    """Deprecated. The catalogue lives in design_studio.DesignAsset.

    Migration design_studio.0007 moved every row into the library and the
    endpoints switched over with it, so nothing writes here any more. The table
    is kept for one release as a fallback if that move needs inspecting, and is
    then dropped.
    """

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
    # A boutique with one generalist keeps using Master; larger studios split the
    # work across specialists. Both are valid, and a stage accepts either.
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
    # assigned_to is who *should* do this stage; performed_by is who actually did.
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

class CustomerMessage(models.Model):
    """One outbound message to a customer, and what became of it.

    Notification is the CRM's own inbox -- staff read it inside the app.
    This is the record of what was sent *out* to the customer, which is a
    different thing with a different lifecycle: it has a destination, a
    delivery state that a provider updates after the fact, and it has to stay
    readable as history even after the transport is swapped.

    A row is written for every automated notification regardless of whether a
    transport is configured, so an order's communication history is complete
    from the first order rather than from whenever WhatsApp is connected.
    """

    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('SENT', 'Sent'),
        ('DELIVERED', 'Delivered'),
        ('READ', 'Read'),
        ('FAILED', 'Failed'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='customer_messages')
    channel = models.CharField(max_length=30, default='whatsapp')
    # Which notification this is (order_confirmation, stage_update, ...). Named
    # rather than free text so the boutique can switch individual ones off and
    # so an approved provider template can be mapped to it later.
    template_key = models.CharField(max_length=100, db_index=True)
    # Snapshot: the number as it was when we sent, not as it is now. A customer
    # who changes their number must not rewrite where past messages went.
    to_number = models.CharField(max_length=20)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED', db_index=True)
    provider_message_id = models.CharField(max_length=255, blank=True, null=True)
    error = models.TextField(blank=True, null=True)
    # Null for automated messages; set for ones staff send by hand.
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def whatsapp_url(self):
        """Click-to-chat link that opens WhatsApp with this message ready to send.

        There is no Business API here on purpose: the owner sends from their own
        phone, so the product's job is to remove the retyping, not to automate
        the send. Following this link opens the chat with the customer and the
        body already in the box; the owner presses send.
        """
        number = whatsapp_number(self.to_number)
        if not number:
            return ''
        return f"https://wa.me/{number}?text={quote(self.body)}"

    def __str__(self):
        return f"{self.order.order_id} - {self.template_key} ({self.status})"

# Every stage keeps "Master" alongside its specialist so a boutique staffed by one
# generalist is unaffected, while a studio that has split the roles can restrict
# work to the right person. Owner is always permitted, in code, regardless.
def get_default_workflow():
    return [
        {"key": "created", "name": "Created", "sla_hours": 12, "roles": ["Owner", "Master"]},
        {"key": "measurements_completed", "name": "Measurements Completed", "sla_hours": 24, "roles": ["Owner", "Master", "Measurement Master"]},
        {"key": "fabric_confirmed", "name": "Fabric Confirmed", "sla_hours": 24, "roles": ["Owner", "Master"]},
        {"key": "pattern_cutting", "name": "Pattern Cutting", "sla_hours": 24, "roles": ["Owner", "Master", "Pattern Master", "Cutting Master"]},
        # Embroidery happens on cut fabric, before stitching. Not every garment needs
        # it -- mark the stage SKIPPED on those orders.
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
    name = models.CharField(max_length=255, default="Scaleezy Atelier")
    address = models.TextField(default="123 Atelier Way, Fashion District")
    phone = models.CharField(max_length=50, default="+91 9999999999")
    email = models.EmailField(default="contact@scaleezy.com")
    logo = models.ImageField(upload_to='fabrics/', blank=True, null=True)
    workflow_config = models.JSONField(default=get_default_workflow, blank=True)
    # Off by default: a small team is usually the owner and one or two
    # designers, and forcing every upload through a queue just to reach the
    # library they already trust is friction with no one on the other end of
    # it. A team that wants a review step turns this on per boutique.
    design_approval_required = models.BooleanField(default=False)
    # The master switch for everything sent to customers. On by default because
    # the shipped transport only logs; a boutique that connects a real one and
    # wants to go quiet flips this rather than editing code.
    customer_messaging_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name
