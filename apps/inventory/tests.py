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

    def test_issuing_without_a_reservation_works(self):
        """Material is often handed to the workroom without being reserved first."""
        item = self.make_item()
        InventoryService.stock_in(item, 40, user=self.owner)

        InventoryService.issue(item, 15, user=self.owner)

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('25.000'))
        self.assertEqual(item.reserved_stock, Decimal('0.000'))

    def test_issuing_more_than_reserved_takes_the_rest_from_free_stock(self):
        item = self.make_item()
        InventoryService.stock_in(item, 40, user=self.owner)
        InventoryService.reserve(item, 5, user=self.owner)

        InventoryService.issue(item, 12, user=self.owner)

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('28.000'))
        self.assertEqual(item.reserved_stock, Decimal('0.000'), 'the reservation is consumed, not left negative')
        self.assertEqual(item.available_stock, Decimal('28.000'))

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

        InventoryService.issue(item, 22, user=self.owner)
        self.assertTrue(Notification.objects.filter(title__icontains='Reorder level').exists())

    def test_running_out_notifies_the_owner(self):
        item = self.make_item(reorder_level=Decimal('0'))
        InventoryService.stock_in(item, 5, user=self.owner)
        InventoryService.issue(item, 5, user=self.owner)
        self.assertTrue(Notification.objects.filter(title__icontains='Out of stock').exists())

    def test_the_same_alert_is_not_repeated_while_unread(self):
        item = self.make_item(reorder_level=Decimal('10'))
        InventoryService.stock_in(item, 30, user=self.owner)
        InventoryService.issue(item, 21, user=self.owner)
        InventoryService.issue(item, 1, user=self.owner)
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
        row = response.json()['results'][0]
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

    def test_a_rejected_line_rolls_back_the_lines_before_it(self):
        """The multi-line receipt that used to leave half a delivery in stock.

        Each InventoryService.purchase() is its own atomic block, so the earlier
        lines committed before the later one raised. The owner was told the
        receipt failed while the first items were already booked in -- and
        correcting the typo and resubmitting counted them twice, permanently.
        """
        item_a = self.make_item(item_code='FAB-ATOM-A', name='Silk Roll A')
        item_b = self.make_item(item_code='FAB-ATOM-B', name='Silk Roll B')
        po = PurchaseOrder.objects.create(po_number='PO-ATOMIC', supplier=self.supplier)
        line_a = PurchaseOrderLine.objects.create(
            purchase_order=po, item=item_a, quantity_ordered=Decimal('10'),
            unit_cost=Decimal('100.00'))
        line_b = PurchaseOrderLine.objects.create(
            purchase_order=po, item=item_b, quantity_ordered=Decimal('5'),
            unit_cost=Decimal('100.00'))

        response = self.client.post(
            reverse('purchase-order-receive', args=[po.id]),
            {'lines': [
                {'line_id': str(line_a.id), 'quantity': '10'},   # fine
                {'line_id': str(line_b.id), 'quantity': '99'},   # over-receipt
            ]}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        item_a.refresh_from_db()
        line_a.refresh_from_db()
        po.refresh_from_db()
        # Nothing of the first line survived the failure of the second.
        self.assertEqual(item_a.current_stock, Decimal('0.000'))
        self.assertEqual(line_a.quantity_received, Decimal('0.000'))
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)
        self.assertFalse(StockMovement.objects.filter(item=item_a).exists())

    def test_a_junk_quantity_is_a_400_not_a_500(self):
        # Decimal('abc') raises InvalidOperation -- an ArithmeticError, which
        # escaped the ValueError handler as an unhandled server error.
        po, line, item = self._po_with_line()
        response = self.client.post(
            reverse('purchase-order-receive', args=[po.id]),
            {'lines': [{'line_id': str(line.id), 'quantity': 'abc'}]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('0.000'))

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


class CatalogSeedTests(InventoryTestBase):
    """The published catalogue is loaded whole.

    The specification's central rule is that no category, sub-category or item
    from the two source documents may be omitted, merged or renamed. Asserting a
    count would only catch a wholesale failure, so these tests re-parse the
    originals -- which are committed alongside the code in catalog_sources/ --
    and compare them against the database name by name. If someone edits a
    source document without regenerating catalog_definitions.py, or quietly drops
    a row from it, this fails and says exactly which item went missing.
    """

    SKIP_SECTIONS = {
        # A recap of items already listed above it, not new catalogue entries.
        'Common Materials Used in Bridal Maggam Work',
        # Numbered prose, not a material list.
        'Complete Workflow (Apparel Lifecycle)',
    }

    @classmethod
    def _parse_source(cls, filename):
        """(section, subsection, item) for every bullet in a source document."""
        import re
        from pathlib import Path

        path = Path(__file__).resolve().parent / 'catalog_sources' / filename
        section = subsection = None
        rows = []
        for raw in path.read_text(encoding='utf-8').splitlines():
            if raw.startswith('## '):
                heading = raw[3:].strip()
                match = re.match(r'^(\d+)\.\s+(.*)$', heading)
                section = match.group(2) if match else heading
                subsection = None
                continue
            if raw.startswith('### '):
                subsection = raw[4:].strip()
                continue
            match = re.match(r'^- (.+)$', raw)
            if match and section and section not in cls.SKIP_SECTIONS:
                name = re.sub(r'\s*\*\(.*?\)\*\s*$', '', match.group(1).strip())
                rows.append((section, subsection, name))
        return rows

    def _source_rows(self):
        return (self._parse_source('01-maggam-embroidery-materials.md')
                + self._parse_source('02-apparel-ecosystem-checklist.md'))

    def test_catalog_matches_the_source_documents(self):
        from .models import CatalogItem

        expected = {(sec, sub, name) for sec, sub, name in self._source_rows()}
        actual = {
            (item.section.name, item.section.subsection, item.name)
            for item in CatalogItem.objects.select_related('section')
        }

        missing = expected - actual
        extra = actual - expected
        self.assertFalse(missing, f"{len(missing)} catalogue item(s) missing: {sorted(missing)[:15]}")
        self.assertFalse(extra, f"{len(extra)} item(s) not in any source document: {sorted(extra)[:15]}")

    def test_every_source_section_exists_unmerged(self):
        from .models import CatalogSection

        expected = {(sec, sub) for sec, sub, _ in self._source_rows()}
        actual = set(CatalogSection.objects.values_list('name', 'subsection'))
        self.assertEqual(expected, actual)

    def test_catalog_covers_both_documents(self):
        from .models import CatalogItem, CatalogSection

        self.assertEqual(
            CatalogSection.objects.filter(doc=CatalogSection.Doc.MAGGAM)
            .values('name').distinct().count(), 22)
        self.assertEqual(
            CatalogSection.objects.filter(doc=CatalogSection.Doc.APPAREL)
            .values('name').distinct().count(), 27)
        self.assertEqual(CatalogItem.objects.count(), 732)

    def test_non_stockable_rows_are_typed_as_such(self):
        """A payment gateway and a garment category cannot hold stock."""
        from .models import CatalogItem, ItemType

        for name, expected in [
            ('Payment Gateway', ItemType.SYSTEM),
            ('ERP', ItemType.SYSTEM),
            ('Sarees', ItemType.PRODUCT_CATEGORY),
            ('Sherwanis', ItemType.PRODUCT_CATEGORY),
        ]:
            for item in CatalogItem.objects.filter(name=name):
                self.assertEqual(item.item_type, expected, name)
                self.assertFalse(item.is_stockable, name)

    def test_materials_stay_stockable(self):
        from .models import CatalogItem

        for name in ('Dabka', 'Nakshi', 'Kundan Stones', 'Raw Silk', 'Seed Beads'):
            items = CatalogItem.objects.filter(name=name)
            self.assertTrue(items.exists(), f"{name} is missing from the catalogue")
            for item in items:
                self.assertTrue(item.is_stockable, name)

    def test_syncing_twice_creates_nothing_new(self):
        """A redeploy re-runs the loader; it must not duplicate the catalogue."""
        from .catalog_sync import sync_catalog
        from .models import CatalogItem, CatalogSection

        before = (CatalogSection.objects.count(), CatalogItem.objects.count())
        result = sync_catalog()
        after = (CatalogSection.objects.count(), CatalogItem.objects.count())
        self.assertEqual(before, after)
        self.assertEqual(result, {'sections': 0, 'items': 0})


class CatalogApiTests(InventoryTestBase):
    """Browsing the catalogue, and turning one of its rows into stock."""

    def test_sections_list_reports_every_section_with_counts(self):
        response = self.client.get('/api/inventory/catalog/items/sections/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 61)
        self.assertEqual(sum(row['item_count'] for row in response.data), 732)

    def test_items_can_be_filtered_by_section_name(self):
        response = self.client.get(
            '/api/inventory/catalog/items/?section_name=Traditional Zardosi Materials')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row['name'] for row in response.data['results']}
        for expected in ('Dabka', 'Nakshi', 'Kasab', 'Salma', 'Sitara'):
            self.assertIn(expected, names)

    def test_stockable_filter_excludes_systems_and_garment_categories(self):
        response = self.client.get('/api/inventory/catalog/items/?stockable=true&search=Payment')
        self.assertEqual(response.data['results'], [])

    def test_stocking_a_catalog_row_creates_an_inventory_item(self):
        from .models import CatalogItem

        dabka = CatalogItem.objects.filter(name='Dabka').first()
        response = self.client.post(f'/api/inventory/catalog/items/{dabka.id}/stock/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['name'], 'Dabka')

        item = InventoryItem.objects.get(id=response.data['id'])
        self.assertEqual(item.catalog_item_id, dabka.id)
        self.assertEqual(item.category, dabka.legacy_category)
        self.assertEqual(Decimal(str(item.current_stock)), Decimal('0'))

    def test_stocking_the_same_row_twice_does_not_duplicate_it(self):
        from .models import CatalogItem

        kundan = CatalogItem.objects.filter(name='Kundan Stones').first()
        first = self.client.post(f'/api/inventory/catalog/items/{kundan.id}/stock/', {}, format='json')
        second = self.client.post(f'/api/inventory/catalog/items/{kundan.id}/stock/', {}, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(InventoryItem.objects.filter(catalog_item=kundan).count(), 1)

    def test_a_non_stockable_row_is_refused(self):
        from .models import CatalogItem

        gateway = CatalogItem.objects.filter(name='Payment Gateway').first()
        response = self.client.post(f'/api/inventory/catalog/items/{gateway.id}/stock/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot hold stock', response.data['detail'])
        self.assertFalse(InventoryItem.objects.filter(catalog_item=gateway).exists())

    def test_stocked_rows_report_their_inventory_item(self):
        from .models import CatalogItem

        zari = CatalogItem.objects.filter(name='Zari Lace').first()
        created = self.client.post(f'/api/inventory/catalog/items/{zari.id}/stock/', {}, format='json')
        response = self.client.get(f'/api/inventory/catalog/items/{zari.id}/')
        self.assertEqual(response.data['stocked_item_id'], created.data['id'])


class StockLocationTests(InventoryTestBase):
    """Locations, transfers, and the invariant that ties them to the total."""

    def setUp(self):
        super().setUp()
        from .models import StockLocation
        self.main = StockLocation.objects.get(is_default=True)
        self.cutting = StockLocation.objects.get(kind=StockLocation.Kind.CUTTING_UNIT)
        self.embroidery = StockLocation.objects.get(kind=StockLocation.Kind.EMBROIDERY_UNIT)

    def _breakdown(self, item):
        from .models import LocationStock
        return {
            row.location.name: row.quantity
            for row in LocationStock.objects.filter(item=item).select_related('location')
        }

    def assertLocationsSumToTotal(self, item):
        from .models import LocationStock
        item.refresh_from_db()
        total = sum(
            (row.quantity for row in LocationStock.objects.filter(item=item)),
            Decimal('0'),
        )
        self.assertEqual(
            total, item.current_stock,
            f"per-location total {total} != current_stock {item.current_stock}",
        )

    def test_the_eight_locations_are_seeded(self):
        from .models import StockLocation
        self.assertEqual(StockLocation.objects.count(), 8)
        self.assertEqual(
            set(StockLocation.objects.values_list('kind', flat=True)),
            set(StockLocation.Kind.values),
        )

    def test_exactly_one_location_is_the_default(self):
        from .models import StockLocation
        self.assertEqual(StockLocation.objects.filter(is_default=True).count(), 1)
        self.assertEqual(self.main.kind, StockLocation.Kind.MAIN_STORE)

    def test_unlocated_stock_in_lands_at_the_default(self):
        """Every caller predates locations; none of them should have to change."""
        item = self.make_item()
        InventoryService.stock_in(item, 40, user=self.owner)
        self.assertEqual(self._breakdown(item), {'Main Store': Decimal('40.000')})
        self.assertLocationsSumToTotal(item)

    def test_transfer_moves_stock_without_changing_the_total(self):
        item = self.make_item()
        InventoryService.stock_in(item, 100, user=self.owner)

        InventoryService.transfer(item, 30, from_location=self.main,
                                  to_location=self.cutting, user=self.owner)

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('100.000'), 'a transfer is not a loss')
        self.assertEqual(self._breakdown(item),
                         {'Main Store': Decimal('70.000'), 'Cutting Unit': Decimal('30.000')})
        self.assertLocationsSumToTotal(item)

    def test_transfer_records_both_ends_on_the_ledger(self):
        item = self.make_item()
        InventoryService.stock_in(item, 50, user=self.owner)
        InventoryService.transfer(item, 20, from_location=self.main,
                                  to_location=self.embroidery, user=self.owner)

        movement = StockMovement.objects.filter(
            movement_type=StockMovement.Type.TRANSFER).get()
        self.assertEqual(movement.from_location, self.main)
        self.assertEqual(movement.to_location, self.embroidery)
        self.assertEqual(movement.previous_stock, movement.new_stock)

    def test_cannot_transfer_more_than_the_source_holds(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        with self.assertRaises(ValueError) as ctx:
            InventoryService.transfer(item, 25, from_location=self.main,
                                      to_location=self.cutting, user=self.owner)
        self.assertIn('only 10', str(ctx.exception))
        self.assertLocationsSumToTotal(item)

    def test_a_failed_transfer_moves_nothing_at_either_end(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        before = self._breakdown(item)
        with self.assertRaises(ValueError):
            InventoryService.transfer(item, 99, from_location=self.main,
                                      to_location=self.cutting, user=self.owner)
        self.assertEqual(self._breakdown(item), before)
        self.assertFalse(
            StockMovement.objects.filter(movement_type=StockMovement.Type.TRANSFER).exists())

    def test_transfer_to_the_same_place_is_refused(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        with self.assertRaises(ValueError) as ctx:
            InventoryService.transfer(item, 5, from_location=self.main,
                                      to_location=self.main, user=self.owner)
        self.assertIn('both the source and the destination', str(ctx.exception))

    def test_issuing_from_a_unit_draws_down_that_unit(self):
        item = self.make_item()
        InventoryService.stock_in(item, 60, user=self.owner)
        InventoryService.transfer(item, 25, from_location=self.main,
                                  to_location=self.cutting, user=self.owner)

        InventoryService.consume(item, 10, from_location=self.cutting, user=self.owner)

        self.assertEqual(self._breakdown(item),
                         {'Main Store': Decimal('35.000'), 'Cutting Unit': Decimal('15.000')})
        self.assertLocationsSumToTotal(item)

    def test_cannot_consume_from_a_unit_that_does_not_hold_it(self):
        item = self.make_item()
        InventoryService.stock_in(item, 60, user=self.owner)
        with self.assertRaises(ValueError) as ctx:
            InventoryService.consume(item, 5, from_location=self.embroidery, user=self.owner)
        self.assertIn('Embroidery Unit', str(ctx.exception))

    def test_the_full_lifecycle_keeps_the_books_straight(self):
        """Receipt, transfer, consumption, waste and a return, end to end."""
        item = self.make_item()
        InventoryService.goods_receipt(item, 100, user=self.owner)
        InventoryService.transfer(item, 40, from_location=self.main,
                                  to_location=self.cutting, user=self.owner)
        InventoryService.consume(item, 25, from_location=self.cutting, user=self.owner)
        InventoryService.waste(item, 5, from_location=self.cutting, user=self.owner)
        InventoryService.return_stock(item, 3, to_location=self.main, user=self.owner)

        item.refresh_from_db()
        # 100 received, 25 consumed, 5 wasted, 3 returned = 73
        self.assertEqual(item.current_stock, Decimal('73.000'))
        self.assertEqual(self._breakdown(item),
                         {'Main Store': Decimal('63.000'), 'Cutting Unit': Decimal('10.000')})
        self.assertLocationsSumToTotal(item)


class TransactionTypeTests(InventoryTestBase):
    """The twelve transaction types the specification requires."""

    REQUIRED = [
        'PURCHASE', 'GOODS_RECEIPT', 'RESERVATION', 'RELEASE', 'CONSUMPTION',
        'RETURN', 'TRANSFER', 'ADJUSTMENT', 'DAMAGE', 'WASTE',
        'CUSTOMER_RETURN', 'SUPPLIER_RETURN',
    ]

    def test_every_required_transaction_type_exists(self):
        available = set(StockMovement.Type.values)
        missing = [t for t in self.REQUIRED if t not in available]
        self.assertFalse(missing, f'missing transaction types: {missing}')

    def test_waste_and_damage_are_separate_lines(self):
        """Waste is a production metric, damage a handling one."""
        item = self.make_item()
        InventoryService.stock_in(item, 50, user=self.owner)
        InventoryService.waste(item, 4, user=self.owner)
        InventoryService.damage(item, 3, user=self.owner)

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('43.000'))
        self.assertEqual(
            StockMovement.objects.filter(movement_type=StockMovement.Type.WASTE).count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(movement_type=StockMovement.Type.DAMAGE).count(), 1)

    def test_customer_return_puts_stock_back(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        InventoryService.customer_return(item, 2, user=self.owner)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('12.000'))

    def test_supplier_return_takes_stock_out(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        InventoryService.supplier_return(item, 4, user=self.owner)
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('6.000'))

    def test_consumption_is_distinct_from_issue(self):
        """Issuing hands material over; consuming records it went into the garment."""
        item = self.make_item()
        InventoryService.stock_in(item, 30, user=self.owner)
        InventoryService.issue(item, 10, user=self.owner)
        InventoryService.consume(item, 5, user=self.owner)

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('15.000'))
        types = list(StockMovement.objects.filter(item=item)
                     .order_by('created_at').values_list('movement_type', flat=True))
        self.assertEqual(types, ['STOCK_IN', 'ISSUE', 'CONSUMPTION'])

    def test_every_movement_stays_in_history(self):
        """Every transaction must remain in history permanently."""
        item = self.make_item()
        for op, qty in [(InventoryService.stock_in, 20), (InventoryService.reserve, 5),
                        (InventoryService.release, 5), (InventoryService.waste, 2),
                        (InventoryService.damage, 1)]:
            op(item, qty, user=self.owner)
        self.assertEqual(StockMovement.objects.filter(item=item).count(), 5)


class LocationApiTests(InventoryTestBase):

    def setUp(self):
        super().setUp()
        from .models import StockLocation
        self.main = StockLocation.objects.get(is_default=True)
        self.cutting = StockLocation.objects.get(kind=StockLocation.Kind.CUTTING_UNIT)

    def test_locations_are_listed(self):
        response = self.client.get('/api/inventory/locations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 8)

    def test_transfer_endpoint_moves_stock(self):
        item = self.make_item()
        InventoryService.stock_in(item, 50, user=self.owner)

        response = self.client.post(
            f'/api/inventory/items/{item.id}/transfer/',
            {'quantity': '20', 'from_location': str(self.main.id),
             'to_location': str(self.cutting.id)}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        breakdown = self.client.get(f'/api/inventory/items/{item.id}/locations/').data
        by_name = {row['location']: Decimal(str(row['quantity'])) for row in breakdown['breakdown']}
        self.assertEqual(by_name,
                         {'Main Store': Decimal('30.000'), 'Cutting Unit': Decimal('20.000')})

    def test_transfer_without_a_destination_is_a_400_not_a_500(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        response = self.client.post(
            f'/api/inventory/items/{item.id}/transfer/',
            {'quantity': '5', 'from_location': str(self.main.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_location_id_is_a_400(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        response = self.client.post(
            f'/api/inventory/items/{item.id}/transfer/',
            {'quantity': '5', 'from_location': str(self.main.id),
             'to_location': '00000000-0000-0000-0000-000000000000'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_location_holding_stock_cannot_be_deleted(self):
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        response = self.client.delete(f'/api/inventory/locations/{self.main.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_location_stock_endpoint_lists_what_is_held(self):
        item = self.make_item()
        InventoryService.stock_in(item, 15, user=self.owner)
        response = self.client.get(f'/api/inventory/locations/{self.main.id}/stock/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['item_name'], item.name)


class FormulaTests(TenantTestCase):
    """The quantity-formula evaluator.

    A formula comes out of the database, so it comes from whoever can write to
    the database. These tests are as much about what it refuses as what it
    computes.
    """

    def test_arithmetic(self):
        from .formula import evaluate
        self.assertEqual(evaluate('2 + 3 * 4'), Decimal('14'))
        self.assertEqual(evaluate('(2 + 3) * 4'), Decimal('20'))
        self.assertEqual(evaluate('10 / 4'), Decimal('2.5'))
        self.assertEqual(evaluate('-3 + 5'), Decimal('2'))

    def test_variables(self):
        from .formula import evaluate
        self.assertEqual(evaluate('0.15 * bust + 0.4', {'bust': 36}), Decimal('5.8'))
        self.assertEqual(evaluate('length * 2', {'length': Decimal('1.25')}), Decimal('2.5'))

    def test_whitelisted_functions(self):
        from .formula import evaluate
        self.assertEqual(evaluate('max(2, 5)'), Decimal('5'))
        self.assertEqual(evaluate('min(2, 5)'), Decimal('2'))
        self.assertEqual(evaluate('ceil(1.2)'), Decimal('2'))
        self.assertEqual(evaluate('floor(1.8)'), Decimal('1'))
        self.assertEqual(evaluate('round(2.345, 2)'), Decimal('2.35'))
        self.assertEqual(evaluate('abs(0 - 7)'), Decimal('7'))

    def test_conditional_quantity(self):
        from .formula import evaluate
        self.assertEqual(evaluate('2.2 if length > 42 else 1.9', {'length': 45}), Decimal('2.2'))
        self.assertEqual(evaluate('2.2 if length > 42 else 1.9', {'length': 40}), Decimal('1.9'))

    # --- what it must refuse -------------------------------------------

    def test_attribute_access_is_refused(self):
        """The classic sandbox escape."""
        from .formula import FormulaError, evaluate
        for hostile in [
            "().__class__",
            "(1).__class__.__bases__",
            "x.__class__.__mro__[1].__subclasses__()",
        ]:
            with self.assertRaises(FormulaError, msg=hostile):
                evaluate(hostile, {'x': 1})

    def test_calls_to_anything_unlisted_are_refused(self):
        from .formula import FormulaError, evaluate
        for hostile in [
            "__import__('os')",
            "open('/etc/passwd')",
            "eval('1+1')",
            "exec('x=1')",
            "globals()",
            "getattr(x, 'y')",
        ]:
            with self.assertRaises(FormulaError, msg=hostile):
                evaluate(hostile, {'x': 1})

    def test_subscripts_and_comprehensions_are_refused(self):
        from .formula import FormulaError, evaluate
        for hostile in ["[1,2][0]", "[i for i in range(3)]", "{1:2}[1]", "(lambda: 1)()"]:
            with self.assertRaises(FormulaError, msg=hostile):
                evaluate(hostile, {})

    def test_unknown_variable_is_reported_not_guessed(self):
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError) as ctx:
            evaluate('hips * 2', {'bust': 36})
        self.assertIn('hips', str(ctx.exception))
        self.assertIn('bust', str(ctx.exception), 'the message should say what is available')

    def test_huge_exponent_is_refused(self):
        """9**9**9 is a denial of service in four characters."""
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate('9 ** 9 ** 9')
        with self.assertRaises(FormulaError):
            evaluate('2 ** 500')

    def test_division_by_zero_is_a_formula_error(self):
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate('5 / 0')
        with self.assertRaises(FormulaError):
            evaluate('5 / (bust - bust)', {'bust': 10})

    def test_overlong_and_malformed_formulas_are_refused(self):
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate('1 +' * 400)
        with self.assertRaises(FormulaError):
            evaluate('2 +')
        with self.assertRaises(FormulaError):
            evaluate('')

    def test_strings_are_not_values(self):
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate("'abc' * 3")

    def test_variables_used_reports_names(self):
        from .formula import variables_used
        self.assertEqual(variables_used('0.1 * bust + max(waist, 2)'), {'bust', 'waist'})


class BomTests(InventoryTestBase):
    """Turning a recipe plus measurements into quantities to reserve."""

    def setUp(self):
        super().setUp()
        from .models import BillOfMaterials
        self.fabric = self.make_item(item_code='FAB-100', name='Raw Silk', unit=Unit.METER)
        self.thread = self.make_item(item_code='THR-100', name='Resham Thread',
                                     category=Category.STITCHING, unit=Unit.PIECE)
        self.bom = BillOfMaterials.objects.create(name='Bridal Blouse')

    def line(self, **kw):
        from .models import BomLine
        defaults = dict(bom=self.bom, role=BomLine.Role.FABRIC,
                        inventory_item=self.fabric, quantity=Decimal('1'), unit=Unit.METER)
        defaults.update(kw)
        return BomLine.objects.create(**defaults)

    def test_fixed_quantity(self):
        from . import bom as bom_service
        self.line(quantity=Decimal('2.5'))
        rows = bom_service.requirements(self.bom)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['required_quantity'], Decimal('2.500'))

    def test_formula_quantity_uses_the_measurements(self):
        from . import bom as bom_service
        self.line(quantity_formula='0.15 * bust + 0.4')
        rows = bom_service.requirements(self.bom, {'bust': 36})
        self.assertEqual(rows[0]['required_quantity'], Decimal('5.800'))

    def test_waste_allowance_is_added_on_top(self):
        from . import bom as bom_service
        self.line(quantity=Decimal('2'), waste_percent=Decimal('10'))
        rows = bom_service.requirements(self.bom)
        self.assertEqual(rows[0]['base_quantity'], Decimal('2.000'))
        self.assertEqual(rows[0]['required_quantity'], Decimal('2.200'))

    def test_waste_applies_to_the_formula_result(self):
        from . import bom as bom_service
        self.line(quantity_formula='2 * panels', waste_percent=Decimal('25'))
        rows = bom_service.requirements(self.bom, {'panels': 3})
        self.assertEqual(rows[0]['required_quantity'], Decimal('7.500'))

    def test_optional_lines_are_skipped_unless_asked_for(self):
        from . import bom as bom_service
        self.line(quantity=Decimal('1'))
        self.line(quantity=Decimal('5'), is_optional=True, inventory_item=self.thread,
                  unit=Unit.PIECE, sequence=2)

        self.assertEqual(len(bom_service.requirements(self.bom)), 1)
        self.assertEqual(len(bom_service.requirements(self.bom, include_optional=True)), 2)

    def test_customer_supplied_lines_are_returned_but_flagged(self):
        from . import bom as bom_service
        from .models import BomLine
        self.line(quantity=Decimal('1'))
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.FABRIC,
                               description="Customer's own gold border",
                               is_customer_supplied=True, quantity=Decimal('2'),
                               unit=Unit.METER, sequence=2)

        summary = bom_service.summarise(self.bom)
        self.assertEqual(summary['boutique_line_count'], 1)
        self.assertEqual(summary['customer_supplied_line_count'], 1)
        flagged = [r for r in summary['requirements'] if r['is_customer_supplied']]
        self.assertEqual(flagged[0]['material'], "Customer's own gold border")
        self.assertIsNone(flagged[0]['inventory_item_id'])

    def test_a_line_can_carry_every_role(self):
        from .models import BomLine
        for role in BomLine.Role.values:
            BomLine.objects.create(bom=self.bom, role=role, inventory_item=self.thread,
                                   quantity=Decimal('1'), unit=Unit.PIECE)
        self.assertEqual(self.bom.lines.count(), len(BomLine.Role.values))

    # --- unit conversion ------------------------------------------------

    def test_line_unit_is_converted_into_the_stocked_unit(self):
        from . import bom as bom_service
        from .models import UnitConversion
        UnitConversion.objects.create(item=self.fabric, from_unit=Unit.ROLL,
                                      to_unit=Unit.METER, factor=Decimal('50'))
        self.line(quantity=Decimal('2'), unit=Unit.ROLL)

        rows = bom_service.requirements(self.bom)
        self.assertEqual(rows[0]['required_quantity'], Decimal('100.000'))
        self.assertEqual(rows[0]['unit'], Unit.METER)

    def test_a_conversion_works_in_reverse_too(self):
        from . import bom as bom_service
        from .models import UnitConversion
        UnitConversion.objects.create(item=self.fabric, from_unit=Unit.ROLL,
                                      to_unit=Unit.METER, factor=Decimal('50'))
        self.line(quantity=Decimal('100'), unit=Unit.METER)
        self.fabric.unit = Unit.ROLL
        self.fabric.save()

        rows = bom_service.requirements(self.bom)
        self.assertEqual(rows[0]['required_quantity'], Decimal('2.000'))

    def test_global_conversions_need_no_setup(self):
        from .bom import convert
        self.assertEqual(convert(Decimal('2'), Unit.KILOGRAM, Unit.GRAM), Decimal('2000.000'))
        self.assertEqual(convert(Decimal('500'), Unit.GRAM, Unit.KILOGRAM), Decimal('0.500'))

    def test_an_unknown_conversion_is_refused_not_guessed(self):
        """Treating 2 rolls as 2 metres would silently reserve the wrong amount."""
        from . import bom as bom_service
        self.line(quantity=Decimal('2'), unit=Unit.ROLL)
        with self.assertRaises(bom_service.BomError) as ctx:
            bom_service.requirements(self.bom)
        self.assertIn('no conversion', str(ctx.exception))

    def test_waste_is_applied_before_conversion(self):
        """So a percentage means the same thing whichever unit the line uses."""
        from . import bom as bom_service
        from .models import UnitConversion
        UnitConversion.objects.create(item=self.fabric, from_unit=Unit.ROLL,
                                      to_unit=Unit.METER, factor=Decimal('50'))
        self.line(quantity=Decimal('2'), unit=Unit.ROLL, waste_percent=Decimal('10'))

        rows = bom_service.requirements(self.bom)
        # 2 rolls + 10% = 2.2 rolls = 110 m. Converting first would give the same
        # number here, but not once the factor is fractional -- this pins the order.
        self.assertEqual(rows[0]['required_quantity'], Decimal('110.000'))

    # --- error handling -------------------------------------------------

    def test_a_broken_formula_names_the_material(self):
        from . import bom as bom_service
        self.line(quantity_formula='0.15 * hips')
        with self.assertRaises(bom_service.BomError) as ctx:
            bom_service.requirements(self.bom, {'bust': 36})
        self.assertIn('Raw Silk', str(ctx.exception))
        self.assertIn('hips', str(ctx.exception))

    def test_a_negative_formula_result_is_refused(self):
        from . import bom as bom_service
        self.line(quantity_formula='bust - 100')
        with self.assertRaises(bom_service.BomError) as ctx:
            bom_service.requirements(self.bom, {'bust': 36})
        self.assertIn('negative', str(ctx.exception))

    def test_unresolved_lines_are_counted(self):
        """A line naming only a catalogue row cannot be reserved yet."""
        from . import bom as bom_service
        from .models import BomLine, CatalogItem
        dabka = CatalogItem.objects.filter(name='Dabka').first()
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.EMBROIDERY,
                               catalog_item=dabka, quantity=Decimal('3'), unit=Unit.PIECE)
        summary = bom_service.summarise(self.bom)
        self.assertEqual(summary['unresolved_line_count'], 1)


class BomApiTests(InventoryTestBase):

    def setUp(self):
        super().setUp()
        from .models import BillOfMaterials, BomLine
        self.fabric = self.make_item(item_code='FAB-200', name='Banarasi Silk', unit=Unit.METER)
        self.bom = BillOfMaterials.objects.create(name='Lehenga')
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.FABRIC,
                               inventory_item=self.fabric, quantity_formula='0.2 * waist + 2',
                               unit=Unit.METER, waste_percent=Decimal('10'))

    def test_requirements_endpoint_computes_from_measurements(self):
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/requirements/',
            {'variables': {'waist': 30}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        row = response.data['requirements'][0]
        # (0.2*30 + 2) = 8, +10% = 8.8
        self.assertEqual(Decimal(str(row['required_quantity'])), Decimal('8.800'))

    def test_missing_measurement_is_a_400_with_a_readable_message(self):
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/requirements/', {'variables': {}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('waist', response.data['error'])

    def test_variables_must_be_an_object(self):
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/requirements/',
            {'variables': 'waist=30'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_hostile_formula_is_rejected_when_written(self):
        response = self.client.post('/api/inventory/bom-lines/', {
            'bom': str(self.bom.id), 'role': 'FABRIC',
            'inventory_item': str(self.fabric.id),
            'quantity_formula': "__import__('os').system('id')",
            'unit': 'METER',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('quantity_formula', response.data)

    def test_a_line_naming_nothing_is_rejected(self):
        response = self.client.post('/api/inventory/bom-lines/', {
            'bom': str(self.bom.id), 'role': 'FABRIC', 'quantity': '1', 'unit': 'METER',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_version_copies_the_lines_and_retires_the_old_one(self):
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/new-version/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['version'], 2)
        self.assertEqual(len(response.data['lines']), 1)

        self.bom.refresh_from_db()
        self.assertFalse(self.bom.is_active, 'the superseded version is retired')


class FormulaHardeningTests(TenantTestCase):
    """Every defect an adversarial review of stage 3 confirmed, pinned.

    These are regression tests for real holes, not hypotheticals: each one
    failed before the fix that accompanies it.
    """

    def test_negative_base_to_a_fractional_power_is_refused(self):
        """(-1) ** 0.5 is a complex number; float() of it is a TypeError 500."""
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError) as ctx:
            evaluate('(0 - 1) ** 0.5')
        self.assertIn('complex', str(ctx.exception))

    def test_round_with_an_infinite_precision_is_refused(self):
        """int(inf) is an OverflowError, and it used to sit outside the try."""
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate('round(1.5, 1e400)')

    def test_nested_powers_cannot_slip_past_the_exponent_cap(self):
        """Each exponent is 8, so bounding the exponent alone lets this through."""
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate('((9 ** 8) ** 8) ** 8')

    def test_an_astronomical_measurement_is_refused(self):
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate('bust * 2', {'bust': 1e300})
        with self.assertRaises(FormulaError):
            evaluate('1e30')

    def test_nan_and_infinity_cannot_arrive_as_measurements(self):
        """Variables come from the request body, where they are strings."""
        from .formula import FormulaError, evaluate
        for hostile in ('nan', 'inf', '-inf', 'Infinity'):
            with self.assertRaises(FormulaError, msg=hostile):
                evaluate('bust * 2', {'bust': hostile})

    def test_a_huge_integer_literal_is_refused(self):
        from .formula import FormulaError, evaluate
        with self.assertRaises(FormulaError):
            evaluate('9' * 400)

    def test_and_or_short_circuit_and_yield_the_operand(self):
        """`waist or 30` should be the measurement, not "true"."""
        from .formula import evaluate
        self.assertEqual(evaluate('waist or 30', {'waist': 32}), Decimal('32'))
        self.assertEqual(evaluate('waist or 30', {'waist': 0}), Decimal('30'))
        self.assertEqual(evaluate('waist and 30', {'waist': 5}), Decimal('30'))
        self.assertEqual(evaluate('waist and 30', {'waist': 0}), Decimal('0'))

    def test_or_short_circuits_before_an_unknown_name(self):
        """Proof it stops evaluating: the right operand would otherwise raise."""
        from .formula import evaluate
        self.assertEqual(evaluate('waist or hips', {'waist': 32}), Decimal('32'))

    # --- the write-time validation hole --------------------------------

    def test_validate_syntax_catches_a_hostile_call_beside_an_unknown_name(self):
        """The bypass: _eval is depth-first, so the left operand raised first.

        `hips * __import__('os')` used to pass write-time validation, because
        the unknown-variable error from the left was the one the serializer had
        been told to ignore -- and the call on the right was never looked at.
        """
        from .formula import FormulaError, validate_syntax
        with self.assertRaises(FormulaError) as ctx:
            validate_syntax("hips * __import__('os')")
        self.assertIn('__import__', str(ctx.exception))

    def test_validate_syntax_allows_unknown_names(self):
        """A measurement does not exist until an order does."""
        from .formula import validate_syntax
        self.assertTrue(validate_syntax('0.15 * bust + hips'))

    def test_validate_syntax_refuses_every_forbidden_construct(self):
        from .formula import FormulaError, validate_syntax
        for hostile in [
            "x.__class__", "[i for i in range(3)]", "(lambda: 1)()",
            "[1,2][0]", "open('/etc/passwd')", "'abc'", "{1:2}",
        ]:
            with self.assertRaises(FormulaError, msg=hostile):
                validate_syntax(hostile)


class BomHardeningTests(InventoryTestBase):
    """Regression tests for the BOM defects the review confirmed."""

    def setUp(self):
        super().setUp()
        from .models import BillOfMaterials, UnitConversion
        self.fabric = self.make_item(item_code='FAB-900', name='Tissue Silk', unit=Unit.METER)
        self.bom = BillOfMaterials.objects.create(name='Hardening')
        UnitConversion.objects.create(item=self.fabric, from_unit=Unit.ROLL,
                                      to_unit=Unit.METER, factor=Decimal('50'))

    def _line(self, **kw):
        from .models import BomLine
        defaults = dict(bom=self.bom, role=BomLine.Role.FABRIC,
                        inventory_item=self.fabric, unit=Unit.METER)
        defaults.update(kw)
        return BomLine.objects.create(**defaults)

    def test_conversion_happens_before_rounding(self):
        """Rounding in the line's unit first multiplies the error by the factor.

        The stored quantity itself is only 3dp, so the sub-precision digits have
        to come from somewhere the field cannot round away: 0.001 rolls plus 5%
        waste is 0.00105 rolls. Converting first gives 0.00105 x 50 = 0.0525 ->
        0.053 m. Rounding first gives 0.001 -> 0.050 m, understating it by the
        full conversion factor.
        """
        from . import bom as bom_service
        self._line(quantity=Decimal('0.001'), unit=Unit.ROLL, waste_percent=Decimal('5'))
        rows = bom_service.requirements(self.bom)
        self.assertEqual(rows[0]['required_quantity'], Decimal('0.053'))

    def test_an_enormous_quantity_is_a_bom_error_not_a_500(self):
        """decimal.InvalidOperation is an ArithmeticError, not a ValueError."""
        from . import bom as bom_service
        self._line(quantity_formula='bust * 1000', unit=Unit.METER)
        with self.assertRaises(bom_service.BomError):
            bom_service.requirements(self.bom, {'bust': 10 ** 8})

    def test_base_quantity_declares_its_own_unit(self):
        from . import bom as bom_service
        self._line(quantity=Decimal('2'), unit=Unit.ROLL)
        row = bom_service.requirements(self.bom)[0]
        self.assertEqual(row['base_unit'], Unit.ROLL)
        self.assertEqual(row['unit'], Unit.METER)
        self.assertEqual(row['required_quantity'], Decimal('100.000'))


class BomVersioningTests(InventoryTestBase):
    """Version uniqueness, which a single unique constraint could not deliver."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import sync_global_templates
        sync_global_templates()
        from apps.catalog.models import GarmentTemplate
        self.template = GarmentTemplate.resolve('lehenga')

    def test_two_version_ones_for_the_same_template_are_refused(self):
        """The ordinary case: template set, design null. Postgres NULL semantics
        made the original single constraint inert exactly here."""
        from django.db.utils import IntegrityError
        from .models import BillOfMaterials
        BillOfMaterials.objects.create(name='Lehenga', template=self.template)
        with self.assertRaises(IntegrityError):
            BillOfMaterials.objects.create(name='Lehenga', template=self.template)

    def test_two_standalone_boms_with_the_same_name_are_refused(self):
        from django.db.utils import IntegrityError
        from .models import BillOfMaterials
        BillOfMaterials.objects.create(name='Standalone')
        with self.assertRaises(IntegrityError):
            BillOfMaterials.objects.create(name='Standalone')

    def test_differently_named_standalone_boms_still_coexist(self):
        from .models import BillOfMaterials
        BillOfMaterials.objects.create(name='Blouse recipe')
        BillOfMaterials.objects.create(name='Saree recipe')
        self.assertEqual(BillOfMaterials.objects.filter(template=None).count(), 2)

    def test_the_api_reports_a_duplicate_as_400_not_500(self):
        from .models import BillOfMaterials
        BillOfMaterials.objects.create(name='Lehenga', template=self.template)
        response = self.client.post('/api/inventory/boms/', {
            'name': 'Lehenga', 'template': str(self.template.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_standalone_boms_do_not_share_a_version_counter(self):
        """Versioning one standalone BOM used to be numbered off all the others."""
        from .models import BillOfMaterials
        other = BillOfMaterials.objects.create(name='Unrelated', version=9)
        mine = BillOfMaterials.objects.create(name='Mine')

        response = self.client.post(
            f'/api/inventory/boms/{mine.id}/new-version/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['version'], 2, 'should follow its own lineage, not v9')

    def test_a_superseded_version_cannot_be_versioned_again(self):
        """Otherwise two active BOMs end up live for the same garment."""
        from .models import BillOfMaterials
        bom = BillOfMaterials.objects.create(name='Twice', template=self.template)
        first = self.client.post(f'/api/inventory/boms/{bom.id}/new-version/', {}, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        again = self.client.post(f'/api/inventory/boms/{bom.id}/new-version/', {}, format='json')
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            BillOfMaterials.objects.filter(template=self.template, is_active=True).count(), 1)


class BomApiHardeningTests(InventoryTestBase):

    def setUp(self):
        super().setUp()
        from .models import BillOfMaterials, BomLine
        self.fabric = self.make_item(item_code='FAB-950', name='Net', unit=Unit.METER)
        self.bom = BillOfMaterials.objects.create(name='Api hardening')
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.FABRIC,
                               inventory_item=self.fabric, quantity=Decimal('1'),
                               unit=Unit.METER)
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.ACCESSORY,
                               inventory_item=self.fabric, quantity=Decimal('5'),
                               unit=Unit.METER, is_optional=True, sequence=2)

    def test_include_optional_false_is_honoured_as_a_string(self):
        """bool('false') is True; a naive truth-test reserved the optional line."""
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/requirements/',
            {'variables': {}, 'include_optional': 'false'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['requirements']), 1)

    def test_include_optional_true_still_works(self):
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/requirements/',
            {'variables': {}, 'include_optional': True}, format='json')
        self.assertEqual(len(response.data['requirements']), 2)

    def test_a_non_object_body_is_a_400_not_a_500(self):
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/requirements/', ['not', 'an', 'object'],
            format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_enormous_measurement_is_a_400_not_a_500(self):
        from .models import BomLine
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.LINING,
                               inventory_item=self.fabric, quantity_formula='bust * 1000',
                               unit=Unit.METER, sequence=3)
        response = self.client.post(
            f'/api/inventory/boms/{self.bom.id}/requirements/',
            {'variables': {'bust': 10 ** 12}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_a_hostile_formula_beside_an_unknown_name_is_rejected(self):
        """The write-time validation bypass, at the API boundary."""
        response = self.client.post('/api/inventory/bom-lines/', {
            'bom': str(self.bom.id), 'role': 'FABRIC',
            'inventory_item': str(self.fabric.id),
            'quantity_formula': "hips * __import__('os').system('id')",
            'unit': 'METER',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('quantity_formula', response.data)

    def test_a_non_stockable_catalog_row_cannot_be_a_material(self):
        from .models import CatalogItem
        gateway = CatalogItem.objects.filter(name='Payment Gateway').first()
        response = self.client.post('/api/inventory/bom-lines/', {
            'bom': str(self.bom.id), 'role': 'OTHER',
            'catalog_item': str(gateway.id), 'quantity': '1', 'unit': 'PIECE',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


class OrderMaterialTestBase(InventoryTestBase):
    """Shared fixture: an order, a BOM, and stock to satisfy it."""

    def setUp(self):
        super().setUp()
        from crm_api.models import Customer, Order
        from .models import BillOfMaterials, BomLine

        self.customer = Customer.objects.create(
            first_name='Aditi', last_name='Rao', mobile_number='9990001111')
        self.order = Order.objects.create(order_id='T2B-TEST-0001', customer=self.customer)

        self.fabric = self.make_item(item_code='FAB-OM1', name='Raw Silk', unit=Unit.METER)
        self.thread = self.make_item(item_code='THR-OM1', name='Resham Thread',
                                     category=Category.STITCHING, unit=Unit.PIECE)
        self.box = self.make_item(item_code='PKG-OM1', name='Gift Box',
                                  category=Category.PACKAGING, unit=Unit.PIECE)
        InventoryService.stock_in(self.fabric, 100, user=self.owner)
        InventoryService.stock_in(self.thread, 50, user=self.owner)
        InventoryService.stock_in(self.box, 20, user=self.owner)

        self.bom = BillOfMaterials.objects.create(name='Blouse recipe')
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.FABRIC,
                               inventory_item=self.fabric, quantity=Decimal('3'),
                               unit=Unit.METER, sequence=1)
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.THREAD,
                               inventory_item=self.thread, quantity=Decimal('2'),
                               unit=Unit.PIECE, sequence=2)
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.PACKAGING,
                               inventory_item=self.box, quantity=Decimal('1'),
                               unit=Unit.PIECE, sequence=3)

    def plan(self, **kw):
        from . import order_materials
        return order_materials.plan_materials(self.order, self.bom, user=self.owner, **kw)


class OrderMaterialLifecycleTests(OrderMaterialTestBase):
    """The ten steps, in order."""

    def test_1_planning_snapshots_the_requirement(self):
        from .models import OrderMaterialPlan
        plan = self.plan()
        self.assertEqual(plan.status, OrderMaterialPlan.Status.DRAFT)
        self.assertEqual(plan.lines.count(), 3)
        self.assertEqual(plan.bom_version, self.bom.version)
        fabric_line = plan.lines.get(material_name='Raw Silk')
        self.assertEqual(fabric_line.required_quantity, Decimal('3.000'))

    def test_1_a_second_live_plan_is_refused(self):
        from . import order_materials
        self.plan()
        with self.assertRaises(order_materials.MaterialPlanError) as ctx:
            self.plan()
        self.assertIn('already has a live material plan', str(ctx.exception))

    def test_2_availability_reports_a_shortfall(self):
        from . import order_materials
        InventoryService.issue(self.fabric, 98, user=self.owner)   # 2 m left
        plan = self.plan()
        shortfalls = order_materials.check_availability(plan)
        self.assertEqual(len(shortfalls), 1)
        self.assertEqual(shortfalls[0]['material'], 'Raw Silk')
        self.assertEqual(shortfalls[0]['short_by'], Decimal('1.000'))

    def test_3_reserving_holds_stock_without_deducting_it(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('100.000'),
                         'reserving is not a deduction')
        self.assertEqual(self.fabric.reserved_stock, Decimal('3.000'))
        self.assertEqual(self.fabric.available_stock, Decimal('97.000'))

    def test_3_reserving_is_refused_when_stock_is_short(self):
        from . import order_materials
        InventoryService.issue(self.fabric, 99, user=self.owner)
        plan = self.plan()
        with self.assertRaises(order_materials.MaterialPlanError) as ctx:
            order_materials.reserve(plan, user=self.owner)
        self.assertIn('Not enough stock', str(ctx.exception))
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'),
                         'a refused reservation reserves nothing at all')

    def test_4_reserving_twice_does_not_double_allocate(self):
        """The rule the specification calls out by name."""
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.reserve(plan, user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('3.000'),
                         'the second call should reserve nothing')

    def test_5_stock_is_deducted_only_on_confirmed_consumption(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        line = plan.lines.get(material_name='Raw Silk')

        order_materials.confirm_consumption(line, Decimal('2.5'), user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('97.500'))
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.500'))

    def test_6_and_7_actual_use_and_waste_are_recorded_separately(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        line = plan.lines.get(material_name='Raw Silk')

        order_materials.confirm_consumption(
            line, Decimal('2.4'), wasted=Decimal('0.3'), user=self.owner)

        line.refresh_from_db()
        self.assertEqual(line.consumed_quantity, Decimal('2.400'))
        self.assertEqual(line.wasted_quantity, Decimal('0.300'))
        self.assertEqual(
            StockMovement.objects.filter(
                item=self.fabric, movement_type=StockMovement.Type.WASTE).count(), 1)

    def test_8_unused_reservations_go_back(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        line = plan.lines.get(material_name='Raw Silk')
        order_materials.confirm_consumption(line, Decimal('2'), user=self.owner)

        released = order_materials.release_unused(plan, user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'))
        self.assertEqual(self.fabric.available_stock, Decimal('98.000'))
        self.assertTrue(any(r['material'] == 'Raw Silk' for r in released))

    def test_9_packaging_is_deducted_at_dispatch_not_before(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)

        self.box.refresh_from_db()
        self.assertEqual(self.box.current_stock, Decimal('20.000'),
                         'reserved, not yet used')

        order_materials.deduct_packaging(plan, user=self.owner)

        self.box.refresh_from_db()
        self.assertEqual(self.box.current_stock, Decimal('19.000'))

    def test_9_packaging_is_not_deducted_twice(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.deduct_packaging(plan, user=self.owner)
        with self.assertRaises(order_materials.MaterialPlanError) as ctx:
            order_materials.deduct_packaging(plan, user=self.owner)
        self.assertIn('already deducted', str(ctx.exception))

        self.box.refresh_from_db()
        self.assertEqual(self.box.current_stock, Decimal('19.000'))

    def test_10_reconcile_reports_outstanding_reservations(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)

        report = order_materials.reconcile(plan)
        self.assertFalse(report['is_reconciled'])
        self.assertTrue(report['outstanding_reservations'])

        order_materials.release_unused(plan, user=self.owner)
        self.assertTrue(order_materials.reconcile(plan)['is_reconciled'])

    def test_10_closing_releases_what_is_left(self):
        from . import order_materials
        from .models import OrderMaterialPlan
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)

        order_materials.close(plan, user=self.owner)

        plan.refresh_from_db()
        self.assertEqual(plan.status, OrderMaterialPlan.Status.COMPLETED)
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'))

    def test_closing_a_plan_frees_the_order_for_a_new_one(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.close(plan, user=self.owner)
        self.assertIsNotNone(self.plan(), 'the one-live-plan rule is about live plans')

    def test_cancelling_gives_every_reservation_back(self):
        from . import order_materials
        from .models import OrderMaterialPlan
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.cancel(plan, user=self.owner)

        plan.refresh_from_db()
        self.assertEqual(plan.status, OrderMaterialPlan.Status.CANCELLED)
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'))

    def test_the_whole_ledger_balances_end_to_end(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        fabric_line = plan.lines.get(material_name='Raw Silk')
        order_materials.confirm_consumption(
            fabric_line, Decimal('2.5'), wasted=Decimal('0.2'), user=self.owner)
        order_materials.deduct_packaging(plan, user=self.owner)
        order_materials.close(plan, user=self.owner)

        self.fabric.refresh_from_db()
        # 100 - 2.5 consumed - 0.2 wasted = 97.3, nothing left reserved
        self.assertEqual(self.fabric.current_stock, Decimal('97.300'))
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'))
        self.box.refresh_from_db()
        self.assertEqual(self.box.current_stock, Decimal('19.000'))


class CustomerMaterialTests(OrderMaterialTestBase):
    """The customer's own material, which is never boutique stock."""

    def receive(self, quantity='5'):
        from . import order_materials
        return order_materials.receive_customer_material(
            self.order, name="Customer's Kanchipuram silk", quantity=quantity,
            unit=Unit.METER, user=self.owner)

    def test_receiving_creates_no_inventory_item(self):
        """The rule the specification states most emphatically."""
        from .models import InventoryItem
        before = InventoryItem.objects.count()
        material = self.receive()
        self.assertEqual(InventoryItem.objects.count(), before)
        self.assertEqual(material.remaining_quantity, Decimal('5.000'))

    def test_the_five_balances_are_tracked(self):
        from . import order_materials
        from .models import CustomerMaterialMovement
        material = self.receive('10')
        order_materials.record_customer_material(
            material, CustomerMaterialMovement.Type.USED, '6', user=self.owner)
        order_materials.record_customer_material(
            material, CustomerMaterialMovement.Type.DAMAGED, '1', user=self.owner)
        order_materials.record_customer_material(
            material, CustomerMaterialMovement.Type.RETURNED, '2', user=self.owner)

        material.refresh_from_db()
        self.assertEqual(material.received_quantity, Decimal('10.000'))
        self.assertEqual(material.used_quantity, Decimal('6.000'))
        self.assertEqual(material.damaged_quantity, Decimal('1.000'))
        self.assertEqual(material.returned_quantity, Decimal('2.000'))
        self.assertEqual(material.remaining_quantity, Decimal('1.000'))

    def test_cannot_account_for_more_than_was_received(self):
        from . import order_materials
        from .models import CustomerMaterialMovement
        material = self.receive('4')
        with self.assertRaises(order_materials.MaterialPlanError) as ctx:
            order_materials.record_customer_material(
                material, CustomerMaterialMovement.Type.USED, '5', user=self.owner)
        self.assertIn('Only 4', str(ctx.exception))

    def test_every_change_leaves_a_movement(self):
        from . import order_materials
        from .models import CustomerMaterialMovement
        material = self.receive('10')
        order_materials.record_customer_material(
            material, CustomerMaterialMovement.Type.USED, '3', user=self.owner)

        movements = material.movements.order_by('created_at')
        self.assertEqual(
            [m.movement_type for m in movements],
            [CustomerMaterialMovement.Type.RECEIVED, CustomerMaterialMovement.Type.USED])
        self.assertEqual(movements[1].previous_remaining, Decimal('10.000'))
        self.assertEqual(movements[1].new_remaining, Decimal('7.000'))

    def test_a_customer_supplied_bom_line_is_never_reserved(self):
        from . import order_materials
        from .models import BomLine
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.FABRIC,
                               description="Customer's own border",
                               is_customer_supplied=True, quantity=Decimal('2'),
                               unit=Unit.METER, sequence=4)
        plan = self.plan()
        result = order_materials.reserve(plan, user=self.owner)

        self.assertNotIn("Customer's own border",
                         [r['material'] for r in result['reserved']])
        line = plan.lines.get(material_name="Customer's own border")
        self.assertEqual(line.reserved_quantity, Decimal('0.000'))

    def test_a_customer_supplied_line_cannot_consume_boutique_stock(self):
        from . import order_materials
        from .models import BomLine
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.FABRIC,
                               description="Customer's own border",
                               is_customer_supplied=True, quantity=Decimal('2'),
                               unit=Unit.METER, sequence=4)
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        line = plan.lines.get(material_name="Customer's own border")

        with self.assertRaises(order_materials.MaterialPlanError) as ctx:
            order_materials.confirm_consumption(line, Decimal('1'), user=self.owner)
        self.assertIn('customer-supplied', str(ctx.exception))

    def test_reconcile_flags_customer_material_still_held(self):
        from . import order_materials
        self.receive('5')
        plan = self.plan()
        report = order_materials.reconcile(plan)
        self.assertEqual(len(report['customer_material_to_return']), 1)
        self.assertEqual(report['customer_material_to_return'][0]['remaining'],
                         Decimal('5.000'))


class OrderMaterialApiTests(OrderMaterialTestBase):

    def test_the_whole_flow_over_the_api(self):
        from .models import OrderMaterialPlan

        created = self.client.post('/api/inventory/material-plans/plan/', {
            'order': str(self.order.id), 'bom': str(self.bom.id)}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        plan_id = created.data['id']

        availability = self.client.get(f'/api/inventory/material-plans/{plan_id}/availability/')
        self.assertTrue(availability.data['is_available'])

        reserved = self.client.post(f'/api/inventory/material-plans/{plan_id}/reserve/',
                                    {}, format='json')
        self.assertEqual(reserved.status_code, status.HTTP_200_OK, reserved.data)

        plan = OrderMaterialPlan.objects.get(pk=plan_id)
        line = plan.lines.get(material_name='Raw Silk')
        consumed = self.client.post(f'/api/inventory/material-plans/{plan_id}/consume/',
                                    {'line': str(line.id), 'used': '2', 'wasted': '0.5'},
                                    format='json')
        self.assertEqual(consumed.status_code, status.HTTP_200_OK, consumed.data)

        self.client.post(f'/api/inventory/material-plans/{plan_id}/deduct-packaging/',
                         {}, format='json')
        closed = self.client.post(f'/api/inventory/material-plans/{plan_id}/close/',
                                  {}, format='json')
        self.assertEqual(closed.data['status'], OrderMaterialPlan.Status.COMPLETED)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('97.500'))
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'))

    def test_planning_an_unknown_order_is_a_400(self):
        response = self.client.post('/api/inventory/material-plans/plan/', {
            'order': '00000000-0000-0000-0000-000000000000',
            'bom': str(self.bom.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_consuming_a_line_from_another_plan_is_refused(self):
        from crm_api.models import Order
        from . import order_materials
        other_order = Order.objects.create(order_id='T2B-TEST-0002', customer=self.customer)
        mine = self.plan()
        theirs = order_materials.plan_materials(other_order, self.bom, user=self.owner)
        order_materials.reserve(mine, user=self.owner)

        foreign_line = theirs.lines.first()
        response = self.client.post(f'/api/inventory/material-plans/{mine.id}/consume/',
                                    {'line': str(foreign_line.id), 'used': '1'},
                                    format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_material_api_records_use_and_return(self):
        created = self.client.post('/api/inventory/customer-materials/', {
            'order': str(self.order.id), 'name': 'Customer silk',
            'received_quantity': '8', 'unit': 'METER', 'kind': 'FABRIC'}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        material_id = created.data['id']

        used = self.client.post(f'/api/inventory/customer-materials/{material_id}/use/',
                                {'quantity': '5'}, format='json')
        self.assertEqual(Decimal(str(used.data['remaining_quantity'])), Decimal('3.000'))

        over = self.client.post(f'/api/inventory/customer-materials/{material_id}/return/',
                                {'quantity': '9'}, format='json')
        self.assertEqual(over.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_material_balances_cannot_be_patched_directly(self):
        created = self.client.post('/api/inventory/customer-materials/', {
            'order': str(self.order.id), 'name': 'Customer silk',
            'received_quantity': '8', 'unit': 'METER'}, format='json')
        material_id = created.data['id']

        self.client.patch(f'/api/inventory/customer-materials/{material_id}/',
                          {'used_quantity': '99'}, format='json')

        from .models import CustomerMaterial
        material = CustomerMaterial.objects.get(pk=material_id)
        self.assertEqual(material.used_quantity, Decimal('0.000'),
                         'balances move only through recorded movements')


class MaterialPlanHardeningTests(OrderMaterialTestBase):
    """Regression tests for the defects an adversarial review confirmed.

    The important ones all share a root: a consumption used to release
    reservation clamped against the item's GLOBAL reserved figure, so one
    order's over-consumption silently cancelled another order's reservation and
    left that order unable to release what it still believed it held.
    """

    def second_order(self):
        from crm_api.models import Order
        return Order.objects.create(order_id='T2B-TEST-0009', customer=self.customer)

    def test_over_consuming_does_not_eat_another_orders_reservation(self):
        from . import order_materials
        other = self.second_order()
        mine = self.plan()
        theirs = order_materials.plan_materials(other, self.bom, user=self.owner)
        order_materials.reserve(mine, user=self.owner)
        order_materials.reserve(theirs, user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('6.000'))

        # Production on my order used 5 m though only 3 were reserved.
        line = mine.lines.get(material_name='Raw Silk')
        order_materials.confirm_consumption(line, Decimal('5'), user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('3.000'),
                         "the other order's reservation must survive")
        self.assertEqual(self.fabric.current_stock, Decimal('95.000'))

    def test_the_other_order_can_still_be_closed_afterwards(self):
        """The wedge: releasing used to fail, so the order could never close."""
        from . import order_materials
        other = self.second_order()
        mine = self.plan()
        theirs = order_materials.plan_materials(other, self.bom, user=self.owner)
        order_materials.reserve(mine, user=self.owner)
        order_materials.reserve(theirs, user=self.owner)

        order_materials.confirm_consumption(
            mine.lines.get(material_name='Raw Silk'), Decimal('5'), user=self.owner)

        order_materials.close(theirs, user=self.owner)          # must not raise
        theirs.refresh_from_db()
        from .models import OrderMaterialPlan
        self.assertEqual(theirs.status, OrderMaterialPlan.Status.COMPLETED)

    def test_the_other_order_can_still_be_cancelled_afterwards(self):
        from . import order_materials
        other = self.second_order()
        mine = self.plan()
        theirs = order_materials.plan_materials(other, self.bom, user=self.owner)
        order_materials.reserve(mine, user=self.owner)
        order_materials.reserve(theirs, user=self.owner)
        order_materials.confirm_consumption(
            mine.lines.get(material_name='Raw Silk'), Decimal('5'), user=self.owner)

        order_materials.cancel(theirs, user=self.owner)         # must not raise
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'))

    def test_release_then_dispatch_does_not_steal_a_reservation(self):
        """Steps 8 then 9, the documented order, with a shared packaging item."""
        from . import order_materials
        other = self.second_order()
        mine = self.plan()
        theirs = order_materials.plan_materials(other, self.bom, user=self.owner)
        order_materials.reserve(mine, user=self.owner)
        order_materials.reserve(theirs, user=self.owner)

        order_materials.release_unused(mine, user=self.owner)   # step 8
        order_materials.deduct_packaging(mine, user=self.owner)  # step 9

        self.box.refresh_from_db()
        self.assertEqual(self.box.reserved_stock, Decimal('1.000'),
                         "order B's box reservation must survive")
        order_materials.close(theirs, user=self.owner)          # must not raise

    def test_waste_beyond_the_reservation_also_stays_bounded(self):
        from . import order_materials
        other = self.second_order()
        mine = self.plan()
        theirs = order_materials.plan_materials(other, self.bom, user=self.owner)
        order_materials.reserve(mine, user=self.owner)
        order_materials.reserve(theirs, user=self.owner)

        order_materials.confirm_consumption(
            mine.lines.get(material_name='Raw Silk'), 0, wasted=Decimal('5'),
            user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('3.000'))

    # --- status guards ---------------------------------------------------

    def test_packaging_cannot_be_deducted_from_a_cancelled_plan(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.cancel(plan, user=self.owner)

        with self.assertRaises(order_materials.MaterialPlanError):
            order_materials.deduct_packaging(plan, user=self.owner)
        self.box.refresh_from_db()
        self.assertEqual(self.box.current_stock, Decimal('20.000'))

    def test_packaging_cannot_be_deducted_from_a_completed_plan(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.close(plan, user=self.owner)
        with self.assertRaises(order_materials.MaterialPlanError):
            order_materials.deduct_packaging(plan, user=self.owner)

    def test_packaging_cannot_be_deducted_from_a_draft_plan(self):
        from . import order_materials
        plan = self.plan()
        with self.assertRaises(order_materials.MaterialPlanError):
            order_materials.deduct_packaging(plan, user=self.owner)

    def test_a_cancelled_plan_cannot_release_again(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.cancel(plan, user=self.owner)
        with self.assertRaises(order_materials.MaterialPlanError):
            order_materials.release_unused(plan, user=self.owner)

    # --- counters --------------------------------------------------------

    def test_re_reserving_after_a_release_actually_reserves_again(self):
        """reserved_quantity is a lifetime total, not a current holding."""
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.release_unused(plan, user=self.owner)

        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('0.000'))

        order_materials.reserve(plan, user=self.owner)
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.reserved_stock, Decimal('3.000'),
                         'a re-reserve after releasing must not be a silent no-op')

    def test_two_lines_naming_the_same_item_are_summed(self):
        """A lehenga's skirt and blouse are both silk; 60 + 60 does not fit 100."""
        from . import order_materials
        from .models import BillOfMaterials, BomLine
        bom = BillOfMaterials.objects.create(name='Two silk panels')
        for sequence in (1, 2):
            BomLine.objects.create(bom=bom, role=BomLine.Role.FABRIC,
                                   inventory_item=self.fabric, quantity=Decimal('60'),
                                   unit=Unit.METER, sequence=sequence)
        from crm_api.models import Order
        order = Order.objects.create(order_id='T2B-TEST-0010', customer=self.customer)
        plan = order_materials.plan_materials(order, bom, user=self.owner)

        shortfalls = order_materials.check_availability(plan)
        self.assertTrue(shortfalls, '120 m of demand against 100 m of stock is short')
        self.assertEqual(shortfalls[0]['short_by'], Decimal('20.000'))

        with self.assertRaises(order_materials.MaterialPlanError):
            order_materials.reserve(plan, user=self.owner)

    # --- quantities ------------------------------------------------------

    def test_a_nan_quantity_is_refused_not_a_500(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        line = plan.lines.get(material_name='Raw Silk')
        for bad in ('nan', 'inf', '-inf'):
            with self.assertRaises(order_materials.MaterialPlanError, msg=bad):
                order_materials.confirm_consumption(line, bad, user=self.owner)

    def test_customer_quantities_are_rounded_to_the_stored_precision(self):
        from . import order_materials
        material = order_materials.receive_customer_material(
            self.order, name='Customer silk', quantity='5.5555', unit=Unit.METER,
            user=self.owner)
        self.assertEqual(material.received_quantity, Decimal('5.556'))
        movement = material.movements.get()
        self.assertEqual(movement.new_remaining, material.remaining_quantity,
                         'the ledger must agree with the balance it explains')


class CustomerMaterialApiHardeningTests(OrderMaterialTestBase):

    def make(self, **overrides):
        payload = {'order': str(self.order.id), 'name': 'Customer silk',
                   'received_quantity': '8', 'unit': 'METER'}
        payload.update(overrides)
        return self.client.post('/api/inventory/customer-materials/', payload, format='json')

    def test_material_cannot_be_repointed_at_another_order(self):
        from crm_api.models import Order
        from .models import CustomerMaterial
        other = Order.objects.create(order_id='T2B-TEST-0011', customer=self.customer)
        created = self.make()
        response = self.client.patch(
            f"/api/inventory/customer-materials/{created.data['id']}/",
            {'order': other.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            CustomerMaterial.objects.get(pk=created.data['id']).order_id, self.order.id)

    def test_unit_cannot_be_changed_after_receipt(self):
        created = self.make()
        response = self.client.patch(
            f"/api/inventory/customer-materials/{created.data['id']}/",
            {'unit': 'PIECE'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_descriptive_fields_can_still_be_edited(self):
        created = self.make()
        response = self.client.patch(
            f"/api/inventory/customer-materials/{created.data['id']}/",
            {'notes': 'Left with the front desk'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_deleting_a_material_is_not_allowed(self):
        """It would cascade away the movement ledger that explains the balances."""
        created = self.make()
        response = self.client.delete(
            f"/api/inventory/customer-materials/{created.data['id']}/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_the_payload_is_validated(self):
        self.assertEqual(self.make(name='').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.make(name='   ').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.make(unit='FURLONG').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.make(kind='NONSENSE').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.make(received_quantity='abc').status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_malformed_line_id_is_a_400_not_a_500(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        response = self.client.post(f'/api/inventory/material-plans/{plan.id}/consume/',
                                    {'line': 'not-a-uuid', 'used': '1'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_malformed_location_id_is_a_400_not_a_500(self):
        from . import order_materials
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        line = plan.lines.get(material_name='Raw Silk')
        response = self.client.post(
            f'/api/inventory/material-plans/{plan.id}/consume/',
            {'line': str(line.id), 'used': '1', 'from_location': 'main-store'},
            format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class InventoryReportTests(OrderMaterialTestBase):
    """The sixteen figures, against a known set of movements."""

    def test_stock_position_covers_six_of_the_reports(self):
        from . import reports
        position = reports.stock_position()
        # 100 fabric + 50 thread + 20 box
        self.assertEqual(position['current_stock'], Decimal('170.000'))
        self.assertEqual(position['reserved_stock'], Decimal('0.000'))
        self.assertEqual(position['available_stock'], Decimal('170.000'))
        self.assertEqual(position['item_count'], 3)

    def test_reserved_and_available_move_apart_once_reserved(self):
        from . import order_materials, reports
        order_materials.reserve(self.plan(), user=self.owner)
        position = reports.stock_position()
        self.assertEqual(position['current_stock'], Decimal('170.000'))
        self.assertEqual(position['reserved_stock'], Decimal('6.000'))   # 3 + 2 + 1
        self.assertEqual(position['available_stock'], Decimal('164.000'))

    def test_inventory_value_is_stock_times_purchase_price(self):
        from . import reports
        # every fixture item is priced at 1200
        self.assertEqual(reports.stock_position()['inventory_value'],
                         Decimal('204000.00'))

    def test_low_stock_measures_availability_not_shelf_quantity(self):
        """Material promised to an order will not be there for the next one."""
        from . import order_materials, reports
        self.fabric.refresh_from_db()
        self.fabric.reorder_level = Decimal('98')
        self.fabric.save(update_fields=['reorder_level'])
        self.assertEqual(reports.low_stock(), [], 'a full shelf is not low')

        order_materials.reserve(self.plan(), user=self.owner)
        rows = reports.low_stock()
        self.assertEqual([r['name'] for r in rows], ['Raw Silk'])
        self.assertEqual(rows[0]['available_stock'], Decimal('97.000'))

    def test_consumption_totals_by_item(self):
        from . import order_materials, reports
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.confirm_consumption(
            plan.lines.get(material_name='Raw Silk'), Decimal('2.5'), user=self.owner)

        report = reports.consumption()
        self.assertEqual(report['total_quantity'], Decimal('2.500'))
        self.assertEqual(report['rows'][0]['name'], 'Raw Silk')
        self.assertEqual(report['rows'][0]['value'], Decimal('3000.00'))

    def test_consumption_scopes_are_separate_reports(self):
        from . import order_materials, reports
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.confirm_consumption(
            plan.lines.get(material_name='Raw Silk'), Decimal('3'), user=self.owner)
        order_materials.deduct_packaging(plan, user=self.owner)

        self.assertEqual(reports.consumption('fabric')['total_quantity'], Decimal('3.000'))
        self.assertEqual(reports.consumption('packaging')['total_quantity'], Decimal('1.000'))
        self.assertEqual(reports.consumption('embroidery')['total_quantity'], Decimal('0'))

    def test_an_unknown_consumption_scope_is_refused(self):
        from . import reports
        with self.assertRaises(ValueError):
            reports.consumption('lehengas')

    def test_waste_and_damage_rates_use_different_denominators(self):
        from . import order_materials, reports
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.confirm_consumption(
            plan.lines.get(material_name='Raw Silk'), Decimal('2'),
            wasted=Decimal('0.5'), user=self.owner)
        InventoryService.damage(self.thread, Decimal('5'), user=self.owner)

        rates = reports.loss_rates()
        self.assertEqual(rates['consumed'], Decimal('2.000'))
        self.assertEqual(rates['wasted'], Decimal('0.500'))
        self.assertEqual(rates['damaged'], Decimal('5.000'))
        # waste over what went to production: 0.5 / (2 + 0.5) = 20%
        self.assertEqual(rates['waste_percent'], Decimal('20.00'))
        # damage over what was taken in: 5 / 170 = 2.94%
        self.assertEqual(rates['damage_percent'], Decimal('2.94'))

    def test_a_rate_with_no_data_is_none_not_zero(self):
        """0% waste and "no production yet" must not look the same."""
        from . import reports
        rates = reports.loss_rates()
        self.assertIsNone(rates['waste_percent'])
        self.assertIsNotNone(rates['damage_percent'], 'stock was received')

    def test_cost_per_order_counts_waste_as_cost(self):
        from . import order_materials, reports
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.confirm_consumption(
            plan.lines.get(material_name='Raw Silk'), Decimal('2'),
            wasted=Decimal('0.5'), user=self.owner)

        rows = reports.cost_per_order()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['material_cost'], Decimal('2400.00'))
        self.assertEqual(rows[0]['waste_cost'], Decimal('600.00'))
        self.assertEqual(rows[0]['total_cost'], Decimal('3000.00'))

    def test_customer_material_costs_the_boutique_nothing(self):
        from . import order_materials, reports
        from .models import BomLine
        BomLine.objects.create(bom=self.bom, role=BomLine.Role.FABRIC,
                               description="Customer's own silk", is_customer_supplied=True,
                               quantity=Decimal('4'), unit=Unit.METER, sequence=9)
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.receive_customer_material(
            self.order, name="Customer's own silk", quantity='4', unit=Unit.METER,
            user=self.owner)

        usage = reports.order_material_usage(self.order)
        self.assertEqual(len(usage['customer_materials']), 1)
        self.assertNotIn("Customer's own silk",
                         [row['material'] for row in usage['boutique_materials']])
        self.assertEqual(usage['material_cost'], Decimal('0.00'),
                         'nothing consumed yet, and the customer silk is not a cost')

    def test_order_usage_keeps_the_two_ledgers_apart(self):
        from . import order_materials, reports
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.confirm_consumption(
            plan.lines.get(material_name='Raw Silk'), Decimal('3'), user=self.owner)
        order_materials.receive_customer_material(
            self.order, name='Customer border', quantity='2', unit=Unit.METER,
            user=self.owner)

        usage = reports.order_material_usage(self.order)
        self.assertEqual(usage['order'], self.order.order_id)
        self.assertEqual(usage['material_cost'], Decimal('3600.00'))
        self.assertEqual(usage['customer_materials'][0]['remaining'], Decimal('2.000'))

    def test_supplier_performance_judges_only_what_can_be_judged(self):
        """An order still open is not late, and one with no promised date cannot
        be judged either way."""
        import datetime
        from . import reports
        from .models import PurchaseOrder

        PurchaseOrder.objects.create(
            po_number='PO-ON-TIME', supplier=self.supplier,
            expected_date=datetime.date(2026, 1, 10),
            received_date=datetime.date(2026, 1, 9))
        PurchaseOrder.objects.create(
            po_number='PO-LATE', supplier=self.supplier,
            expected_date=datetime.date(2026, 1, 10),
            received_date=datetime.date(2026, 1, 15))
        PurchaseOrder.objects.create(po_number='PO-OPEN', supplier=self.supplier,
                                     expected_date=datetime.date(2026, 2, 1))
        PurchaseOrder.objects.create(po_number='PO-NO-DATE', supplier=self.supplier,
                                     received_date=datetime.date(2026, 1, 20))

        rows = reports.supplier_performance()
        row = next(r for r in rows if r['supplier'] == 'Rajesh Textiles')
        self.assertEqual(row['order_count'], 4)
        self.assertEqual(row['judged_count'], 2, 'only the two with both dates')
        self.assertEqual(row['on_time_count'], 1)
        self.assertEqual(row['on_time_percent'], Decimal('50.00'))

    def test_movement_history_can_be_filtered_by_order(self):
        from . import order_materials, reports
        plan = self.plan()
        order_materials.reserve(plan, user=self.owner)
        order_materials.confirm_consumption(
            plan.lines.get(material_name='Raw Silk'), Decimal('1'), user=self.owner)

        rows = reports.movement_history(order=self.order)
        self.assertTrue(rows)
        self.assertTrue(all(r['order'] == self.order.order_id for r in rows))
        self.assertIn(StockMovement.Type.CONSUMPTION, [r['movement_type'] for r in rows])

    def test_movement_summary_totals_each_type(self):
        from . import reports
        summary = {row['movement_type']: row for row in reports.movement_summary()}
        self.assertEqual(summary['STOCK_IN']['count'], 3)
        self.assertEqual(summary['STOCK_IN']['quantity'], Decimal('170.000'))


class InventoryReportApiTests(OrderMaterialTestBase):

    def test_every_report_endpoint_answers(self):
        endpoints = [
            'stock-position', 'low-stock', 'consumption', 'loss-rates',
            'cost-per-order', 'suppliers', 'movements', 'movement-summary',
            'dashboard',
        ]
        for endpoint in endpoints:
            response = self.client.get(f'/api/inventory/reports/{endpoint}/')
            self.assertEqual(response.status_code, status.HTTP_200_OK,
                             f'{endpoint}: {response.data}')

    def test_order_usage_needs_an_order(self):
        response = self.client.get('/api/inventory/reports/order-usage/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        ok = self.client.get(f'/api/inventory/reports/order-usage/?order={self.order.id}')
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_a_bad_date_is_refused_not_ignored(self):
        """Silently reporting over all time would be the worst outcome."""
        response = self.client.get('/api/inventory/reports/loss-rates/?since=last-tuesday')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_valid_date_window_is_honoured(self):
        response = self.client.get(
            '/api/inventory/reports/movement-summary/?since=2026-01-01&until=2030-01-01')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_a_bad_limit_is_refused(self):
        for bad in ('abc', '0', '-5'):
            response = self.client.get(f'/api/inventory/reports/low-stock/?limit={bad}')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)

    def test_an_unknown_scope_is_a_400(self):
        response = self.client.get('/api/inventory/reports/consumption/?scope=lehengas')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unknown_movement_type_is_a_400(self):
        response = self.client.get('/api/inventory/reports/movements/?movement_type=TELEPORT')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_malformed_item_filter_is_a_400_not_a_500(self):
        response = self.client.get('/api/inventory/reports/movements/?item=not-a-uuid')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StaleInstanceGuardTests(InventoryTestBase):
    """A stale instance must not be able to rewind stock.

    The DirectStockWriteError guard compares an instance against its own
    snapshot, which cannot detect this case: an instance loaded before a
    movement still holds the old balance, agrees with its own snapshot, and a
    plain save() writes that figure back over the real one. Nothing looks
    changed and the stock is silently rewound.
    """

    def test_saving_a_stale_instance_does_not_rewind_stock(self):
        item = self.make_item()
        InventoryService.stock_in(item, 100, user=self.owner)

        # `item` is the instance from before the movement: it still believes
        # current_stock is 0, and so does its snapshot.
        self.assertEqual(item.current_stock, Decimal('0'))
        item.rack_location = 'A-4'
        item.save()

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('100.000'),
                         'an unrelated edit must not roll the balance back')

    def test_the_unrelated_edit_is_still_written(self):
        item = self.make_item()
        InventoryService.stock_in(item, 100, user=self.owner)
        item.rack_location = 'B-7'
        item.reorder_level = Decimal('25')
        item.save()

        item.refresh_from_db()
        self.assertEqual(item.rack_location, 'B-7')
        self.assertEqual(item.reorder_level, Decimal('25.000'))
        self.assertEqual(item.current_stock, Decimal('100.000'))

    def test_a_deliberate_direct_edit_is_still_refused(self):
        """The original guard must keep working."""
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        item.refresh_from_db()
        item.current_stock = Decimal('999')
        with self.assertRaises(DirectStockWriteError):
            item.save()

    def test_refreshing_then_saving_is_allowed(self):
        """refresh_from_db must re-snapshot, or the guard reads it as an edit."""
        item = self.make_item()
        InventoryService.stock_in(item, 40, user=self.owner)
        item.refresh_from_db()
        item.rack_location = 'C-1'
        item.save()          # must not raise

        item.refresh_from_db()
        self.assertEqual(item.rack_location, 'C-1')
        self.assertEqual(item.current_stock, Decimal('40.000'))


class ReportDateWindowTests(OrderMaterialTestBase):
    """A bare date has to become a moment, and the two ends differ."""

    def test_until_today_includes_today(self):
        """?until=<today> meaning midnight this morning excludes today's work."""
        import datetime
        from django.utils import timezone

        today = timezone.localdate().isoformat()
        response = self.client.get(
            f'/api/inventory/reports/movement-summary/?until={today}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_type = {row['movement_type']: row for row in response.data}
        self.assertIn('STOCK_IN', by_type,
                      "today's movements must fall inside a window ending today")
        self.assertEqual(by_type['STOCK_IN']['quantity'], Decimal('170.000'))

    def test_since_today_also_includes_today(self):
        from django.utils import timezone
        today = timezone.localdate().isoformat()
        response = self.client.get(
            f'/api/inventory/reports/movement-summary/?since={today}')
        by_type = {row['movement_type']: row for row in response.data}
        self.assertIn('STOCK_IN', by_type)

    def test_a_window_that_ended_yesterday_excludes_today(self):
        import datetime
        from django.utils import timezone
        yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        response = self.client.get(
            f'/api/inventory/reports/movement-summary/?until={yesterday}')
        self.assertEqual(response.data, [])

    def test_a_full_timestamp_is_still_accepted(self):
        response = self.client.get(
            '/api/inventory/reports/movement-summary/?since=2026-01-01T00:00:00Z')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class WriteOffWhileReservedTests(InventoryTestBase):
    """Physical loss has to be recordable even when the material is spoken for."""

    def test_damage_can_be_recorded_against_reserved_stock(self):
        """record_movement refused any movement leaving reserved > stock, with a
        message hardcoded to 'Cannot reserve'. It fired for DAMAGE, SCRAP,
        supplier returns and stock counts -- operations that carry no
        reservation at all -- so a real loss could not be written off, and the
        owner was told about a reservation they never attempted.
        """
        item = self.make_item()
        InventoryService.stock_in(item, 10, user=self.owner)
        InventoryService.reserve(item, 10, user=self.owner)

        InventoryService.damage(item, 4, user=self.owner)

        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('6'))
        # The reservation cannot outlive the stock that backed it.
        self.assertEqual(item.reserved_stock, Decimal('6'))


class GatheringChecklistTests(TenantTestCase):
    """The Master's material checklist: created on first look, ticked with a
    name on record, photographed for the road ahead."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@checklist.test"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        from django.contrib.auth.models import User
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient
        from crm_api.models import Customer, Measurement, Tailor

        self.owner = User.objects.create_user(
            username="owner@checklist.test", email="owner@checklist.test",
            password="pw12345678", first_name="Owner")
        self.master_user = User.objects.create_user(
            username="master@checklist.test", email="master@checklist.test",
            password="pw12345678", first_name="Master")
        Tailor.objects.create(name="M", specialty="x", role="Master",
                              status="Available", user=self.master_user)
        self.tailor_user = User.objects.create_user(
            username="t@checklist.test", email="t@checklist.test",
            password="pw12345678", first_name="T")
        Tailor.objects.create(name="T", specialty="x", role="Tailor",
                              status="Available", user=self.tailor_user)

        self.customer = Customer.objects.create(
            first_name="C", last_name="K", mobile_number="9811111111",
            garment_type="Blouse")
        Measurement.objects.create(customer=self.customer, bust=36, waist=30, hips=38)

        def client_for(user):
            c = APIClient()
            token, _ = Token.objects.get_or_create(user=user)
            c.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
            return c
        self.client_for = client_for

    def make_order_with_materials(self):
        from apps.catalog.models import GarmentJob, GarmentTemplate, JobMaterial
        from apps.inventory.models import CatalogItem, CatalogSection, InventoryItem
        from domains.orders.services import OrderService

        order = OrderService.create_order_for_customer(
            self.customer, {"base_price": 9000}, user=self.owner)
        template = GarmentTemplate.resolve("blouse")
        job = GarmentJob.objects.create(order=order, template=template)
        section = CatalogSection.objects.first() or CatalogSection.objects.create(
            name="Fabrics", sequence=1)
        cat_item = CatalogItem.objects.create(
            section=section, name="Silk", item_type="FABRIC", default_unit="M")
        item = InventoryItem.objects.create(
            catalog_item=cat_item, name="Kanchipuram Silk", category="FABRIC",
            unit="M", current_stock=20)
        JobMaterial.objects.create(
            job=job, field_key="main_fabric", inventory_item=item,
            quantity=3, unit="M")
        return order

    def test_checklist_creates_plan_on_first_look(self):
        order = self.make_order_with_materials()
        res = self.client_for(self.master_user).get(
            f"/api/inventory/material-plans/checklist/?order={order.id}")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.data["plan"])
        lines = res.data["plan"]["lines"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["material_name"], "Kanchipuram Silk")
        self.assertIsNone(lines[0]["gathered_at"])
        # Second look finds the same plan rather than making another.
        res2 = self.client_for(self.owner).get(
            f"/api/inventory/material-plans/checklist/?order={order.id}")
        self.assertEqual(res2.data["plan"]["id"], res.data["plan"]["id"])

    def test_gather_is_supervisors_only_and_audited(self):
        from crm_api.models import OrderActivity
        order = self.make_order_with_materials()
        plan = self.client_for(self.owner).get(
            f"/api/inventory/material-plans/checklist/?order={order.id}").data["plan"]
        line_id = plan["lines"][0]["id"]

        refused = self.client_for(self.tailor_user).post(
            f"/api/inventory/material-plans/{plan['id']}/gather/",
            {"line_id": line_id}, format="json")
        self.assertEqual(refused.status_code, 403)

        ok = self.client_for(self.master_user).post(
            f"/api/inventory/material-plans/{plan['id']}/gather/",
            {"line_id": line_id}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertIsNotNone(ok.data["gathered_at"])
        self.assertEqual(ok.data["gathered_by_name"], "Master")
        self.assertTrue(OrderActivity.objects.filter(
            order=order, event_type="MATERIAL_GATHERED").exists())

        undone = self.client_for(self.master_user).post(
            f"/api/inventory/material-plans/{plan['id']}/gather/",
            {"line_id": line_id, "gathered": False}, format="json")
        self.assertIsNone(undone.data["gathered_at"])

    def test_line_photo_appends_and_audits(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from crm_api.models import OrderActivity
        order = self.make_order_with_materials()
        plan = self.client_for(self.owner).get(
            f"/api/inventory/material-plans/checklist/?order={order.id}").data["plan"]
        line_id = plan["lines"][0]["id"]

        photo = SimpleUploadedFile("silk.jpg", b"notreallyajpeg", content_type="image/jpeg")
        res = self.client_for(self.master_user).post(
            f"/api/inventory/material-plans/{plan['id']}/line-photo/",
            {"line_id": line_id, "image": photo}, format="multipart")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["photos"]), 1)
        self.assertIn("material_photos/", res.data["photos"][0])
        self.assertTrue(OrderActivity.objects.filter(
            order=order, event_type="MATERIAL_PHOTO").exists())

        refused = self.client_for(self.tailor_user).post(
            f"/api/inventory/material-plans/{plan['id']}/line-photo/",
            {"line_id": line_id, "image": SimpleUploadedFile("x.jpg", b"z", content_type="image/jpeg")},
            format="multipart")
        self.assertEqual(refused.status_code, 403)

    def test_checklist_read_does_not_create_for_tailor(self):
        from apps.inventory.models import OrderMaterialPlan
        order = self.make_order_with_materials()
        # An order the tailor is not on is invisible to them -- the checklist
        # answers with the same opaque 400 as a nonexistent order, and no
        # plan comes into being on their account either way.
        res = self.client_for(self.tailor_user).get(
            f"/api/inventory/material-plans/checklist/?order={order.id}")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(OrderMaterialPlan.objects.filter(order=order).exists())

    def test_checklist_on_delivered_order_returns_history_not_a_blank(self):
        from apps.inventory.models import OrderMaterialPlan
        order = self.make_order_with_materials()
        first = self.client_for(self.owner).get(
            f"/api/inventory/material-plans/checklist/?order={order.id}").data["plan"]
        # Delivery closes the plan; a later look must show that record, not
        # conjure a fresh blank one.
        OrderMaterialPlan.objects.filter(id=first["id"]).update(
            status=OrderMaterialPlan.Status.COMPLETED)
        order.order_status = "Delivered"
        order.save(update_fields=["order_status"])
        again = self.client_for(self.owner).get(
            f"/api/inventory/material-plans/checklist/?order={order.id}").data["plan"]
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(OrderMaterialPlan.objects.filter(order=order).count(), 1)
