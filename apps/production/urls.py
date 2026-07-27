from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductionTaskViewSet, QCRecordViewSet

router = DefaultRouter()
router.register(r'tasks', ProductionTaskViewSet, basename='production-task')
router.register(r'qc', QCRecordViewSet, basename='qc-record')

urlpatterns = [
    path('', include(router.urls)),
]
