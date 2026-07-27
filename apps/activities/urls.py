from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UniversalActivityViewSet

router = DefaultRouter()
router.register(r'activities', UniversalActivityViewSet, basename='universal-activity')

urlpatterns = [
    path('', include(router.urls)),
]
