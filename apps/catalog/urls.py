from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import GarmentJobViewSet, GarmentTemplateViewSet

router = DefaultRouter()
router.register(r'templates', GarmentTemplateViewSet, basename='garment-template')
router.register(r'jobs', GarmentJobViewSet, basename='garment-job')

urlpatterns = [
    path('', include(router.urls)),
]
