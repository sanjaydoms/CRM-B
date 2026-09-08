import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django_tenants.utils import schema_context
from tenants.models import WhatsAppAccount
from .whatsapp_service import send_whatsapp_message, get_whatsapp_status

logger = logging.getLogger(__name__)



class WhatsAppWebhookView(APIView):
    """
    Webhook endpoint in Django to receive incoming WhatsApp messages from whatsapp_service.
    Protected by X-Internal-API-Secret header check.
    Maps incoming session to the correct BoutiqueTenant and enters schema_context.
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        secret_header = request.headers.get('X-Internal-API-Secret')
        expected_secret = getattr(settings, 'INTERNAL_API_SECRET', '')

        if not secret_header or secret_header != expected_secret:
            logger.warning("[Django Webhook] Rejected incoming webhook: Invalid or missing X-Internal-API-Secret")
            return Response(
                {"success": False, "error": "Unauthorized: Invalid internal API secret"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        data = request.data or {}
        session_id = data.get('sessionId') or data.get('session_id') or 'default'
        message_id = data.get('messageId')
        phone = data.get('phone')
        text = data.get('text')
        direction = data.get('direction', 'incoming')
        msg_type = data.get('type', 'text')
        timestamp = data.get('timestamp')

        # Resolve tenant mapping via WhatsAppAccount
        account = WhatsAppAccount.objects.select_related('tenant').filter(session_id=session_id).first()
        tenant_name = account.tenant.name if account else 'Unknown / Default'
        tenant_schema = account.tenant.schema_name if account else 'public'

        logger.info(
            f"[Django Webhook] Incoming message ({message_id}) from {phone} mapped to Tenant '{tenant_name}' ({tenant_schema})"
        )
        print(
            f"\n[Django Webhook Received] Tenant: '{tenant_name}' ({tenant_schema}) | Session: {session_id} | ID: {message_id} | From: {phone} | Text: '{text}'\n"
        )

        # Scoped execution within tenant schema context
        with schema_context(tenant_schema):
            return Response({
                "success": True,
                "message": "Incoming message received by Django webhook",
                "tenant": {
                    "schema": tenant_schema,
                    "name": tenant_name,
                    "sessionId": session_id
                },
                "receivedMessage": {
                    "messageId": message_id,
                    "phone": phone,
                    "text": text,
                    "timestamp": timestamp,
                    "type": msg_type,
                    "direction": direction
                }
            }, status=status.HTTP_200_OK)


class WhatsAppSendMessageView(APIView):
    """
    API endpoint in Django allowing current tenant to request sending a WhatsApp text message.
    Automatically resolves the tenant's WhatsApp session.
    """

    def post(self, request):
        phone = request.data.get('phone')
        message_text = request.data.get('message')

        if not phone or not message_text:
            return Response(
                {"success": False, "error": "Both 'phone' and 'message' fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Resolve current tenant from request
        current_tenant = getattr(request, 'tenant', None)
        session_id = None
        if current_tenant and hasattr(current_tenant, 'whatsapp_account'):
            session_id = current_tenant.whatsapp_account.session_id

        result = send_whatsapp_message(
            phone=str(phone),
            message_text=str(message_text),
            session_id=session_id,
            tenant=current_tenant
        )

        if result.get('success'):
            return Response(result.get('data', {}), status=status.HTTP_200_OK)
        else:
            return Response(
                {
                    "success": False,
                    "error": result.get('error') or result.get('data', {}).get('error') or "Failed to send WhatsApp message"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WhatsAppStatusView(APIView):
    """
    API endpoint in Django for fetching the current tenant's WhatsApp connection status & QR code.
    """

    def get(self, request):
        current_tenant = getattr(request, 'tenant', None)
        session_id = None
        if current_tenant and hasattr(current_tenant, 'whatsapp_account'):
            session_id = current_tenant.whatsapp_account.session_id

        result = get_whatsapp_status(session_id=session_id, tenant=current_tenant)
        return Response(result, status=status.HTTP_200_OK)

