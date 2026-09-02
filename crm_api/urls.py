from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, TailorViewSet, BoutiqueFabricViewSet, BoutiqueDesignViewSet, OrderViewSet, OrderDraftViewSet, DashboardView, NotificationViewSet, BoutiqueSettingsViewSet
from .auth_views import (
    SignupView, LoginView, LogoutView, MeView, SeedDataView,
    PasswordResetRequestView, PasswordResetConfirmView, TokenRefreshView,
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'tailors', TailorViewSet, basename='tailor')
router.register(r'fabrics', BoutiqueFabricViewSet, basename='fabric')
router.register(r'boutique-designs', BoutiqueDesignViewSet, basename='boutique-design')
router.register(r'orders', OrderViewSet, basename='order')
# Registered apart from orders on purpose: a draft is not an order, and
# nothing that reads orders should be able to reach one. See
# domains/orders/drafts.py.
router.register(r'order-drafts', OrderDraftViewSet, basename='order-draft')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'boutique-settings', BoutiqueSettingsViewSet, basename='boutique-settings')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('auth/signup/', SignupView.as_view(), name='auth-signup'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
    path('auth/seed-data/', SeedDataView.as_view(), name='auth-seed-data'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(),
         name='auth-password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(),
         name='auth-password-reset-confirm'),
]

