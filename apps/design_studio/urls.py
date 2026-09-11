from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DesignAssetViewSet, DesignBoardViewSet, DesignContextView, DesignDiscoveryView,
    DesignerViewSet, DesignCategoryView, DesignCatalogueView, DesignDashboardView, CollectionViewSet,
    GarmentPartImageView,
    ReferenceUploadView,
    DesignAssignmentViewSet,
)

router = DefaultRouter()
router.register(r'assets', DesignAssetViewSet, basename='design-asset')
router.register(r'boards', DesignBoardViewSet, basename='design-board')
router.register(r'designers', DesignerViewSet, basename='designer')
router.register(r'collections', CollectionViewSet, basename='collection')
router.register(r'assignments', DesignAssignmentViewSet, basename='design-assignment')

urlpatterns = [
    path('context/', DesignContextView.as_view(), name='design-context'),
    path('discover/', DesignDiscoveryView.as_view(), name='design-discover'),
    path('categories/', DesignCategoryView.as_view(), name='design-categories'),
    path('catalogue/', DesignCatalogueView.as_view(), name='design-catalogue'),
    path('part-images/', GarmentPartImageView.as_view(), name='design-part-images'),
    path('reference-upload/', ReferenceUploadView.as_view(), name='design-reference-upload'),
    path('dashboard/', DesignDashboardView.as_view(), name='design-dashboard'),
    path('', include(router.urls)),
]
