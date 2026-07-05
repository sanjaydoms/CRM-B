from django.db import models
import uuid
from django.contrib.auth.models import User

class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    mobile_number = models.CharField(max_length=20, unique=True)
    email_address = models.EmailField(max_length=254, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city_region = models.CharField(max_length=100, blank=True, null=True)
    source = models.CharField(max_length=50, default="Walk In") # Walk In, Instagram, Referral, etc.
    customer_type = models.CharField(max_length=50, default="Women") # Women, Men, Kids
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
    
    created_at = models.DateTimeField(auto_now_add=True)
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
    order_id = models.CharField(max_length=50, unique=True) # e.g. T2B-240529-7856
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    tailor = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    master = models.ForeignKey(Tailor, on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_orders')
    payment_status = models.CharField(max_length=50, default="Pending") # Pending, Paid
    order_status = models.CharField(max_length=50, default="Received") # Received, Confirmed, Stylist Review, Design & Creation, Quality Check, Ready for Dispatch, Shipped, Delivered
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
    
    order_date = models.DateTimeField(auto_now_add=True)
    estimated_delivery = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"Order {self.order_id} - {self.customer.first_name} {self.customer.last_name}"
