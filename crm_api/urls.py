from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, TailorViewSet, BoutiqueDesignViewSet, OrderViewSet, OrderDraftViewSet, DashboardView, NotificationViewSet, BoutiqueSettingsViewSet
from .client_errors import ClientErrorView
from .auth_views import (
    SignupView, LoginView, LogoutView, MeView, SeedDataView,
    PasswordResetRequestView, PasswordResetConfirmView,
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'tailors', TailorViewSet, basename='tailor')
router.register(r'boutique-designs', BoutiqueDesignViewSet, basename='boutique-design')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'order-drafts', OrderDraftViewSet, basename='order-draft')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'boutique-settings', BoutiqueSettingsViewSet, basename='boutique-settings')

from .whatsapp_views import WhatsAppWebhookView, WhatsAppSendMessageView, WhatsAppStatusView, WhatsAppResetView
from .invoice_views import InvoiceTemplateView

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('client-errors/', ClientErrorView.as_view(), name='client-errors'),
    path('auth/signup/', SignupView.as_view(), name='auth-signup'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
    path('auth/seed-data/', SeedDataView.as_view(), name='auth-seed-data'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(),
         name='auth-password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(),
         name='auth-password-reset-confirm'),
    path('settings/invoice-template/', InvoiceTemplateView.as_view(), name='settings-invoice-template'),
    path('whatsapp/webhook/', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    path('whatsapp/send/', WhatsAppSendMessageView.as_view(), name='whatsapp-send'),
    path('whatsapp/status/', WhatsAppStatusView.as_view(), name='whatsapp-status'),
    path('whatsapp/reset/', WhatsAppResetView.as_view(), name='whatsapp-reset'),
    path('whatsapp/connect/', WhatsAppResetView.as_view(), name='whatsapp-connect'),
]


