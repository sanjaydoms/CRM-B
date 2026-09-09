"""P&L math is money, so it gets a runnable check.

The property that matters: profit = revenue - (salaries + inventory + manual),
and each cost source is read from its own table without double-counting.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from django_tenants.test.cases import TenantTestCase

from apps.finance.models import Expense
from apps.finance import services


class ProfitLossTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = 'owner@finance.test'
        tenant.name = 'Finance Test'
        return tenant

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner@finance.test', email='owner@finance.test',
            password='pw12345678')
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.owner).key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name)

    def test_manual_expense_flows_into_profit(self):
        Expense.objects.create(category='RENT', amount=Decimal('15000.00'),
                               incurred_on=date(2026, 8, 15))
        Expense.objects.create(category='UTILITIES', amount=Decimal('3000.00'),
                               incurred_on=date(2026, 8, 20))
        pnl = services.profit_and_loss(since=date(2026, 8, 1),
                                       until=date(2026, 8, 31))
        # No orders, payouts or POs in this fresh tenant -> costs are the two
        # manual rows, revenue is zero, profit is negative by exactly them.
        self.assertEqual(pnl['costs']['manual_total'], Decimal('18000.00'))
        self.assertEqual(pnl['costs']['salaries'], Decimal('0.00'))
        self.assertEqual(pnl['costs']['inventory'], Decimal('0.00'))
        self.assertEqual(pnl['costs']['total'], Decimal('18000.00'))
        self.assertEqual(pnl['revenue']['total'], Decimal('0.00'))
        self.assertEqual(pnl['profit'], Decimal('-18000.00'))

    def test_expense_outside_window_is_excluded(self):
        Expense.objects.create(category='RENT', amount=Decimal('15000.00'),
                               incurred_on=date(2026, 7, 15))
        pnl = services.profit_and_loss(since=date(2026, 8, 1),
                                       until=date(2026, 8, 31))
        self.assertEqual(pnl['costs']['manual_total'], Decimal('0.00'))

    def test_zero_amount_expense_is_refused(self):
        resp = self.client.post('/api/finance/expenses/', {
            'category': 'RENT', 'amount': '0', 'incurred_on': '2026-08-15',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_a_tailor_cannot_read_expenses(self):
        from crm_api.models import Tailor
        u = User.objects.create_user(username='t@finance.test',
                                     password='pw12345678')
        Tailor.objects.create(name='Tee', role='Tailor', user=u)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=u).key}',
                      HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.assertEqual(c.get('/api/finance/expenses/').status_code, 403)
        self.assertEqual(c.get('/api/finance/profit-loss/').status_code, 403)
