"""HTTP surface: every endpoint the frontend calls, and every error it must show."""

from decimal import Decimal

from rest_framework import status

from apps.alterations.models import AlterationStatus, AlterationType
from apps.alterations.testbase import AlterationTestCase
from crm_api.models import Order
from domains.alterations import services

BASE = '/api/alterations/'


class AlterationAPITests(AlterationTestCase):

    def setUp(self):
        super().setUp()
        self.client = self.api_client(self.owner)

    def create_payload(self, **kw):
        payload = {
            'customer_id': str(self.customer.id),
            'order_id': self.order.order_id,
            'garment_job_id': str(self.blouse.id),
            'alteration_type': AlterationType.PAID_CLIENT_REQUEST,
            'issue_description': 'The waist is loose.',
            'requested_adjustments': {'waist': 'let out 1 inch'},
            'charge_amount': '750.00',
        }
        payload.update(kw)
        return payload

    def create(self, **kw):
        res = self.client.post(BASE, self.create_payload(**kw), format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        return res.data

    def post(self, alteration_id, path, body=None, expect=status.HTTP_200_OK):
        res = self.client.post(f'{BASE}{alteration_id}/{path}/', body or {}, format='json')
        self.assertEqual(res.status_code, expect, res.data)
        return res.data

    # -- create -----------------------------------------------------------

    def test_create_returns_the_full_detail(self):
        data = self.create()
        self.assertEqual(data['status'], AlterationStatus.RECEIVED)
        self.assertEqual(data['customer']['name'], 'Lakshmi Iyer')
        self.assertEqual(data['original_order']['order_id'], 'T2B-ALT-1')
        self.assertEqual(data['garment_job']['template_name'], 'Blouse')
        self.assertEqual(data['outstanding_balance'], '750.00')
        self.assertIn('start-inspection', data['available_actions'])

    def test_create_against_a_live_order_is_a_400(self):
        res = self.client.post(BASE, self.create_payload(
            order_id=self.live_order.order_id,
            garment_job_id=str(self.live_garment.id)), format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Delivered', res.data['detail'])

    def test_create_with_a_garment_from_another_order_is_a_400(self):
        res = self.client.post(BASE, self.create_payload(
            garment_job_id=str(self.live_garment.id)), format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('does not belong', res.data['detail'])

    def test_create_with_a_missing_field_is_a_400(self):
        res = self.client.post(BASE, {'customer_id': str(self.customer.id)},
                               format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('order_id', res.data)

    def test_free_alteration_with_a_charge_is_a_400(self):
        res = self.client.post(BASE, self.create_payload(
            alteration_type=AlterationType.FREE_BOUTIQUE_FAULT,
            charge_amount='500.00'), format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # -- read -------------------------------------------------------------

    def test_list_and_filters(self):
        first = self.create()
        self.create(garment_job_id=str(self.lehenga.id),
                    alteration_type=AlterationType.FREE_BOUTIQUE_FAULT,
                    charge_amount='0.00')

        self.assertEqual(len(self.client.get(BASE).data), 2)

        by_status = self.client.get(f'{BASE}?status={AlterationStatus.RECEIVED}')
        self.assertEqual(len(by_status.data), 2)

        by_type = self.client.get(
            f'{BASE}?alteration_type={AlterationType.FREE_BOUTIQUE_FAULT}')
        self.assertEqual(len(by_type.data), 1)

        by_customer = self.client.get(f'{BASE}?customer={self.customer.id}')
        self.assertEqual(len(by_customer.data), 2)

        by_order = self.client.get(f'{BASE}?order={self.order.order_id}')
        self.assertEqual(len(by_order.data), 2)

        by_garment = self.client.get(f'{BASE}?garment_job={self.blouse.id}')
        self.assertEqual(len(by_garment.data), 1)

        searched = self.client.get(f'{BASE}?search={first["alteration_number"]}')
        self.assertEqual(len(searched.data), 1)

        open_only = self.client.get(f'{BASE}?open=1')
        self.assertEqual(len(open_only.data), 2)

    def test_retrieve_carries_tasks_activities_payments_and_materials(self):
        data = self.create()
        alteration_id = data['id']
        self.post(alteration_id, 'start-inspection')
        self.post(alteration_id, 'submit-for-approval', {'charge_amount': '750.00'})
        self.post(alteration_id, 'approve')
        self.post(alteration_id, 'assign', {'tailor_id': self.tailor.id})
        self.post(alteration_id, 'payments', {'amount': '750.00'},
                  expect=status.HTTP_201_CREATED)
        self.post(alteration_id, 'materials',
                  {'item_id': str(self.fabric.id), 'quantity': '1.5'},
                  expect=status.HTTP_201_CREATED)

        detail = self.client.get(f'{BASE}{alteration_id}/').data
        self.assertEqual(len(detail['tasks']), 1)
        self.assertEqual(detail['tasks'][0]['assigned_to_name'], 'Sunita Devi')
        self.assertEqual(len(detail['payments']), 1)
        self.assertEqual(len(detail['material_lines']), 1)
        self.assertGreaterEqual(len(detail['activities']), 6)
        self.assertEqual(detail['assigned_to_name'], 'Sunita Devi')

    def test_unauthenticated_access_is_refused(self):
        from rest_framework.test import APIClient
        anon = APIClient()
        anon.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.assertEqual(anon.get(BASE).status_code, status.HTTP_401_UNAUTHORIZED)

    # -- workflow over http -----------------------------------------------

    def test_every_workflow_action(self):
        alteration_id = self.create()['id']

        self.post(alteration_id, 'start-inspection', {'notes': 'On the table.'})
        self.post(alteration_id, 'record-inspection',
                  {'inspection_notes': 'Out by an inch.',
                   'adjustments': {'waist': '+1'}})
        self.post(alteration_id, 'submit-for-approval', {'charge_amount': '750.00'})
        self.post(alteration_id, 'approve')
        self.post(alteration_id, 'assign', {'tailor_id': self.tailor.id})
        self.post(alteration_id, 'start-work')
        self.post(alteration_id, 'send-to-qc')

        failed = self.post(alteration_id, 'fail-qc', {'reason': 'Seam puckered.'})
        self.assertEqual(failed['status'], AlterationStatus.IN_PROGRESS)

        self.post(alteration_id, 'send-to-qc')
        passed = self.post(alteration_id, 'pass-qc')
        self.assertEqual(passed['status'], AlterationStatus.READY_FOR_PICKUP)

        self.post(alteration_id, 'payments', {'amount': '750.00'},
                  expect=status.HTTP_201_CREATED)
        done = self.post(alteration_id, 'complete')
        self.assertEqual(done['status'], AlterationStatus.COMPLETED)

    def test_invalid_transition_is_a_400(self):
        alteration_id = self.create()['id']
        res = self.client.post(f'{BASE}{alteration_id}/approve/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot move', res.data['detail'])

    def test_fail_qc_without_a_reason_is_a_400(self):
        alteration_id = self.create()['id']
        res = self.client.post(f'{BASE}{alteration_id}/fail-qc/', {'reason': ''},
                               format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('reason', res.data)

    def test_cancel_without_a_reason_is_a_400(self):
        alteration_id = self.create()['id']
        res = self.client.post(f'{BASE}{alteration_id}/cancel/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_with_a_reason_works(self):
        alteration_id = self.create()['id']
        data = self.post(alteration_id, 'cancel', {'reason': 'Customer withdrew.'})
        self.assertEqual(data['status'], AlterationStatus.CANCELLED)

    def test_assign_needs_a_tailor(self):
        alteration_id = self.create()['id']
        res = self.client.post(f'{BASE}{alteration_id}/assign/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('tailor_id', res.data)

    def test_unknown_alteration_is_a_404(self):
        import uuid
        res = self.client.get(f'{BASE}{uuid.uuid4()}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # -- money and materials over http ------------------------------------

    def test_payment_endpoints(self):
        alteration_id = self.create()['id']

        self.assertEqual(self.client.get(f'{BASE}{alteration_id}/payments/').data, [])

        self.post(alteration_id, 'payments',
                  {'amount': '300.00', 'payment_method': 'UPI',
                   'transaction_reference': 'UPI-1'},
                  expect=status.HTTP_201_CREATED)

        listed = self.client.get(f'{BASE}{alteration_id}/payments/').data
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['payment_method_display'], 'UPI / QR')

        balance = self.client.get(f'{BASE}{alteration_id}/outstanding-balance/').data
        self.assertEqual(balance['outstanding_balance'], '450.00')
        self.assertEqual(balance['amount_paid'], '300.00')

    def test_overpayment_over_http_is_a_400(self):
        alteration_id = self.create()['id']
        res = self.client.post(f'{BASE}{alteration_id}/payments/',
                               {'amount': '9999.00'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('more than the', res.data['detail'])

    def test_duplicate_reference_over_http_is_a_400(self):
        alteration_id = self.create()['id']
        body = {'amount': '100.00', 'transaction_reference': 'UPI-9'}
        self.post(alteration_id, 'payments', body, expect=status.HTTP_201_CREATED)
        res = self.client.post(f'{BASE}{alteration_id}/payments/', body, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_material_endpoints(self):
        alteration_id = self.create()['id']
        self.assertEqual(self.client.get(f'{BASE}{alteration_id}/materials/').data, [])

        self.post(alteration_id, 'materials',
                  {'item_id': str(self.fabric.id), 'quantity': '2', 'remarks': 'Panel'},
                  expect=status.HTTP_201_CREATED)

        listed = self.client.get(f'{BASE}{alteration_id}/materials/').data
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['material_name'], 'Silk Panel')

    def test_insufficient_stock_over_http_is_a_400(self):
        alteration_id = self.create()['id']
        res = self.client.post(f'{BASE}{alteration_id}/materials/',
                               {'item_id': str(self.fabric.id), 'quantity': '999'},
                               format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not enough', res.data['detail'])

    def test_completion_with_a_balance_over_http_is_a_400(self):
        alteration_id = self.create()['id']
        for path, body in (('start-inspection', {}),
                           ('submit-for-approval', {'charge_amount': '750.00'}),
                           ('approve', {}),
                           ('assign', {'tailor_id': self.tailor.id}),
                           ('start-work', {}), ('send-to-qc', {}), ('pass-qc', {})):
            self.post(alteration_id, path, body)

        res = self.client.post(f'{BASE}{alteration_id}/complete/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('outstanding balance', res.data['detail'])

    # -- the order is still untouched, seen from the API ------------------

    def test_the_order_is_unchanged_after_an_api_lifecycle(self):
        self.test_every_workflow_action()
        order = Order.objects.get(pk=self.order.pk)
        self.assertEqual(order.order_status, 'Delivered')
        self.assertEqual(order.amount_paid, Decimal('25000.00'))
        self.assertEqual(order.total_amount, Decimal('25000.00'))

    def test_there_is_no_generic_update_or_delete(self):
        alteration_id = self.create()['id']
        for method in (self.client.patch, self.client.put, self.client.delete):
            res = method(f'{BASE}{alteration_id}/', {'status': 'COMPLETED'},
                         format='json')
            self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
