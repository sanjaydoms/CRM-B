from django.urls import path
from apps.email_service.controllers import SendEmailAPIView, SendBulkEmailAPIView


urlpatterns = [
    path('send/', SendEmailAPIView.as_view(), name='send-email'),
    path('send-bulk/', SendBulkEmailAPIView.as_view(), name='send-bulk-email'),
    path('send-many/', SendBulkEmailAPIView.as_view(), name='send-many-email'),
]

