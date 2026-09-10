import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.test import RequestFactory
from django_tenants.utils import schema_context
from tenants.models import BoutiqueTenant, WhatsAppAccount
from crm_api.whatsapp_views import WhatsAppWebhookView, WhatsAppSendMessageView
from crm_api.whatsapp_service import send_whatsapp_message

def test_tenant_isolation():
    factory = RequestFactory()
    secret = 'scaleezy_internal_secret_key_2026'

    print("=== MULTI-TENANT WHATSAPP ISOLATION TEST ===")

    # 1. Setup Tenant A and Tenant B
    tenant_a, _ = BoutiqueTenant.objects.get_or_create(
        schema_name='tenant_a_test',
        defaults={'name': 'Boutique A', 'owner_email': 'owner_a@boutique.com'}
    )
    account_a, _ = WhatsAppAccount.objects.get_or_create(
        tenant=tenant_a,
        defaults={'session_id': 'session_tenant_a_123', 'phone_number': '919000000001'}
    )

    tenant_b, _ = BoutiqueTenant.objects.get_or_create(
        schema_name='tenant_b_test',
        defaults={'name': 'Boutique B', 'owner_email': 'owner_b@boutique.com'}
    )
    account_b, _ = WhatsAppAccount.objects.get_or_create(
        tenant=tenant_b,
        defaults={'session_id': 'session_tenant_b_456', 'phone_number': '919000000002'}
    )

    print(f"Created Tenant A: {tenant_a.name} -> Session: {account_a.session_id}")
    print(f"Created Tenant B: {tenant_b.name} -> Session: {account_b.session_id}")

    # 2. Test Incoming Message Routing to Tenant A
    print("\n--- Test 1: Incoming Message Webhook for Tenant A ---")
    payload_a = {
        'sessionId': account_a.session_id,
        'messageId': 'MSG_A_001',
        'phone': '919876543210',
        'text': 'Hello Boutique A',
        'direction': 'incoming'
    }
    req_a = factory.post('/api/whatsapp/webhook/', data=payload_a, content_type='application/json', HTTP_X_INTERNAL_API_SECRET=secret)
    res_a = WhatsAppWebhookView.as_view()(req_a)
    print("Response Status:", res_a.status_code)
    print("Response Data:", res_a.data)

    assert res_a.status_code == 200
    assert res_a.data['tenant']['schema'] == 'tenant_a_test'
    assert res_a.data['tenant']['sessionId'] == 'session_tenant_a_123'
    print("SUCCESS: Incoming message mapped strictly to Tenant A!")

    # 3. Test Incoming Message Routing to Tenant B
    print("\n--- Test 2: Incoming Message Webhook for Tenant B ---")
    payload_b = {
        'sessionId': account_b.session_id,
        'messageId': 'MSG_B_002',
        'phone': '919876543211',
        'text': 'Hello Boutique B',
        'direction': 'incoming'
    }
    req_b = factory.post('/api/whatsapp/webhook/', data=payload_b, content_type='application/json', HTTP_X_INTERNAL_API_SECRET=secret)
    res_b = WhatsAppWebhookView.as_view()(req_b)
    print("Response Status:", res_b.status_code)
    print("Response Data:", res_b.data)

    assert res_b.status_code == 200
    assert res_b.data['tenant']['schema'] == 'tenant_b_test'
    assert res_b.data['tenant']['sessionId'] == 'session_tenant_b_456'
    print("SUCCESS: Incoming message mapped strictly to Tenant B!")

    # 4. Test Outgoing Message Session Resolution for Tenant A
    print("\n--- Test 3: Outgoing Message Session Resolution for Tenant A ---")
    out_result_a = send_whatsapp_message('919876543210', 'Hello from Tenant A', tenant=tenant_a)
    print("Tenant A Send Result:", out_result_a)
    # Target status_code is 503 (since WhatsApp Baileys socket for session_tenant_a_123 is waiting for QR pairing)
    # The key assertion is that whatsapp_service receives request targeted specifically at session_tenant_a_123!
    assert 'session_tenant_a_123' in out_result_a['data'].get('message', '')

    # 5. Test Outgoing Message Session Resolution for Tenant B
    print("\n--- Test 4: Outgoing Message Session Resolution for Tenant B ---")
    out_result_b = send_whatsapp_message('919876543211', 'Hello from Tenant B', tenant=tenant_b)
    print("Tenant B Send Result:", out_result_b)
    assert 'session_tenant_b_456' in out_result_b['data'].get('message', '')

    print("\n=== ALL TENANT ISOLATION TESTS PASSED PERFECTLY! ===")

if __name__ == '__main__':
    test_tenant_isolation()
