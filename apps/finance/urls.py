from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ExpenseViewSet, ProfitLossView

router = DefaultRouter()
router.register(r'expenses', ExpenseViewSet, basename='expense')

urlpatterns = [
    path('profit-loss/', ProfitLossView.as_view(), name='finance-profit-loss'),
    path('', include(router.urls)),
]
