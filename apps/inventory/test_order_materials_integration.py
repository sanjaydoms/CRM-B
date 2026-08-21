"""The order workflow and the stock ledger, joined.

The regression these pin down: materials chosen on the order form were stored
as bare item ids inside the garment's spec JSON, which nothing in the inventory
module reads. An order could name brocade, lining, can-can, canvas, zip, hooks
and thread, run all the way to Delivered, and leave every stock figure exactly
as it was before the order was taken. Nothing was reserved, issued or consumed,
and no movement carried an order id.

So these tests do not assert "stock went down". They assert that stock went
down *for a reason the system can name*: which garment, on which order, in what
quantity, moved by whom. A number that is right by accident is the bug this is
here to catch.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.catalog.models import GarmentJob, GarmentTemplate, JobMaterial
from crm_api.models import BoutiqueSettings, Customer, Order, OrderStage, Tailor
from domains.orders.services import OrderService

from . import order_materials
from .models import (
    Category, InventoryItem, OrderMaterialPlan, StockMovement, Unit,
)
from .services import InventoryService


class OrderMaterialsTestBase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@materials.test"
        tenant.name = "Materials Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)

        self.owner = User.objects.create_user(
            username="owner@materials.test", email="owner@materials.test",
            password="ownerpass123",
        )
        BoutiqueSettings.objects.get_or_create(id=1)

        self.customer = Customer.objects.create(
            first_name="Lakshmi", last_name="Iyer", mobile_number="919845012345",
            email_address="lakshmi@materials.test", address="44 Church Street",
            customer_type="Women", garment_type="Blouse",
        )
        # The workflow requires somebody to be holding the garment before
        # stitching may start, so a fixture order needs real staff on it.
        self.tailor = Tailor.objects.create(
            name="Sunita Devi", specialty="Stitching", role="Tailor")
        self.master = Tailor.objects.create(
            name="Ravi Kumar", specialty="Cutting", role="Master")
        self.blouse_template = GarmentTemplate.objects.create(
            key='blouse', name='Blouse', version=1, sequence=0)
        self.lehenga_template = GarmentTemplate.objects.create(
            key='lehenga', name='Lehenga', version=1, sequence=1)

        self.brocade = self.stocked('FAB-MRN-001', 'Maroon Brocade',
                                    Category.FABRIC, Unit.METER, 25)
        self.lining = self.stocked('LIN-COT-001', 'Cotton Lining',
                                   Category.LINING, Unit.METER, 30)
        self.hooks = self.stocked('STI-HK-001', 'Hooks and Eyes',
                                  Category.STITCHING, Unit.PACKET, 50)
        self.cancan = self.stocked('LIN-CAN-001', 'Can Can Net',
                                   Category.LINING, Unit.METER, 20)

    def stocked(self, code, name, category, unit, quantity):
        item = InventoryItem.objects.create(
            item_code=code, name=name, category=category, unit=unit,
            purchase_price=Decimal('100.00'), reorder_level=Decimal('5'),
        )
        if quantity:
            InventoryService.stock_in(item, Decimal(quantity), user=self.owner,
                                      remarks='Opening stock')
        item.refresh_from_db()
        return item

    def make_order(self, order_id="T2B-MAT-1"):
        order = Order.objects.create(order_id=order_id, customer=self.customer,
                                     total_amount=Decimal('32025.00'),
                                     tailor=self.tailor, master=self.master)
        # The workflow reads its stages; OrderService seeds them on real orders.
        for seq, key in enumerate([
            'created', 'measurements_completed', 'fabric_confirmed', 'pattern_cutting',
            'maggam_work', 'assigned_to_tailor', 'stitching_in_progress',
            'stitching_completed', 'finishing', 'pressing', 'master_quality_check',
            'trial_scheduled', 'trial_completed', 'ready_for_delivery', 'delivered',
        ]):
            OrderStage.objects.create(
                order=order, stage_key=key, stage_name=key.replace('_', ' ').title(),
                sequence=seq,
            )
        return order

    def garment(self, order, template, materials, sequence=0, measurements=None):
        job = GarmentJob.objects.create(
            order=order, template=template, template_version=1,
            spec={},
            # Assigning a tailor requires that somebody measured something.
            measurements=measurements or {'chest': '36'},
            sequence=sequence,
        )
        for field_key, item, quantity in materials:
            JobMaterial.objects.create(
                job=job, field_key=field_key, inventory_item=item,
                quantity=Decimal(str(quantity)),
                unit=item.unit if item else '',
                source=JobMaterial.Source.STORE if item else JobMaterial.Source.CUSTOMER,
            )
        return job

    #: The workflow in order. Reaching a stage means completing what precedes
    #: it, which is what the backend now requires of everyone -- these tests
    #: used to jump straight to fabric_confirmed or stitching_completed, and a
    #: fixture that can do what the product forbids is testing a system nobody
    #: runs.
    SEQUENCE = [
        'created', 'measurements_completed', 'fabric_confirmed', 'pattern_cutting',
        'maggam_work', 'assigned_to_tailor', 'stitching_in_progress',
        'stitching_completed', 'finishing', 'pressing', 'master_quality_check',
        'trial_scheduled', 'trial_completed', 'ready_for_delivery', 'delivered',
    ]
    #: Stages a garment may legitimately not have. Skipped rather than completed
    #: while walking, so the walk exercises the real distinction.
    OPTIONAL = {'maggam_work'}

    def advance(self, order, stage_key, user=None):
        """Take the order to `stage_key`, completing everything before it."""
        for key in self.SEQUENCE[:self.SEQUENCE.index(stage_key)]:
            stage = order.stages.filter(stage_key=key).first()
            if stage is None or stage.status in ('COMPLETED', 'SKIPPED'):
                continue
            OrderService.transition_order_stage(
                order=order, stage_key=key,
                new_status='SKIPPED' if key in self.OPTIONAL else 'COMPLETED',
                user=user or self.owner,
            )
        return OrderService.transition_order_stage(
            order=order, stage_key=stage_key, new_status='COMPLETED',
            user=user or self.owner,
        )

    def stock(self, item):
        item.refresh_from_db()
        return item.current_stock, item.reserved_stock


class PlanFromGarmentJobsTests(OrderMaterialsTestBase):
    """1 and 2: the wizard's selections become real, per-garment material lines."""

    def test_one_garment_with_several_materials(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [
            ('main_fabric', self.brocade, 2),
            ('lining', self.lining, 1.5),
            ('hooks', self.hooks, 1),
        ])
        plan, skipped = order_materials.plan_from_garment_jobs(order, user=self.owner)

        self.assertEqual(skipped, [])
        self.assertEqual(plan.lines.count(), 3)
        self.assertIsNone(plan.bom, "a wizard-built plan has no BOM behind it")
        by_name = {line.material_name: line for line in plan.lines.all()}
        self.assertEqual(by_name['Maroon Brocade'].required_quantity, Decimal('2.000'))
        self.assertEqual(by_name['Cotton Lining'].required_quantity, Decimal('1.500'))
        self.assertEqual(by_name['Maroon Brocade'].unit, Unit.METER)

    def test_two_garments_keep_their_materials_apart(self):
        order = self.make_order()
        blouse = self.garment(order, self.blouse_template, [
            ('main_fabric', self.brocade, 2), ('hooks', self.hooks, 1)], sequence=0)
        lehenga = self.garment(order, self.lehenga_template, [
            ('main_fabric', self.brocade, 4), ('can_can', self.cancan, 6)], sequence=1)

        plan, _ = order_materials.plan_from_garment_jobs(order, user=self.owner)
        self.assertEqual(plan.lines.count(), 4)

        by_job = {}
        for line in plan.lines.select_related('garment_job'):
            by_job.setdefault(line.garment_job_id, []).append(line)
        self.assertEqual(len(by_job[blouse.id]), 2)
        self.assertEqual(len(by_job[lehenga.id]), 2)
        # Every line knows which dress it belongs to. Without this the ledger
        # can say six metres left stock but not which garment took what.
        self.assertTrue(all(line.garment_job_id for line in plan.lines.all()))

    def test_same_material_on_two_garments_stays_two_lines(self):
        """Two dresses cut from one roll are two separate accounts of it."""
        order = self.make_order()
        self.garment(order, self.blouse_template,
                     [('main_fabric', self.brocade, 2)], sequence=0)
        self.garment(order, self.lehenga_template,
                     [('main_fabric', self.brocade, 4)], sequence=1)

        plan, _ = order_materials.plan_from_garment_jobs(order, user=self.owner)
        brocade_lines = plan.lines.filter(item=self.brocade)
        self.assertEqual(brocade_lines.count(), 2)
        self.assertEqual(
            sum(line.required_quantity for line in brocade_lines), Decimal('6.000'))
        # ...and they are attributable to different garments.
        self.assertEqual(len({line.garment_job_id for line in brocade_lines}), 2)

    def test_a_material_with_no_quantity_is_reported_not_silently_planned(self):
        """A line with no quantity would reserve nothing and still reconcile."""
        order = self.make_order()
        self.garment(order, self.blouse_template, [
            ('main_fabric', self.brocade, 2), ('hooks', self.hooks, 0)])

        plan, skipped = order_materials.plan_from_garment_jobs(order, user=self.owner)
        self.assertEqual(plan.lines.count(), 1)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]['material'], 'Hooks and Eyes')
        self.assertIn('no quantity', skipped[0]['reason'])

    def test_an_order_with_no_materials_plans_nothing_and_does_not_crash(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [])
        plan, skipped = order_materials.plan_from_garment_jobs(order, user=self.owner)
        self.assertIsNone(plan)
        self.assertEqual(skipped, [])


class ReservationTests(OrderMaterialsTestBase):
    """4 and 6: reserving, and what happens when the shelf is short."""

    def test_confirming_fabric_reserves_against_stock(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [
            ('main_fabric', self.brocade, 2), ('lining', self.lining, 1.5)])

        self.advance(order, 'fabric_confirmed')

        # Reserved, not deducted: the cloth is spoken for but still on the shelf.
        self.assertEqual(self.stock(self.brocade), (Decimal('25.000'), Decimal('2.000')))
        self.assertEqual(self.brocade.available_stock, Decimal('23.000'))
        self.assertEqual(
            StockMovement.objects.filter(
                item=self.brocade, movement_type=StockMovement.Type.RESERVATION,
                order=order).count(), 1)

    def test_reservation_movement_names_the_garment_it_is_for(self):
        order = self.make_order()
        blouse = self.garment(order, self.blouse_template,
                              [('main_fabric', self.brocade, 2)], sequence=0)
        lehenga = self.garment(order, self.lehenga_template,
                               [('main_fabric', self.brocade, 4)], sequence=1)

        self.advance(order, 'fabric_confirmed')

        movements = StockMovement.objects.filter(
            item=self.brocade, movement_type=StockMovement.Type.RESERVATION)
        attributed = {m.garment_job_id: m.quantity for m in movements}
        self.assertEqual(attributed[blouse.id], Decimal('2.000'))
        self.assertEqual(attributed[lehenga.id], Decimal('4.000'))

    def test_selecting_a_material_never_consumes_it(self):
        """Reservation is not consumption, and must never quietly become it.

        The invariant that separates "this cloth is promised to an order" from
        "this cloth is gone". Getting it wrong in either direction is expensive:
        consume too early and the shelf lies about what is physically there;
        never reserve and two orders sell the same roll.
        """
        order = self.make_order()
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 2)])
        self.advance(order, 'fabric_confirmed')

        current, reserved = self.stock(self.brocade)
        self.assertEqual(current, Decimal('25.000'), 'still physically on the shelf')
        self.assertEqual(reserved, Decimal('2.000'), 'but spoken for')
        self.assertFalse(
            StockMovement.objects.filter(
                item=self.brocade,
                movement_type__in=(StockMovement.Type.CONSUMPTION,
                                   StockMovement.Type.ISSUE)).exists(),
            'selecting a material must not consume or issue it')
        line = order_materials.live_plan(order).lines.get(item=self.brocade)
        self.assertEqual(line.consumed_quantity, Decimal('0'))

    def test_a_reservation_nobody_consumes_is_given_back(self):
        """The inverse of consumption: what production never used comes back.

        Full cancellation and rework arrive with the exception flows, but the
        release path they will use is this one, and it has to be right before
        anything is built on it.
        """
        order = self.make_order()
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 2)])
        self.advance(order, 'fabric_confirmed')
        self.assertEqual(self.stock(self.brocade)[1], Decimal('2.000'))

        released = order_materials.release_unused(
            order_materials.live_plan(order), user=self.owner)

        self.assertEqual(released[0]['quantity'], Decimal('2.000'))
        current, reserved = self.stock(self.brocade)
        self.assertEqual(current, Decimal('25.000'), 'nothing was ever taken')
        self.assertEqual(reserved, Decimal('0.000'), 'and nothing is still held')
        self.assertTrue(StockMovement.objects.filter(
            item=self.brocade, movement_type=StockMovement.Type.RELEASE,
            garment_job__order=order).exists())

    def test_short_stock_reserves_what_there_is_and_reports_the_rest(self):
        """A boutique routinely sells cloth it has not bought yet."""
        order = self.make_order()
        self.garment(order, self.blouse_template,
                     [('main_fabric', self.brocade, 40)])  # only 25 in stock

        self.advance(order, 'fabric_confirmed')

        current, reserved = self.stock(self.brocade)
        self.assertEqual(current, Decimal('25.000'))
        self.assertEqual(reserved, Decimal('25.000'))
        report = order.activities.filter(event_type='STAGE_TRANSITION').first().metadata
        self.assertTrue(report['materials']['shortfalls'])
        self.assertEqual(report['materials']['shortfalls'][0]['material'], 'Maroon Brocade')

    def test_reserving_twice_does_not_reserve_twice_over(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 2)])
        self.advance(order, 'fabric_confirmed')
        plan = order_materials.live_plan(order)
        order_materials.reserve(plan, user=self.owner, allow_partial=True)
        self.assertEqual(self.stock(self.brocade)[1], Decimal('2.000'))


class ConsumptionTests(OrderMaterialsTestBase):
    """5: stock leaves the shelf when the garment is stitched, not before."""

    def test_stitching_consumes_and_reduces_stock(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [
            ('main_fabric', self.brocade, 2), ('hooks', self.hooks, 1)])

        self.advance(order, 'fabric_confirmed')
        self.assertEqual(self.stock(self.brocade), (Decimal('25.000'), Decimal('2.000')))

        self.advance(order, 'stitching_completed')

        # Consumed: gone from stock, and no longer reserved.
        self.assertEqual(self.stock(self.brocade), (Decimal('23.000'), Decimal('0.000')))
        self.assertEqual(self.stock(self.hooks), (Decimal('49.000'), Decimal('0.000')))

    def test_consumption_is_attributable_to_the_garment_that_took_it(self):
        """The question the ledger could not answer: which dress took what."""
        order = self.make_order()
        blouse = self.garment(order, self.blouse_template,
                              [('main_fabric', self.brocade, 2)], sequence=0)
        lehenga = self.garment(order, self.lehenga_template,
                               [('main_fabric', self.brocade, 4)], sequence=1)

        self.advance(order, 'fabric_confirmed')
        self.advance(order, 'stitching_completed')

        self.assertEqual(self.stock(self.brocade)[0], Decimal('19.000'))  # 25 - 6

        consumed = StockMovement.objects.filter(
            item=self.brocade, movement_type=StockMovement.Type.CONSUMPTION)
        by_job = {m.garment_job_id: m for m in consumed}
        self.assertEqual(by_job[blouse.id].quantity, Decimal('2.000'))
        self.assertEqual(by_job[lehenga.id].quantity, Decimal('4.000'))
        # ...and each one names the order and the person who caused it.
        for movement in consumed:
            self.assertEqual(movement.order_id, order.id)
            self.assertEqual(movement.user_id, self.owner.id)
            self.assertIsNotNone(movement.created_at)

    def test_every_movement_names_the_stage_that_caused_it(self):
        """An audit has to read as a sentence, not a number.

        "2m brocade consumed for the Blouse during Stitching Completed by
        Sunita at 12:24" -- item, garment, order, stage, type, quantity, who,
        when. The stage is what turns a ledger line into an account of what
        happened on the floor.
        """
        order = self.make_order()
        blouse = self.garment(order, self.blouse_template,
                              [('main_fabric', self.brocade, 2)])
        self.advance(order, 'fabric_confirmed')
        self.advance(order, 'stitching_completed')

        reservation = StockMovement.objects.get(
            item=self.brocade, movement_type=StockMovement.Type.RESERVATION)
        consumption = StockMovement.objects.get(
            item=self.brocade, movement_type=StockMovement.Type.CONSUMPTION)

        self.assertEqual(reservation.stage_key, 'fabric_confirmed')
        self.assertEqual(consumption.stage_key, 'stitching_completed')
        # The whole sentence, from one row.
        self.assertEqual(consumption.garment_job_id, blouse.id)
        self.assertEqual(consumption.order_id, order.id)
        self.assertEqual(consumption.quantity, Decimal('2.000'))
        self.assertEqual(consumption.user_id, self.owner.id)
        self.assertIsNotNone(consumption.created_at)

    def test_a_release_carries_the_stage_it_was_made_at(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 2)])
        self.advance(order, 'fabric_confirmed')

        order_materials.release_unused(
            order_materials.live_plan(order), user=self.owner,
            stage_key='ready_for_delivery')

        release = StockMovement.objects.get(
            item=self.brocade, movement_type=StockMovement.Type.RELEASE)
        self.assertEqual(release.stage_key, 'ready_for_delivery')
        self.assertEqual(release.quantity, Decimal('2.000'))

    def test_a_garment_added_after_fabric_was_confirmed_is_still_accounted_for(self):
        """The safety net, for materials the plan could not have seen.

        The wizard creates the order first and its garments immediately after,
        so an order can pass through Fabric Confirmed while it still has no
        garment rows -- there is nothing to plan from, and no plan is made. The
        materials arrive moments later. Without a second chance to plan, that
        order would reach Delivered having moved no stock at all, which is the
        exact failure this whole change set exists to end.
        """
        order = self.make_order()
        # Fabric confirmed while the order is still empty: nothing to plan.
        self.advance(order, 'fabric_confirmed')
        self.assertIsNone(order_materials.live_plan(order))
        self.assertEqual(self.stock(self.brocade), (Decimal('25.000'), Decimal('0.000')))

        # The garment and its materials land afterwards.
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 2)])

        self.advance(order, 'stitching_completed')

        self.assertEqual(self.stock(self.brocade)[0], Decimal('23.000'))
        self.assertTrue(StockMovement.objects.filter(
            item=self.brocade, movement_type=StockMovement.Type.CONSUMPTION,
            order=order).exists())

    def test_nothing_moves_before_the_fabric_is_confirmed(self):
        """Taking the order is not committing the cloth."""
        order = self.make_order()
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 2)])
        # Up to the stage immediately before fabric is confirmed.
        self.advance(order, 'measurements_completed')
        self.assertEqual(self.stock(self.brocade), (Decimal('25.000'), Decimal('0.000')))
        self.assertFalse(StockMovement.objects.filter(order=order).exists())


class CustomerSuppliedMaterialTests(OrderMaterialsTestBase):
    """7: the customer's own cloth never touches the boutique's stock."""

    def test_customer_material_is_planned_but_never_reserved_or_consumed(self):
        order = self.make_order()
        job = GarmentJob.objects.create(
            order=order, template=self.blouse_template, template_version=1,
            spec={'material_source': 'customer'},
            # Assigning a tailor needs real measurements, not merely a stage
            # marked done -- so a hand-built job needs them too.
            measurements={'chest': '36'}, sequence=0)
        JobMaterial.objects.create(
            job=job, field_key='main_fabric', inventory_item=None,
            free_text="Customer's raw silk, 1.2m, tag VT-CM-01",
            quantity=Decimal('1.2'), unit=Unit.METER,
            source=JobMaterial.Source.CUSTOMER)
        JobMaterial.objects.create(
            job=job, field_key='hooks', inventory_item=self.hooks,
            quantity=Decimal('1'), unit=Unit.PACKET,
            source=JobMaterial.Source.STORE)

        self.advance(order, 'fabric_confirmed')
        self.advance(order, 'stitching_completed')

        # The boutique's hooks moved; the customer's silk did not appear in
        # boutique stock at any point.
        self.assertEqual(self.stock(self.hooks)[0], Decimal('49.000'))
        customer_line = order_materials.live_plan(order).lines.get(
            is_customer_supplied=True)
        self.assertEqual(customer_line.consumed_quantity, Decimal('0'))
        self.assertEqual(customer_line.reserved_quantity, Decimal('0'))
        self.assertFalse(
            StockMovement.objects.filter(remarks__icontains='raw silk').exists())


class ReconciliationTests(OrderMaterialsTestBase):
    """8: the order's material account has to add up, and be explainable."""

    def test_delivery_releases_the_unused_and_reconciles(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [
            ('main_fabric', self.brocade, 2), ('lining', self.lining, 1.5)])

        opening = self.stock(self.brocade)[0]
        self.advance(order, 'fabric_confirmed')
        self.advance(order, 'stitching_completed')
        self.advance(order, 'master_quality_check')
        self.advance(order, 'delivered')

        plan = OrderMaterialPlan.objects.get(order=order)
        self.assertEqual(plan.status, OrderMaterialPlan.Status.COMPLETED)

        line = plan.lines.get(item=self.brocade)
        # X - Z + R - W, with nothing returned and nothing wasted.
        expected = (opening - line.consumed_quantity
                    + line.returned_quantity - line.wasted_quantity)
        self.assertEqual(self.stock(self.brocade)[0], expected)
        # Nothing left spoken for once the order is out of the building.
        self.assertEqual(self.stock(self.brocade)[1], Decimal('0.000'))
        self.assertTrue(order_materials.reconcile(plan)['is_reconciled'])

    def test_the_ledger_reconstructs_the_stock_figure_from_its_movements(self):
        """Every change is explained by a movement, and they sum to the balance."""
        order = self.make_order()
        self.garment(order, self.blouse_template,
                     [('main_fabric', self.brocade, 2)], sequence=0)
        self.garment(order, self.lehenga_template,
                     [('main_fabric', self.brocade, 4)], sequence=1)

        self.advance(order, 'fabric_confirmed')
        self.advance(order, 'stitching_completed')
        self.advance(order, 'master_quality_check')
        self.advance(order, 'delivered')

        movements = StockMovement.objects.filter(item=self.brocade).order_by('created_at')
        # Each movement records the balance either side of it, so the chain has
        # to be continuous -- no change without a line to explain it.
        for earlier, later in zip(movements, movements[1:]):
            self.assertEqual(earlier.new_stock, later.previous_stock)
        self.assertEqual(movements.last().new_stock, self.stock(self.brocade)[0])

    def test_using_less_than_planned_returns_the_difference_to_the_shelf(self):
        """Two metres were reserved, one was used; the other must come back.

        This is the difference between a reservation and a write-off, and the
        case where a wrong ledger is most expensive: material invisible to every
        other order for as long as the plan stays open.
        """
        order = self.make_order()
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 2)])
        self.advance(order, 'fabric_confirmed')

        plan = order_materials.live_plan(order)
        line = plan.lines.get(item=self.brocade)
        order_materials.confirm_consumption(line, Decimal('1'), user=self.owner)

        current, reserved = self.stock(self.brocade)
        self.assertEqual(current, Decimal('24.000'))
        self.assertEqual(reserved, Decimal('1.000'), "the unused metre is still held")

        self.advance(order, 'stitching_completed')
        self.advance(order, 'master_quality_check')
        self.advance(order, 'delivered')

        line.refresh_from_db()
        current, reserved = self.stock(self.brocade)
        self.assertEqual(reserved, Decimal('0.000'), "nothing left spoken for")
        # The order took what the second metre's consumption at stitching used,
        # and the account still balances against the ledger.
        self.assertEqual(
            current,
            Decimal('25.000') - line.consumed_quantity
            + line.returned_quantity - line.wasted_quantity)

    def test_waste_is_recorded_separately_from_what_went_into_the_garment(self):
        order = self.make_order()
        self.garment(order, self.blouse_template, [('main_fabric', self.brocade, 3)])
        self.advance(order, 'fabric_confirmed')

        plan = order_materials.live_plan(order)
        line = plan.lines.get(item=self.brocade)
        order_materials.confirm_consumption(
            line, Decimal('2'), wasted=Decimal('1'), user=self.owner)

        line.refresh_from_db()
        self.assertEqual(line.consumed_quantity, Decimal('2.000'))
        self.assertEqual(line.wasted_quantity, Decimal('1.000'))
        # Both left the shelf, but the ledger can tell offcuts from garment.
        self.assertEqual(self.stock(self.brocade)[0], Decimal('22.000'))
        self.assertTrue(StockMovement.objects.filter(
            item=self.brocade, movement_type=StockMovement.Type.WASTE,
            garment_job__order=order).exists())

    def test_the_order_activity_log_records_what_left_stock_and_for_which_garment(self):
        order = self.make_order()
        self.garment(order, self.blouse_template,
                     [('main_fabric', self.brocade, 2)], sequence=0)
        self.advance(order, 'fabric_confirmed')
        self.advance(order, 'stitching_completed')

        entry = order.activities.filter(
            event_type='STAGE_TRANSITION',
            metadata__stage_key='stitching_completed').first()
        consumed = entry.metadata['materials']['consumed']
        self.assertEqual(consumed[0]['material'], 'Maroon Brocade')
        self.assertEqual(consumed[0]['quantity'], '2.000')
        self.assertEqual(consumed[0]['garment'], 'Blouse')
