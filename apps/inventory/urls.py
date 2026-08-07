from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BillOfMaterialsViewSet, BomLineViewSet, CatalogItemViewSet, CatalogSectionViewSet,
    CustomerMaterialViewSet, InventoryItemViewSet, LocationStockViewSet,
    OrderMaterialPlanViewSet, PurchaseOrderViewSet, StockLocationViewSet,
    StockMovementViewSet, SupplierViewSet, UnitConversionViewSet,
)

router = DefaultRouter()
router.register(r'items', InventoryItemViewSet, basename='inventory-item')
router.register(r'movements', StockMovementViewSet, basename='stock-movement')
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'purchase-orders', PurchaseOrderViewSet, basename='purchase-order')
router.register(r'catalog/sections', CatalogSectionViewSet, basename='catalog-section')
router.register(r'catalog/items', CatalogItemViewSet, basename='catalog-item')
router.register(r'locations', StockLocationViewSet, basename='stock-location')
router.register(r'location-stock', LocationStockViewSet, basename='location-stock')
router.register(r'boms', BillOfMaterialsViewSet, basename='bom')
router.register(r'bom-lines', BomLineViewSet, basename='bom-line')
router.register(r'unit-conversions', UnitConversionViewSet, basename='unit-conversion')
router.register(r'material-plans', OrderMaterialPlanViewSet, basename='material-plan')
router.register(r'customer-materials', CustomerMaterialViewSet, basename='customer-material')

urlpatterns = [
    path('', include(router.urls)),
]
