from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.alterations.views import AlterationRequestViewSet

router = DefaultRouter()
router.register(r'', AlterationRequestViewSet, basename='alteration')

urlpatterns = [
    path('', include(router.urls)),
]
