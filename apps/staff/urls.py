from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import StaffProfileViewSet

router = DefaultRouter()
router.register(r'profiles', StaffProfileViewSet, basename='staff-profile')

urlpatterns = [
    path('', include(router.urls)),
]
