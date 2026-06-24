from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, TailorViewSet, BoutiqueFabricViewSet, BoutiqueDesignViewSet, OrderViewSet, DashboardView
from .auth_views import SignupView, LoginView, LogoutView, MeView

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'tailors', TailorViewSet, basename='tailor')
router.register(r'fabrics', BoutiqueFabricViewSet, basename='fabric')
router.register(r'boutique-designs', BoutiqueDesignViewSet, basename='boutique-design')
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('auth/signup/', SignupView.as_view(), name='auth-signup'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
]

