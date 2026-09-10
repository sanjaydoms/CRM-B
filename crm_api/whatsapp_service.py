import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_whatsapp_message(phone: str, message_text: str, session_id: str = None, tenant=None) -> dict:
    """
    Client function in Django to request whatsapp_service to send an outgoing WhatsApp message.
    Resolves session_id from tenant's WhatsAppAccount mapping if not explicitly provided.
    Authenticates using X-Internal-API-Secret header.
    """
    if not session_id and tenant:
        account = getattr(tenant, 'whatsapp_account', None)
        if account:
            session_id = account.session_id

    if not session_id:
        session_id = 'default'

    base_url = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://127.0.0.1:3001').rstrip('/')
    url = f"{base_url}/whatsapp/send-message"
    secret = getattr(settings, 'INTERNAL_API_SECRET', '')

    headers = {
        'Content-Type': 'application/json',
        'X-Internal-API-Secret': secret
    }
    payload = {
        'sessionId': session_id,
        'phone': phone,
        'message': message_text
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        content_type = response.headers.get('content-type', '')

        if content_type.startswith('application/json'):
            res_data = response.json()
        else:
            res_data = {'raw': response.text}

        return {
            'success': response.status_code == 200,
            'status_code': response.status_code,
            'data': res_data
        }
    except Exception as exc:
        logger.error(f"[Django WhatsApp Client] Failed to reach whatsapp_service for session {session_id}: {exc}")
        return {
            'success': False,
            'status_code': 500,
            'error': str(exc)
        }


def get_whatsapp_status(session_id: str = None, tenant=None) -> dict:
    """
    Client function in Django to query whatsapp_service for session connection status and QR code.
    """
    if not session_id and tenant:
        account = getattr(tenant, 'whatsapp_account', None)
        if account:
            session_id = account.session_id

    if not session_id:
        session_id = 'default'

    base_url = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://127.0.0.1:3001').rstrip('/')
    url = f"{base_url}/whatsapp/status?sessionId={session_id}"
    secret = getattr(settings, 'INTERNAL_API_SECRET', '')

    headers = {
        'Content-Type': 'application/json',
        'X-Internal-API-Secret': secret
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        content_type = response.headers.get('content-type', '')

        if response.status_code == 200 and content_type.startswith('application/json'):
            return response.json()
        return {
            'success': False,
            'connected': False,
            'status': 'disconnected',
            'qrCode': None,
            'error': f"WhatsApp service returned status code {response.status_code}"
        }
    except Exception as exc:
        logger.error(f"[Django WhatsApp Client] Failed to fetch status from whatsapp_service for session {session_id}: {exc}")
        return {
            'success': False,
            'connected': False,
            'status': 'disconnected',
            'qrCode': None,
            'error': str(exc)
        }


def reset_whatsapp_session(session_id: str = None, tenant=None) -> dict:
    """
    Client function in Django to request whatsapp_service to reset session and regenerate QR code.
    """
    if not session_id and tenant:
        account = getattr(tenant, 'whatsapp_account', None)
        if account:
            session_id = account.session_id

    if not session_id:
        session_id = 'default'

    base_url = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://127.0.0.1:3001').rstrip('/')
    url = f"{base_url}/whatsapp/reset-session"
    secret = getattr(settings, 'INTERNAL_API_SECRET', '')

    headers = {
        'Content-Type': 'application/json',
        'X-Internal-API-Secret': secret
    }
    payload = {
        'sessionId': session_id
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return {
            'success': response.status_code == 200,
            'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        }
    except Exception as exc:
        logger.error(f"[Django WhatsApp Client] Failed to reset session {session_id}: {exc}")
        return {
            'success': False,
            'error': str(exc)
        }


