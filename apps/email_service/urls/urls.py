from django.urls import path
from apps.email_service.controllers import (
    SendEmailAPIView,
    SendBulkEmailAPIView,
    QueueEmailAPIView,
    EmailJobStatusAPIView,
)


urlpatterns = [
    path('send/', SendEmailAPIView.as_view(), name='send-email'),
    path('send-bulk/', SendBulkEmailAPIView.as_view(), name='send-bulk-email'),
    path('send-many/', SendBulkEmailAPIView.as_view(), name='send-many-email'),
    path('queue/', QueueEmailAPIView.as_view(), name='queue-email'),
    path('send-async/', QueueEmailAPIView.as_view(), name='send-async-email'),
    path('jobs/<str:job_id>/', EmailJobStatusAPIView.as_view(), name='email-job-status'),
]


