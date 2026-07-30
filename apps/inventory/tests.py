from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import Notification
from .models import (
    Category, DirectStockWriteError, InventoryItem, PurchaseOrder,
    PurchaseOrderLine, StockMovement, Supplier, Unit,
)
from .services import InventoryService


class InventoryTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "inventory@test.com"
        tenant.name = "Inventory Test Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.owner = User.objects.create_user(
            username="owner@inv.test", email="owner@inv.test", password="pw12345678"
        )
        self.token = Token.objects.create(user=self.owner)
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.token.key}',
            HTTP_X_TENANT_ID=self.tenant.schema_name,
        )
        self.supplier = Supplier.objects.create(name="Rajesh Textiles")

    def make_item(self, **kw):
        defaults = dict(
            item_code=kw.pop('item_code', 'FAB-001'),
            name='Silk Dupion',
            category=Category.FABRIC,
            unit=Unit.METER,
            purchase_price=Decimal('1200.00'),
            reorder_level=Decimal('5'),
            supplier=self.supplier,
        )
        defaults.update(kw)
        item = InventoryItem.objects.create(**defaults)
        return item


class StockLedgerTests(InventoryTestBase):
    """Business rule: stock changes only through movements, and they must agree."""

    def test_stock_in_records_a_movement_with_before_and_after(self):
        item = self.make_item()
        InventoryService.stock_in(item, 50, user=self.owner)

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('50.000'))
        movement = StockMovement.objects.get(item=item)
        self.assertEqual(movement.movement_type, StockMovement.Type.STOCK_IN)
        self.assertEqual(movement.previous_stock, Decimal('0.000'))
        self.assertEqual(movement.new_stock, Decimal('50.000'))

    def test_direct_stock_edit_is_refused(self):
        """The rule that makes the ledger trustworthy."""
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)

        item.refresh_from_db()
        item.current_stock = Decimal('999')
        with self.assertRaises(DirectStockWriteError):
            item.save()

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('10.000'))

    def test_editing_a_non_stock_field_still_works(self):
        item = self.make_item()
        item.rack_location = 'A-12'
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.rack_location, 'A-12')

    def test_balance_always_matches_the_ledger(self):
        item = self.make_item()
        InventoryService.stock_in(item, 100, user=self.owner)
        InventoryService.reserve(item, 20, user=self.owner)
        InventoryService.issue(item, 15, user=self.owner)
        InventoryService.return_stock(item, 3, user=self.owner)
        InventoryService.damage(item, 2, user=self.owner)

        item.refresh_from_db()
        # 100 in, 15 issued out, 3 back, 2 damaged out = 86
        self.assertEqual(item.current_stock, Decimal('86.000'))
        # 20 reserved, 15 of it issued = 5 still reserved
        self.assertEqual(item.reserved_stock, Decimal('5.000'))
        self.assertEqual(item.available_stock, Decimal('81.000'))

        last = StockMovement.objects.filter(item=item).order_by('created_at').last()
        self.assertEqual(last.new_stock, item.current_stock)


class StockGuardTests(InventoryTestBase):

    def test_cannot_issue_more_than_exists(self):
        item = self.make_item()
        InventoryService.stock_in(item, 5, user=self.owner)
        with self.assertRaises(ValueError) as ctx:
            InventoryService.issue(item, 6, user=self.owner)
        self.assertIn('only 5', str(ctx.exception))

    def test_cannot_reserve_more_than_available(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        InventoryService.reserve(item, 7, user=self.owner)
        with self.assertRaises(ValueError):
            InventoryService.reserve(item, 4, user=self.owner)

    def test_cannot_release_more_than_reserved(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        InventoryService.reserve(item, 2, user=self.owner)
        with self.assertRaises(ValueError) as ctx:
            InventoryService.release(item, 5, user=self.owner)
        self.assertIn('only 2', str(ctx.exception))

    def test_zero_and_negative_quantities_are_refused(self):
        item = self.make_item()
        for bad in (0, -3):
            with self.assertRaises(ValueError):
                InventoryService.stock_in(item, bad, user=self.owner)

    def test_reservation_does_not_change_physical_stock(self):
        item = self.make_item()
        InventoryService.stock_in(item, 30, user=self.owner)
        InventoryService.reserve(item, 8, user=self.owner)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('30.000'))
        self.assertEqual(item.available_stock, Decimal('22.000'))

    def test_failed_movement_leaves_no_ledger_line(self):
        item = self.make_item()
        InventoryService.stock_in(item, 4, user=self.owner)
        before = StockMovement.objects.count()
        with self.assertRaises(ValueError):
            InventoryService.issue(item, 99, user=self.owner)
        self.assertEqual(StockMovement.objects.count(), before)


class StockAdjustmentTests(InventoryTestBase):

    def test_adjustment_records_the_difference_in_both_directions(self):
        item = self.make_item()
        InventoryService.stock_in(item, 20, user=self.owner)

        InventoryService.adjust(item, 18, user=self.owner)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('18.000'))

        InventoryService.adjust(item, 25, user=self.owner)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('25.000'))

        types = list(StockMovement.objects.filter(
            item=item, movement_type=StockMovement.Type.ADJUSTMENT
        ).values_list('quantity', flat=True))
        self.assertEqual(sorted(types), [Decimal('2.000'), Decimal('7.000')])

    def test_adjusting_to_the_same_figure_writes_nothing(self):
        item = self.make_item()
        InventoryService.stock_in(item, 12, user=self.owner)
        before = StockMovement.objects.count()
        self.assertIsNone(InventoryService.adjust(item, 12, user=self.owner))
        self.assertEqual(StockMovement.objects.count(), before)


class ReorderAlertTests(InventoryTestBase):

    def test_dropping_to_reorder_level_notifies_the_owner(self):
        item = self.make_item(reorder_level=Decimal('10'))
        InventoryService.stock_in(item, 30, user=self.owner)
        self.assertFalse(Notification.objects.filter(title__icontains='Reorder').exists())

        InventoryService.issue(item, 22, from_reservation=False, user=self.owner)
        self.assertTrue(Notification.objects.filter(title__icontains='Reorder level').exists())

    def test_running_out_notifies_the_owner(self):
        item = self.make_item(reorder_level=Decimal('0'))
        InventoryService.stock_in(item, 5, user=self.owner)
        InventoryService.issue(item, 5, from_reservation=False, user=self.owner)
        self.assertTrue(Notification.objects.filter(title__icontains='Out of stock').exists())

    def test_the_same_alert_is_not_repeated_while_unread(self):
        item = self.make_item(reorder_level=Decimal('10'))
        InventoryService.stock_in(item, 30, user=self.owner)
        InventoryService.issue(item, 21, from_reservation=False, user=self.owner)
        InventoryService.issue(item, 1, from_reservation=False, user=self.owner)
        self.assertEqual(
            Notification.objects.filter(title__icontains='Reorder level').count(), 1
        )


class InventoryApiTests(InventoryTestBase):

    def test_list_returns_flat_rows_with_availability(self):
        item = self.make_item()
        InventoryService.stock_in(item, 40, user=self.owner)
        InventoryService.reserve(item, 6, user=self.owner)

        response = self.client.get(reverse('inventory-item-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.json()[0]
        self.assertEqual(Decimal(row['available_stock']), Decimal('34.000'))
        self.assertNotIn('supplier_name', row)

    def test_api_cannot_write_stock_directly(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)

        response = self.client.patch(
            reverse('inventory-item-detail', args=[item.id]),
            {'current_stock': '500'}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('10.000'), 'stock must ignore direct writes')

    def test_issue_endpoint_reports_a_shortage_readably(self):
        item = self.make_item()
        InventoryService.stock_in(item, 2, user=self.owner)

        response = self.client.post(
            reverse('inventory-item-issue', args=[item.id]),
            {'quantity': '9'}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('only 2', response.json()['error'])

    def test_summary_reports_value_and_what_needs_attention(self):
        plenty = self.make_item(item_code='FAB-100', reorder_level=Decimal('2'))
        InventoryService.stock_in(plenty, 10, user=self.owner)
        low = self.make_item(item_code='BTN-001', name='Pearl Buttons',
                             category=Category.STITCHING, unit=Unit.PIECE,
                             purchase_price=Decimal('5.00'), reorder_level=Decimal('50'))
        InventoryService.stock_in(low, 20, user=self.owner)

        body = self.client.get(reverse('inventory-item-summary')).json()

        # 10 x 1200 + 20 x 5 = 12,100
        self.assertEqual(Decimal(str(body['inventory_value'])), Decimal('12100.00'))
        self.assertEqual(body['needs_reorder_count'], 1)
        self.assertEqual(body['needs_reorder'][0]['item_code'], 'BTN-001')

    def test_movements_endpoint_is_read_only(self):
        item = self.make_item()
        InventoryService.stock_in(item, 3, user=self.owner)
        response = self.client.post(reverse('stock-movement-list'), {}, format='json')
        self.assertIn(response.status_code,
                      [status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN])


class PurchaseOrderTests(InventoryTestBase):

    def _po_with_line(self, ordered=Decimal('25')):
        item = self.make_item()
        po = PurchaseOrder.objects.create(po_number='PO-001', supplier=self.supplier)
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, item=item, quantity_ordered=ordered,
            unit_cost=Decimal('1100.00'),
        )
        return po, line, item

    def test_receiving_stock_in_updates_the_item_and_the_ledger(self):
        po, line, item = self._po_with_line()

        response = self.client.post(
            reverse('purchase-order-receive', args=[po.id]),
            {'lines': [{'line_id': str(line.id), 'quantity': '25'}]}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        po.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('25.000'))
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
        self.assertTrue(StockMovement.objects.filter(
            item=item, movement_type=StockMovement.Type.PURCHASE).exists())

    def test_partial_receipt_leaves_the_order_open(self):
        po, line, item = self._po_with_line()

        self.client.post(
            reverse('purchase-order-receive', args=[po.id]),
            {'lines': [{'line_id': str(line.id), 'quantity': '10'}]}, format='json',
        )

        po.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.PARTIALLY_RECEIVED)
        self.assertEqual(line.quantity_outstanding, Decimal('15.000'))

    def test_cannot_receive_more_than_ordered(self):
        po, line, item = self._po_with_line(ordered=Decimal('5'))

        response = self.client.post(
            reverse('purchase-order-receive', args=[po.id]),
            {'lines': [{'line_id': str(line.id), 'quantity': '9'}]}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('0.000'))

    def test_purchase_order_totals(self):
        po, line, item = self._po_with_line(ordered=Decimal('10'))
        po.tax_amount = Decimal('550.00')
        po.save()
        self.assertEqual(po.subtotal, Decimal('11000.00'))
        self.assertEqual(po.total, Decimal('11550.00'))
