from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

from crm_api.tracking_views import order_tracking
from tenants.views import demo_request

urlpatterns = [
    path('admin/', admin.site.urls),
    path('track/<str:token>/', order_tracking, name='order-tracking'),
    path('demo-request/', demo_request, name='demo-request'),
    path('api/superadmin/', include('superadmin.urls')),
    path('api/', include('crm_api.urls')),
    path('api/production/', include('apps.production.urls')),
    path('api/activities/', include('apps.activities.urls')),
    path('api/scheduling/', include('apps.scheduling.urls')),
    path('api/design-studio/', include('apps.design_studio.urls')),
    path('api/inventory/', include('apps.inventory.urls')),
    path('api/catalog/', include('apps.catalog.urls')),
    path('api/email/', include('apps.email_service.urls')),
]

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

