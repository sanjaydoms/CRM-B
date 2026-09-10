"""Shared fixtures for the alteration tests.

One delivered order carrying two garments, the roster that works on it, and a
stocked store room -- which is the only situation an alteration can start from.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token

from apps.catalog.models import GarmentJob, GarmentTemplate
from apps.inventory.models import Category, InventoryItem, Unit
from apps.inventory.services import InventoryService
from crm_api.models import (
    BoutiqueSettings,
    Customer,
    Order,
    OrderStage,
    Tailor,
    get_default_workflow,
)

OWNER_EMAIL = 'owner@alterations.test'


class AlterationTestCase(TenantTestCase):
    """A boutique with a delivered two-garment order ready to come back."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = OWNER_EMAIL
        tenant.name = 'Alteration Atelier'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

        BoutiqueSettings.objects.get_or_create(id=1)

        self.owner = User.objects.create_user(
            username=OWNER_EMAIL, email=OWNER_EMAIL, password='ownerpass123')

        self.master = Tailor.objects.create(
            name='Ravi Kumar', specialty='Supervision', role='Master',
            user=self._staff_user('master@alterations.test'))
        self.tailor = Tailor.objects.create(
            name='Sunita Devi', specialty='Stitching', role='Tailor',
            user=self._staff_user('tailor@alterations.test'))
        self.other_tailor = Tailor.objects.create(
            name='Meena Rao', specialty='Stitching', role='Tailor',
            user=self._staff_user('other@alterations.test'))
        self.qc = Tailor.objects.create(
            name='Anil Shah', specialty='Quality', role='QC Master',
            user=self._staff_user('qc@alterations.test'))

        # Authenticated, but no Tailor and no Designer profile claims them:
        # the state a removed staff member's un-revoked token lands in.
        self.rogue = User.objects.create_user(
            username='rogue@alterations.test', email='rogue@alterations.test',
            password='roguepass123')

        self.customer = Customer.objects.create(
            first_name='Lakshmi', last_name='Iyer', mobile_number='919845012345',
            email_address='lakshmi@alterations.test', customer_type='Women',
            garment_type='Lehenga')

        self.blouse_template = GarmentTemplate.objects.create(
            key='blouse', name='Blouse', version=1, sequence=0)
        self.lehenga_template = GarmentTemplate.objects.create(
            key='lehenga', name='Lehenga', version=1, sequence=1)

        self.order = self.make_order('T2B-ALT-1', status='Delivered')
        self.blouse, self.lehenga = self.order.garment_jobs.order_by('sequence')

        self.live_order = self.make_order('T2B-ALT-2', status='Design & Creation')
        self.live_garment = self.live_order.garment_jobs.first()

        self.fabric = self.stocked('FAB-SLK-001', 'Silk Panel',
                                   Category.FABRIC, Unit.METER, 20)
        self.thread = self.stocked('STI-THR-001', 'Matching Thread',
                                   Category.STITCHING, Unit.PIECE, 5)

    # -- fixtures ---------------------------------------------------------

    def _staff_user(self, email):
        return User.objects.create_user(username=email, email=email, password='staffpass123')

    def make_order(self, order_id, status='Delivered'):
        order = Order.objects.create(
            order_id=order_id, customer=self.customer,
            tailor=self.tailor, master=self.master,
            order_status=status, production_status='COMPLETED',
            current_stage_key='delivered',
            base_price=Decimal('20000.00'), total_amount=Decimal('25000.00'),
            amount_paid=Decimal('25000.00'), payment_status='Paid',
            estimated_delivery=timezone.now().date(),
        )
        for seq, stage in enumerate(get_default_workflow()):
            OrderStage.objects.create(
                order=order, stage_key=stage['key'], stage_name=stage['name'],
                status='COMPLETED' if status == 'Delivered' else 'NOT_STARTED',
                sequence=seq, sla_hours=stage['sla_hours'],
                completed_at=timezone.now() if status == 'Delivered' else None,
            )
        for seq, template in enumerate((self.blouse_template, self.lehenga_template)):
            GarmentJob.objects.create(
                order=order, template=template, template_version=1,
                spec={'neckline': 'Boat'}, sequence=seq,
                base_price=Decimal('10000.00'),
            )
        return order

    def stocked(self, code, name, category, unit, quantity):
        item = InventoryItem.objects.create(
            item_code=code, name=name, category=category, unit=unit,
            purchase_price=Decimal('500.00'), reorder_level=Decimal('1'))
        InventoryService.stock_in(item, Decimal(quantity), user=self.owner,
                                  remarks='Opening stock')
        item.refresh_from_db()
        return item

    def token_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        return token.key

    def api_client(self, user):
        from rest_framework.test import APIClient
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token_for(user)}',
                           HTTP_X_TENANT_ID=self.tenant.schema_name)
        return client
