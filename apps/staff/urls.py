from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceSessionViewSet, DayMarkViewSet, PerformanceView,
    StaffDocumentViewSet, StaffPerformanceReviewViewSet, StaffProfileViewSet,
    TimesheetView,
)

router = DefaultRouter()
router.register(r'profiles', StaffProfileViewSet, basename='staff-profile')
router.register(r'attendance', AttendanceSessionViewSet, basename='staff-attendance')
router.register(r'reviews', StaffPerformanceReviewViewSet, basename='staff-review')
router.register(r'documents', StaffDocumentViewSet, basename='staff-document')
router.register(r'day-marks', DayMarkViewSet, basename='staff-day-mark')

urlpatterns = [
    # Its own path rather than a router action: a timesheet is a computed report
    # over sessions, not a view of one. Same reasoning as DashboardView.
    path('timesheet/', TimesheetView.as_view(), name='staff-timesheet'),
    # A computed report over attendance and the workflow, not a view of a
    # resource -- same reasoning as the timesheet and DashboardView.
    path('performance/', PerformanceView.as_view(), name='staff-performance'),
    path('', include(router.urls)),
]
