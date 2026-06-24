from django.contrib import admin
from .models import Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign

class MeasurementInline(admin.StackedInline):
    model = Measurement
    can_delete = False
    verbose_name_plural = 'Body Measurements'
    extra = 1

class DesignPreferenceInline(admin.TabularInline):
    model = DesignPreference
    extra = 1

class FabricSelectionInline(admin.TabularInline):
    model = FabricSelection
    extra = 1

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'mobile_number', 'email_address', 'garment_type', 'customer_type', 'created_at')
    search_fields = ('first_name', 'last_name', 'mobile_number', 'email_address')
    list_filter = ('customer_type', 'garment_type', 'source', 'created_at')
    inlines = [MeasurementInline, DesignPreferenceInline, FabricSelectionInline]

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

@admin.register(BoutiqueDesign)
class BoutiqueDesignAdmin(admin.ModelAdmin):
    list_display = ('name', 'garment_type', 'is_boutique', 'price')
    search_fields = ('name', 'garment_type', 'description')
    list_filter = ('is_boutique', 'garment_type')
