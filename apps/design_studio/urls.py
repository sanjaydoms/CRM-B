from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DesignAssetViewSet, DesignBoardViewSet, DesignContextView, DesignDiscoveryView,
    DesignerViewSet,
)

router = DefaultRouter()
router.register(r'assets', DesignAssetViewSet, basename='design-asset')
router.register(r'boards', DesignBoardViewSet, basename='design-board')
router.register(r'designers', DesignerViewSet, basename='designer')

urlpatterns = [
    path('context/', DesignContextView.as_view(), name='design-context'),
    path('discover/', DesignDiscoveryView.as_view(), name='design-discover'),
    path('', include(router.urls)),
]
