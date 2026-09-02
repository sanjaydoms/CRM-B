from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DepositViewSet, PayrollPeriodViewSet, PayrollRecordViewSet

router = DefaultRouter()
router.register(r'periods', PayrollPeriodViewSet, basename='payroll-period')
router.register(r'records', PayrollRecordViewSet, basename='payroll-record')
router.register(r'deposits', DepositViewSet, basename='payroll-deposit')

urlpatterns = [
    path('', include(router.urls)),
]
