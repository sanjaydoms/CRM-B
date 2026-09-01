"""
URL configuration for boutique_crm project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

from crm_api.tracking_views import order_tracking
from tenants.views import demo_request

urlpatterns = [
    path('admin/', admin.site.urls),
    # Public: no auth, no tenant header. The signed token carries both the
    # boutique and the order, so this route is deliberately outside /api/.
    path('track/<str:token>/', order_tracking, name='order-tracking'),
    # Public for the same reason: the marketing site posts here with no token
    # and no tenant. The trailing slash is load-bearing -- APPEND_SLASH is on,
    # so a slash-less POST would 301, the browser would retry it as GET, and
    # the form body would vanish with nothing logged.
    path('demo-request/', demo_request, name='demo-request'),
    # The platform console. Mounted above 'api/' only for legibility -- they do
    # not overlap. This prefix is matched by SUPERADMIN_PREFIX in
    # tenants/middleware.py to pin the connection to the public schema; change
    # one and you must change the other.
    path('api/superadmin/', include('superadmin.urls')),
    path('api/', include('crm_api.urls')),
    path('api/production/', include('apps.production.urls')),
    path('api/activities/', include('apps.activities.urls')),
    path('api/scheduling/', include('apps.scheduling.urls')),
    path('api/design-studio/', include('apps.design_studio.urls')),
    path('api/inventory/', include('apps.inventory.urls')),
    path('api/catalog/', include('apps.catalog.urls')),
    path('api/staff/', include('apps.staff.urls')),
    path('api/payroll/', include('apps.payroll.urls')),
]

# Media is served in every environment, not just DEBUG. Uploads use
# FileSystemStorage (the Supabase driver is bypassed -- see STORAGES in
# settings), and the seeded catalogue images are committed to the repo, so the
# files are on disk wherever the app runs. The old DEBUG-only route meant that
# on Render every fabric and design image 404'd, because nothing was left to
# serve them.
#
# django.conf.urls.static.static() cannot do this: it returns an empty list when
# DEBUG is False by design, which is what hid the problem. serve() resolves
# paths under document_root and rejects traversal outside it.
#
# Uploads still live on Render's ephemeral disk, so anything a user uploads is
# lost on the next deploy. Fixing that means real object storage, not a URL
# route.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

