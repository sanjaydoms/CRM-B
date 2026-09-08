import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.test import RequestFactory
from crm_api.whatsapp_views import WhatsAppWebhookView, WhatsAppSendMessageView
from crm_api.whatsapp_service import send_whatsapp_message

def test_django_whatsapp_integration():
    factory = RequestFactory()
    secret = 'scaleezy_internal_secret_key_2026'

    print("--- Test 1: Django Webhook - Unauthorized (Missing Secret) ---")
    req1 = factory.post('/api/whatsapp/webhook/', data={'phone': '919876543210', 'text': 'Hello'}, content_type='application/json')
    res1 = WhatsAppWebhookView.as_view()(req1)
    print("Status code:", res1.status_code)
    print("Data:", res1.data)
    assert res1.status_code == 401, "Expected 401 Unauthorized"

    print("\n--- Test 2: Django Webhook - Authorized (With Secret) ---")
    req2 = factory.post('/api/whatsapp/webhook/', data={'messageId': 'TEST_123', 'phone': '919876543210', 'text': 'Hello from Customer', 'direction': 'incoming'}, content_type='application/json', HTTP_X_INTERNAL_API_SECRET=secret)
    res2 = WhatsAppWebhookView.as_view()(req2)
    print("Status code:", res2.status_code)
    print("Data:", res2.data)
    assert res2.status_code == 200, "Expected 200 OK"

    print("\n--- Test 3: Django Sending Message to whatsapp_service ---")
    result = send_whatsapp_message('919876543210', 'Hello from Django Test')
    print("Result:", result)
    # result['status_code'] should be 503 (since WhatsApp client in test daemon is waiting for QR scan) or 200 (if connected)
    # The key is that HTTP communication and internal secret authentication between Django and whatsapp_service succeeded!
    assert result['status_code'] in (200, 503), f"Unexpected status code {result.get('status_code')}"

    print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    test_django_whatsapp_integration()
