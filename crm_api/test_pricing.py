
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalog.models import GarmentTemplate
from crm_api.models import BoutiqueSettings, Customer, Order, OrderDraft, Tailor
from domains.orders import pricing
from domains.orders.tracking import build_token


class PricingTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@pricing.test"
        tenant.name = "Pricing Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username="owner@pricing.test", email="owner@pricing.test",
            password="ownerpass123")
        BoutiqueSettings.objects.get_or_create(id=1)
        self.blouse = GarmentTemplate.objects.get(key='blouse')
        self.lehenga = GarmentTemplate.objects.get(key='lehenga')
        self.api = self.client_for(self.owner)

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}',
                        HTTP_X_TENANT_ID=self.tenant.schema_name)
        return api

    MINIMAL_SPECS = {
        'blouse': {'blouse_type': 'princess'},
        'lehenga': {'lehenga_type': 'a_line'},
    }
    MINIMAL_MEASUREMENTS = {
        'blouse': {'chest': '35', 'waist': '29'},
        'lehenga': {'waist': '32', 'floor_length': '41'},
    }

    def garment(self, template, base, fabric=0, embroidery=0, customization=0,
                tailoring=0, **extra):
        entry = {
            'template': str(template.id),
            'spec': dict(self.MINIMAL_SPECS.get(template.key, {})),
            'measurements': dict(self.MINIMAL_MEASUREMENTS.get(template.key, {})),
            'pricing': {'base': base, 'fabric': fabric, 'embroidery': embroidery,
                        'customization': customization, 'tailoring': tailoring},
        }
        entry.update(extra)
        return entry

    def a_draft(self, garments, prices=None, payment=None, customer_suffix=''):
        payload = {
            'first_name': 'Lakshmi', 'last_name': 'Iyer',
            'mobile_number': f'91984501{2000 + len(customer_suffix)}{customer_suffix or "1"}'[:12],
            'email_address': f'lakshmi{customer_suffix}@pricing.test',
            'address': '44 Church Street', 'customer_type': 'Women',
            'prices': prices or {},
            'payment': payment or {'option': 'full'},
            'garments': garments,
        }
        created = self.api.post(reverse('order-draft-list'),
                                {'payload': payload, 'current_step': 6}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        return created.data['id']

    def confirm(self, draft_id):
        return self.api.post(reverse('order-draft-confirm', args=[draft_id]))


class ArithmeticTests(TenantTestCase):


    def test_tax_is_five_percent_after_discount(self):
        subtotal, taxes, total = pricing.totals_from_amounts(
            {'base_price': Decimal('1000')}, Decimal('0'), Decimal('200'))
        self.assertEqual(subtotal, Decimal('800'))
        self.assertEqual(taxes, Decimal('40.00'))
        self.assertEqual(total, Decimal('840.00'))

    def test_tax_rounds_half_up_to_the_paisa(self):
        _, taxes, _ = pricing.totals_from_amounts(
            {'base_price': Decimal('333.33')}, Decimal('0'), Decimal('0'))
        self.assertEqual(taxes, Decimal('16.67'))

    def test_discount_beyond_the_goods_is_refused(self):
        with self.assertRaises(ValueError):
            pricing.totals_from_amounts(
                {'base_price': Decimal('100')}, Decimal('0'), Decimal('101'))

    def test_the_column_ceiling_is_refused_with_words(self):
        with self.assertRaises(ValueError):
            pricing.totals_from_amounts(
                {'base_price': Decimal('99999999')}, Decimal('0'), Decimal('0'))

    def test_negative_components_are_refused(self):
        with self.assertRaises(ValueError):
            pricing.validate_components({'base_price': Decimal('-1')})


class MultiGarmentPricingTests(PricingTestBase):
    def test_two_garments_carry_their_own_prices_and_the_order_sums_them(self):
        draft = self.a_draft([
            self.garment(self.blouse, base=4000, tailoring=1500),
            self.garment(self.lehenga, base=32000, embroidery=7500),
        ])
        response = self.confirm(draft)
        self.assertEqual(response.status_code, 201, response.data)

        order = Order.objects.get()
        jobs = {j.template.key: j for j in order.garment_jobs.all()}
        self.assertEqual(jobs['blouse'].base_price, Decimal('4000.00'))
        self.assertEqual(jobs['blouse'].tailoring_charges, Decimal('1500.00'))
        self.assertEqual(jobs['lehenga'].base_price, Decimal('32000.00'))
        self.assertEqual(jobs['lehenga'].embroidery_price, Decimal('7500.00'))

        self.assertEqual(order.base_price, Decimal('36000.00'))
        self.assertEqual(order.tailoring_charges, Decimal('1500.00'))
        self.assertEqual(order.embroidery_price, Decimal('7500.00'))
        goods = Decimal('45000.00')
        self.assertEqual(order.taxes, (goods * Decimal('0.05')).quantize(Decimal('0.01')))
        self.assertEqual(order.total_amount, goods + order.taxes)

    def test_two_garments_with_different_addons_stay_distinct(self):
        draft = self.a_draft([
            self.garment(self.blouse, base=3000, customization=800),
            self.garment(self.lehenga, base=28000, fabric=6000),
        ])
        self.confirm(draft)
        order = Order.objects.get()
        jobs = {j.template.key: j for j in order.garment_jobs.all()}
        self.assertEqual(jobs['blouse'].customization_price, Decimal('800.00'))
        self.assertEqual(jobs['blouse'].fabric_price, Decimal('0.00'))
        self.assertEqual(jobs['lehenga'].fabric_price, Decimal('6000.00'))
        self.assertEqual(jobs['lehenga'].customization_price, Decimal('0.00'))
        self.assertEqual(pricing.job_subtotal(jobs['blouse']), Decimal('3800.00'))
        self.assertEqual(pricing.job_subtotal(jobs['lehenga']), Decimal('34000.00'))

    def test_the_same_garment_type_twice_is_two_bills_not_one(self):
        draft = self.a_draft([
            self.garment(self.blouse, base=3000),
            self.garment(self.blouse, base=4500, embroidery=1200),
        ])
        self.confirm(draft)
        order = Order.objects.get()
        bases = sorted(j.base_price for j in order.garment_jobs.all())
        self.assertEqual(bases, [Decimal('3000.00'), Decimal('4500.00')])
        self.assertEqual(order.base_price, Decimal('7500.00'))
        self.assertEqual(order.embroidery_price, Decimal('1200.00'))

    def test_zero_priced_optional_work_is_a_real_zero(self):
        draft = self.a_draft([
            self.garment(self.blouse, base=3000, embroidery=0),
        ])
        self.confirm(draft)
        order = Order.objects.get()
        job = order.garment_jobs.get()
        self.assertEqual(job.embroidery_price, Decimal('0.00'))
        self.assertEqual(order.total_amount,
                         (Decimal('3000') * Decimal('1.05')).quantize(Decimal('0.01')))

    def test_discount_is_order_level_and_applied_before_tax(self):
        draft = self.a_draft(
            [self.garment(self.blouse, base=4000),
             self.garment(self.lehenga, base=32000)],
            prices={'packaging': 500, 'discount': 2500})
        self.confirm(draft)
        order = Order.objects.get()
        self.assertEqual(order.discount, Decimal('2500.00'))
        goods = Decimal('4000') + Decimal('32000') + Decimal('500') - Decimal('2500')
        self.assertEqual(order.taxes, (goods * Decimal('0.05')).quantize(Decimal('0.01')))
        self.assertEqual(order.total_amount, goods + order.taxes)

    def test_tax_is_computed_on_the_multi_garment_subtotal(self):
        draft = self.a_draft([
            self.garment(self.blouse, base=1000),
            self.garment(self.lehenga, base=2000),
        ])
        self.confirm(draft)
        order = Order.objects.get()
        self.assertEqual(order.taxes, Decimal('150.00'))
        self.assertEqual(order.total_amount, Decimal('3150.00'))


class PaymentAgainstCanonicalTotalTests(PricingTestBase):
    def _two_garment_draft(self, payment):
        return self.a_draft(
            [self.garment(self.blouse, base=4000),
             self.garment(self.lehenga, base=32000)],
            payment=payment)

    def test_partial_payment_records_the_advance_and_the_balance(self):
        draft = self._two_garment_draft({'option': 'partial', 'advance': 10000})
        self.confirm(draft)
        order = Order.objects.get()
        self.assertEqual(order.payment_status, 'Partially Paid')
        self.assertEqual(order.advance_paid, Decimal('10000.00'))
        self.assertEqual(order.amount_paid, Decimal('10000.00'))
        self.assertEqual(order.total_amount - order.amount_paid, Decimal('27800.00'))

    def test_an_advance_larger_than_the_order_is_clamped_to_it(self):
        draft = self._two_garment_draft({'option': 'partial', 'advance': 999999})
        self.confirm(draft)
        order = Order.objects.get()
        self.assertEqual(order.amount_paid, order.total_amount)

    def test_full_payment_pays_the_canonical_total_exactly(self):
        draft = self._two_garment_draft({'option': 'full'})
        self.confirm(draft)
        order = Order.objects.get()
        self.assertEqual(order.payment_status, 'Paid')
        self.assertEqual(order.amount_paid, order.total_amount)
        self.assertEqual(order.total_amount, Decimal('37800.00'))


class EverySurfaceOneNumberTests(PricingTestBase):


    def _confirmed_order(self):
        draft = self.a_draft(
            [self.garment(self.blouse, base=4000, tailoring=1500),
             self.garment(self.lehenga, base=32000, embroidery=7500)],
            prices={'packaging': 500, 'discount': 2000},
            payment={'option': 'partial', 'advance': 10000})
        response = self.confirm(draft)
        self.assertEqual(response.status_code, 201, response.data)
        return Order.objects.get(), response.data

    def test_the_invoice_identity_holds(self):
        order, data = self._confirmed_order()
        component_sum = sum((
            order.base_price, order.fabric_price, order.embroidery_price,
            order.customization_price, order.tailoring_charges,
            order.packaging_handling))
        self.assertEqual(component_sum - order.discount + order.taxes,
                         order.total_amount)
        self.assertEqual(Decimal(str(data['total_amount'])), order.total_amount)
        self.assertEqual(Decimal(str(data['discount'])), order.discount)

    def test_per_garment_lines_reach_the_client(self):
        _, data = self._confirmed_order()
        jobs = {j['template_key']: j for j in data['garment_jobs']}
        self.assertEqual(Decimal(str(jobs['blouse']['base_price'])), Decimal('4000.00'))
        self.assertEqual(Decimal(str(jobs['lehenga']['embroidery_price'])),
                         Decimal('7500.00'))

    def test_the_customer_tracking_page_shows_the_backend_total(self):
        order, _ = self._confirmed_order()
        response = Client().get(f"/track/{build_token(order)}/")
        connection.set_tenant(self.tenant)
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        from core.formatting import format_money
        self.assertIn(format_money(order.total_amount), page)
        self.assertIn(format_money(order.amount_paid), page)
        self.assertIn(format_money(order.total_amount - order.amount_paid), page)

    def test_analytics_revenue_is_the_sum_of_real_totals(self):
        order, _ = self._confirmed_order()
        response = self.api.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        stats = response.data['stats']
        self.assertEqual(Decimal(str(stats['revenue'])), order.amount_paid)

    def test_customer_lifetime_spend_uses_order_totals(self):
        order, _ = self._confirmed_order()
        response = self.api.get(reverse('customer-detail', args=[order.customer_id]))
        self.assertEqual(Decimal(str(response.data['total_spend'])), order.total_amount)


class DraftPricingLifecycleTests(PricingTestBase):
    def test_reopening_a_draft_returns_the_same_prices(self):
        garments = [self.garment(self.blouse, base=4000),
                    self.garment(self.lehenga, base=32000)]
        draft = self.a_draft(garments, prices={'packaging': 500, 'discount': 100})
        reopened = self.client_for(self.owner).get(
            reverse('order-draft-detail', args=[draft]))
        payload = reopened.data['payload']
        self.assertEqual(payload['garments'][0]['pricing']['base'], 4000)
        self.assertEqual(payload['garments'][1]['pricing']['base'], 32000)
        self.assertEqual(payload['prices']['discount'], 100)
        self.assertEqual(Order.objects.count(), 0, 'still a draft, not an order')

    def test_editing_draft_prices_touches_no_order(self):
        draft = self.a_draft([self.garment(self.blouse, base=4000)])
        response = self.api.patch(
            reverse('order-draft-detail', args=[draft]),
            {'payload': {'first_name': 'Lakshmi', 'last_name': 'Iyer',
                         'mobile_number': '919845012001',
                         'garments': [self.garment(self.blouse, base=9999)]}},
            format='json')
        self.assertIn(response.status_code, (200, 202))
        self.assertEqual(Order.objects.count(), 0)

    def test_confirm_uses_the_drafts_numbers_not_the_sessions(self):
        draft = self.a_draft([self.garment(self.blouse, base=4000)])
        other_client = self.client_for(self.owner)
        response = other_client.post(reverse('order-draft-confirm', args=[draft]))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Order.objects.get().total_amount, Decimal('4200.00'))

    def test_a_second_confirm_cannot_duplicate_or_alter_the_bill(self):
        draft = self.a_draft([self.garment(self.blouse, base=4000)])
        first = self.confirm(draft)
        self.assertEqual(first.status_code, 201)
        total_before = Order.objects.get().total_amount

        second = self.confirm(draft)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().total_amount, total_before)


class ManipulationTests(PricingTestBase):


    def test_client_supplied_taxes_and_total_are_ignored(self):
        garments = [self.garment(self.blouse, base=4000)]
        draft = self.a_draft(garments,
                             prices={'taxes': 1, 'total': 1, 'total_amount': 1})
        self.confirm(draft)
        order = Order.objects.get()
        self.assertEqual(order.taxes, Decimal('200.00'))
        self.assertEqual(order.total_amount, Decimal('4200.00'))

    def test_a_negative_garment_price_is_refused_and_the_draft_survives(self):
        draft = self.a_draft([self.garment(self.blouse, base=-4000)])
        response = self.confirm(draft)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderDraft.objects.count(), 1, 'draft intact to fix')

    def test_a_discount_larger_than_the_order_is_refused(self):
        draft = self.a_draft([self.garment(self.blouse, base=1000)],
                             prices={'discount': 5000})
        response = self.confirm(draft)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_flat_priced_drafts_without_garment_pricing_still_confirm(self):
        payload_garments = [{'template': str(self.blouse.id),
                             'spec': dict(self.MINIMAL_SPECS['blouse']),
                             'measurements': dict(self.MINIMAL_MEASUREMENTS['blouse'])}]
        draft = self.a_draft(payload_garments, prices={'base': 5000})
        response = self.confirm(draft)
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get()
        self.assertEqual(order.base_price, Decimal('5000.00'))
        self.assertEqual(order.total_amount, Decimal('5250.00'))
        self.assertEqual(order.garment_jobs.get().base_price, Decimal('0.00'))
