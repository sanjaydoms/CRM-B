import logging
from typing import Any, Dict

from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.email_service.services import EmailService

logger = logging.getLogger(__name__)


class EmailController:

    @classmethod
    def send_email_action(cls, request_data: Dict[str, Any]) -> Response:
        subject = request_data.get('subject')
        recipients = request_data.get('recipients') or request_data.get('recipient')
        body = request_data.get('body') or request_data.get('message')
        html_message = request_data.get('html_message')

        if isinstance(recipients, list):
            return cls.send_bulk_email_action(request_data)

        if not subject or not recipients or not body:
            return Response(
                {"error": "Please provide subject, recipient, and body."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success = EmailService.send_email(
            subject=subject,
            recipient_list=recipients,
            body=body,
            html_message=html_message,
        )

        if success:
            return Response(
                {"message": "Email sent successfully."},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"error": "Failed to send email. Please check configuration."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @classmethod
    def send_bulk_email_action(cls, request_data: Dict[str, Any]) -> Response:
        subject = request_data.get('subject')
        recipients = request_data.get('recipients') or request_data.get('recipient')
        body = request_data.get('body') or request_data.get('message')
        html_message = request_data.get('html_message')
        send_mode = request_data.get('send_mode', 'bcc')

        if not subject or not recipients or not body:
            return Response(
                {"error": "Please provide subject, recipients, and message (or body)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(recipients, str):
            recipients = [recipients]
        elif not isinstance(recipients, list):
            return Response(
                {"error": "recipients must be a list of email addresses or a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = EmailService.send_bulk_email(
            subject=subject,
            recipients=recipients,
            body=body,
            html_message=html_message,
            send_mode=send_mode,
        )

        if result.get("success"):
            return Response(
                {
                    "message": "Email sent successfully.",
                    "data": result,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "error": result.get("error", "Failed to send email. Please check configuration."),
                "data": result,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR if result.get("total_recipients", 0) > 0 else status.HTTP_400_BAD_REQUEST,
        )


class SendEmailAPIView(views.APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return EmailController.send_email_action(request.data)


class SendBulkEmailAPIView(views.APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return EmailController.send_bulk_email_action(request.data)

