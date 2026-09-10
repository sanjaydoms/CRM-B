
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .api_views import (AuditView, BoutiqueModulesView, ConfigView, ErrorDetailView,
                        ErrorsView, ErrorSummaryView, FlagDetailView, FlagsView,
                        HealthView, ModulesView, OnboardingView, OrdersMonitorView,
                        SearchView, SupportView, UserActionView, UsersView)
from .views import (BoutiqueDataView, LeadViewSet, OverviewView,
                    PlatformLoginView, PlatformLogoutView, PlatformMeView,
                    TenantViewSet)

router = SimpleRouter()
router.register(r'leads', LeadViewSet, basename='superadmin-lead')

urlpatterns = [
    path('auth/login/', PlatformLoginView.as_view(), name='superadmin-login'),
    path('auth/logout/', PlatformLogoutView.as_view(), name='superadmin-logout'),
    path('auth/me/', PlatformMeView.as_view(), name='superadmin-me'),

    path('overview/', OverviewView.as_view(), name='superadmin-overview'),

    path('boutiques/', TenantViewSet.as_view({'get': 'list'}),
         name='superadmin-boutiques'),
    path('boutiques/<str:schema_name>/', TenantViewSet.as_view({'get': 'retrieve'}),
         name='superadmin-boutique'),
    path('boutiques/<str:schema_name>/suspend/',
         TenantViewSet.as_view({'post': 'suspend'}), name='superadmin-suspend'),
    path('boutiques/<str:schema_name>/reactivate/',
         TenantViewSet.as_view({'post': 'reactivate'}), name='superadmin-reactivate'),

    path('boutiques/<str:schema_name>/data/',
         BoutiqueDataView.as_view(), name='superadmin-data'),
    path('boutiques/<str:schema_name>/data/<str:key>/',
         BoutiqueDataView.as_view(), name='superadmin-dataset'),


    path('users/', UsersView.as_view(), name='superadmin-users'),
    path('users/<str:schema_name>/<str:username>/<str:action>/',
         UserActionView.as_view(), name='superadmin-user-action'),

    path('onboarding/', OnboardingView.as_view(), name='superadmin-onboarding'),
    path('onboarding/<str:schema_name>/', OnboardingView.as_view(),
         name='superadmin-onboarding-detail'),

    path('modules/', ModulesView.as_view(), name='superadmin-modules'),
    path('boutiques/<str:schema_name>/modules/', BoutiqueModulesView.as_view(),
         name='superadmin-boutique-modules'),

    path('flags/', FlagsView.as_view(), name='superadmin-flags'),
    path('flags/<str:key>/', FlagDetailView.as_view(), name='superadmin-flag'),

    path('config/', ConfigView.as_view(), name='superadmin-config'),
    path('health/', HealthView.as_view(), name='superadmin-health'),

    path('errors/', ErrorsView.as_view(), name='superadmin-errors'),
    path('errors/summary/', ErrorSummaryView.as_view(), name='superadmin-error-summary'),
    path('errors/<int:pk>/', ErrorDetailView.as_view(), name='superadmin-error'),

    path('audit/', AuditView.as_view(), name='superadmin-audit'),

    path('orders/', OrdersMonitorView.as_view(), name='superadmin-orders'),
    path('orders/<str:schema_name>/', OrdersMonitorView.as_view(),
         name='superadmin-orders-boutique'),

    path('search/', SearchView.as_view(), name='superadmin-search'),
    path('support/<str:schema_name>/', SupportView.as_view(), name='superadmin-support'),

    path('', include(router.urls)),
]
