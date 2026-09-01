from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AttendanceSessionViewSet, StaffProfileViewSet, TimesheetView

router = DefaultRouter()
router.register(r'profiles', StaffProfileViewSet, basename='staff-profile')
router.register(r'attendance', AttendanceSessionViewSet, basename='staff-attendance')

urlpatterns = [
    # Its own path rather than a router action: a timesheet is a computed report
    # over sessions, not a view of one. Same reasoning as DashboardView.
    path('timesheet/', TimesheetView.as_view(), name='staff-timesheet'),
    path('', include(router.urls)),
]
