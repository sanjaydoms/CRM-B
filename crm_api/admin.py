from django.contrib import admin
from django.utils.html import format_html
from .models import Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign

class MeasurementInline(admin.StackedInline):
    model = Measurement
    can_delete = False
    verbose_name_plural = 'Body Measurements'
    extra = 0

class DesignPreferenceInline(admin.TabularInline):
    model = DesignPreference
    extra = 0

class FabricSelectionInline(admin.TabularInline):
    model = FabricSelection
    extra = 0

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('profile_image_tag', 'first_name', 'last_name', 'mobile_number', 'customer_type', 'garment_type', 'created_at')
    search_fields = ('first_name', 'last_name', 'mobile_number', 'email_address')
    list_filter = ('customer_type', 'garment_type', 'source', 'created_at')
    inlines = [MeasurementInline, DesignPreferenceInline, FabricSelectionInline]
    
    fieldsets = (
        ('Personal Info', {
            'fields': (
                ('first_name', 'last_name'),
                ('mobile_number', 'email_address'),
                ('date_of_birth', 'occupation'),
                'preferred_communication',
                ('address', 'city_region'),
                'profile_photo',
            )
        }),
        ('Garment & Occasion', {
            'fields': (
                ('customer_type', 'garment_type'),
                'occasion',
            )
        }),
        ('Design Specifications (Front-End Features)', {
            'fields': (
                ('neckline_style', 'sleeve_style'),
                ('back_style', 'length_preference'),
                ('silhouette', 'pattern_style'),
                'embellishments',
                'custom_requirements',
            )
        }),
        ('Other details', {
            'fields': (
                'source',
                'notes',
            )
        }),
    )

    def profile_image_tag(self, obj):
        if obj.profile_photo:
            return format_html('<img src="{}" style="width: 45px; height: 45px; border-radius: 50%; object-fit: cover;" />', obj.profile_photo.url)
        return "No Photo"
    profile_image_tag.short_description = 'Photo'

@admin.register(BoutiqueFabric)
class BoutiqueFabricAdmin(admin.ModelAdmin):
    list_display = ('name', 'material', 'color', 'price_per_meter', 'is_available')
    search_fields = ('name', 'material', 'color')
    list_filter = ('is_available', 'material')

@admin.register(Tailor)
class TailorAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialty', 'rating', 'status')
    search_fields = ('name', 'specialty')
    list_filter = ('status',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer', 'tailor', 'payment_status', 'order_status', 'total_amount', 'order_date')
    search_fields = ('order_id', 'customer__first_name', 'customer__last_name', 'customer__mobile_number')
    list_filter = ('payment_status', 'order_status', 'order_date')
    raw_id_fields = ('customer', 'tailor')
    
    fieldsets = (
        ('Order & Status Details', {
            'fields': (
                'order_id',
                ('customer', 'tailor'),
                ('order_status', 'payment_status'),
                'estimated_delivery',
            )
        }),
        ('Financial Breakdown', {
            'fields': (
                ('base_price', 'fabric_price'),
                ('embroidery_price', 'customization_price'),
                ('tailoring_charges', 'packaging_handling'),
                ('taxes', 'total_amount'),
            )
        }),
    )

@admin.register(BoutiqueDesign)
class BoutiqueDesignAdmin(admin.ModelAdmin):
    list_display = ('name', 'garment_type', 'is_boutique', 'price')
    search_fields = ('name', 'garment_type', 'description')
    list_filter = ('is_boutique', 'garment_type')

@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = ('customer', 'bust', 'waist', 'hips', 'shoulder', 'arm_length', 'neck', 'length')
    search_fields = ('customer__first_name', 'customer__last_name', 'customer__mobile_number')

@admin.register(DesignPreference)
class DesignPreferenceAdmin(admin.ModelAdmin):
    list_display = ('customer', 'notes')
    search_fields = ('customer__first_name', 'customer__last_name')

@admin.register(FabricSelection)
class FabricSelectionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'fabric_name', 'is_boutique_fabric', 'fabric_price')
    search_fields = ('customer__first_name', 'customer__last_name', 'fabric_name')
    list_filter = ('is_boutique_fabric',)
