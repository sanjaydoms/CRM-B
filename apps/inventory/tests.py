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
        names = {row['name'] for row in response.data}
        for expected in ('Dabka', 'Nakshi', 'Kasab', 'Salma', 'Sitara'):
            self.assertIn(expected, names)

    def test_stockable_filter_excludes_systems_and_garment_categories(self):
        response = self.client.get('/api/inventory/catalog/items/?stockable=true&search=Payment')
        self.assertEqual(list(response.data), [])

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
        self.assertEqual(len(response.data), 8)

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
