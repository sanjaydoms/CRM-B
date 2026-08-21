"""Materials, from order taken to order closed.

The ten steps the specification lays out, in the order it lays them out:

     1. generate a BOM for the order            plan_materials()
     2. check availability                      check_availability()
     3. reserve required materials              reserve()
     4. prevent double allocation               the constraint + reserve()'s guard
     5. deduct only on confirmed consumption    confirm_consumption()
     6. record actual quantities used           confirm_consumption()
     7. record waste                            confirm_consumption(wasted=...)
     8. return unused reserved materials        release_unused()
     9. deduct packaging at dispatch            deduct_packaging()
    10. reconcile before closing                reconcile()

Two rules run through all of it.

Boutique stock only ever moves through InventoryService, so every reservation,
consumption and return here leaves a StockMovement behind it. Nothing in this
module writes a stock figure itself.

Customer-supplied material never touches boutique stock. Its lines are planned
and reconciled alongside everything else -- the garment cannot be made without
them -- but they are satisfied from CustomerMaterial, which is the customer's
own ledger. A line marked customer-supplied is skipped by every operation that
would reserve, consume or return boutique stock.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from . import bom as bom_service
from .models import (
    BomLine, Category, CustomerMaterial, CustomerMaterialMovement,
    OrderMaterialLine, OrderMaterialPlan,
)
from .services import InventoryService

#: An inventory category answers "what shelf is this on"; a BOM role answers
#: "what part does it play in the garment". The plan is keyed on the second, so
#: a wizard selection has to be translated. Anything unmapped is OTHER rather
#: than a guess.
_ROLE_BY_CATEGORY = {
    Category.FABRIC: BomLine.Role.FABRIC,
    Category.BORDER: BomLine.Role.ACCESSORY,
    Category.LINING: BomLine.Role.LINING,
    Category.EMBELLISHMENT: BomLine.Role.ACCESSORY,
    Category.STITCHING: BomLine.Role.THREAD,
    Category.PACKAGING: BomLine.Role.PACKAGING,
    Category.MAGGAM: BomLine.Role.EMBROIDERY,
    Category.OTHER: BomLine.Role.OTHER,
}

#: Roles deducted at dispatch rather than during production -- the box and the
#: labels are used when the garment goes out, not while it is being made.
DISPATCH_ROLES = frozenset({BomLine.Role.PACKAGING, BomLine.Role.LABEL})


class MaterialPlanError(ValueError):
    """An order's materials cannot be moved the way that was asked."""


def _still_to_reserve(line):
    """How much more this line needs to have reserved right now.

    reserved_quantity is a lifetime total, not a current holding, so it cannot
    be subtracted from the requirement directly: after material has been
    released, the line has reserved its full requirement and holds none of it.
    What is still needed is the unmet requirement minus what is still held.
    """
    unmet = line.required_quantity - line.consumed_quantity - line.wasted_quantity
    return max(Decimal('0'), unmet - line.outstanding_reservation)


#: Quantities are stored to three places; rounding on the way in keeps the
#: balances and the movement rows that explain them identical.
PRECISION = Decimal('0.001')


def _quantity(value, field='quantity'):
    """Parse and round a quantity, refusing anything that is not a real number.

    Decimal('nan') parses happily and only blows up on the first comparison --
    and decimal.InvalidOperation is an ArithmeticError, so it would sail past
    every `except ValueError` above and out as a 500. The comparison lives
    inside the try for that reason.
    """
    try:
        quantity = Decimal(str(value))
        if not quantity.is_finite():
            raise MaterialPlanError(f'{field} must be a finite number.')
        if quantity < 0:
            raise MaterialPlanError(f'{field} cannot be negative.')
        return quantity.quantize(PRECISION, rounding=ROUND_HALF_UP)
    except MaterialPlanError:
        raise
    except (ArithmeticError, ValueError, TypeError):
        raise MaterialPlanError(f'{field} must be a number.')


# --- 1. generate ---------------------------------------------------------

@transaction.atomic
def plan_materials(order, bom, variables=None, *, user=None, include_optional=False):
    """Turn a BOM into this order's material plan.

    The computed requirement is written onto the lines, not left to be derived
    later: re-versioning the BOM or correcting a measurement must not silently
    change what an order already reserved.
    """
    if OrderMaterialPlan.objects.select_for_update().filter(
            order=order, status__in=[OrderMaterialPlan.Status.DRAFT,
                                     OrderMaterialPlan.Status.RESERVED,
                                     OrderMaterialPlan.Status.IN_PRODUCTION]).exists():
        raise MaterialPlanError(
            f'Order {order.order_id} already has a live material plan. '
            f'Cancel it before planning again.')

    try:
        rows = bom_service.requirements(bom, variables or {},
                                        include_optional=include_optional)
    except bom_service.BomError as exc:
        raise MaterialPlanError(str(exc))

    plan = OrderMaterialPlan.objects.create(
        order=order, bom=bom, bom_version=bom.version,
        variables=variables or {}, created_by=user,
    )
    OrderMaterialLine.objects.bulk_create([
        OrderMaterialLine(
            plan=plan,
            bom_line_id=row['line_id'],
            item_id=row['inventory_item_id'],
            role=row['role'],
            material_name=row['material'],
            unit=row['unit'],
            required_quantity=row['required_quantity'],
            is_customer_supplied=row['is_customer_supplied'],
            sequence=index,
        )
        for index, row in enumerate(rows)
    ])
    return plan


@transaction.atomic
def plan_from_garment_jobs(order, *, user=None):
    """Turn what the wizard selected for each garment into this order's plan.

    The other origin for a plan. plan_materials() resolves a BOM -- a recipe for
    a garment type. This resolves the boutique's actual choices for one order:
    the owner picked this brocade off this rack for the lehenga and said how
    much. Both produce OrderMaterialLine rows, so reserve(), confirm_consumption(),
    release_unused() and reconcile() work on either without knowing which.

    A JobMaterial with no quantity is not planned. That is deliberate: the wizard
    is what captures quantity, and a line with a required quantity of zero would
    reserve nothing, consume nothing and still report itself reconciled -- a
    material silently absent from the order's account rather than visibly
    missing from it. Returns the skipped lines so the caller can say so.

    Returns (plan, skipped). `plan` is None when there was nothing to plan.
    """
    if OrderMaterialPlan.objects.select_for_update().filter(
            order=order, status__in=[OrderMaterialPlan.Status.DRAFT,
                                     OrderMaterialPlan.Status.RESERVED,
                                     OrderMaterialPlan.Status.IN_PRODUCTION]).exists():
        raise MaterialPlanError(
            f'Order {order.order_id} already has a live material plan. '
            f'Cancel it before planning again.')

    from apps.catalog.models import JobMaterial

    selections = (
        JobMaterial.objects
        .filter(job__order=order)
        .select_related('inventory_item', 'job', 'job__template')
        .order_by('job__sequence', 'field_key')
    )

    rows, skipped = [], []
    for selection in selections:
        item = selection.inventory_item
        is_customer = selection.source == JobMaterial.Source.CUSTOMER
        name = item.name if item else (selection.free_text or selection.field_key)

        quantity = _quantity(selection.quantity, 'quantity')
        if quantity <= 0:
            skipped.append({
                'garment': selection.job.template.name if selection.job.template_id else 'Garment',
                'field_key': selection.field_key,
                'material': name,
                'reason': 'no quantity was recorded on the order',
            })
            continue

        rows.append(OrderMaterialLine(
            plan=None,  # set below, once the plan row exists
            garment_job=selection.job,
            job_material=selection,
            item=item,
            role=(_ROLE_BY_CATEGORY.get(item.category, BomLine.Role.OTHER)
                  if item else BomLine.Role.OTHER),
            material_name=name,
            unit=selection.unit or (item.unit if item else ''),
            required_quantity=quantity,
            is_customer_supplied=is_customer,
            sequence=len(rows),
        ))

    if not rows:
        return None, skipped

    plan = OrderMaterialPlan.objects.create(
        order=order, bom=None, bom_version=None, variables={}, created_by=user,
    )
    for row in rows:
        row.plan = plan
    OrderMaterialLine.objects.bulk_create(rows)
    return plan, skipped


# --- 2. check ------------------------------------------------------------

def check_availability(plan):
    """What this plan cannot currently be satisfied from.

    Reads available stock (on hand minus what other orders already hold), so a
    material that exists but is entirely spoken for is reported as short --
    which is the answer that matters.
    """
    shortfalls = []
    # Demand is summed per item before it is compared with stock. Two lines can
    # name the same material -- a lehenga's skirt and its blouse are both silk --
    # and checking each against the whole available figure independently reports
    # a plan as satisfiable when the two together are not.
    demand = {}
    for line in plan.lines.select_related('item'):
        if line.is_customer_supplied:
            continue
        if line.item is None:
            shortfalls.append({
                'line_id': str(line.id), 'material': line.material_name,
                'required': line.required_quantity, 'available': None,
                'short_by': line.required_quantity,
                'reason': 'not linked to a stocked item',
            })
            continue
        outstanding = _still_to_reserve(line)
        if outstanding <= 0:
            continue
        entry = demand.setdefault(
            line.item_id, {'item': line.item, 'wanted': Decimal('0'), 'lines': []})
        entry['wanted'] += outstanding
        entry['lines'].append(line)

    for entry in demand.values():
        item = entry['item']
        item.refresh_from_db(fields=['current_stock', 'reserved_stock'])
        available = item.available_stock
        if available < entry['wanted']:
            shortfalls.append({
                'line_id': str(entry['lines'][0].id),
                'material': item.name,
                'required': entry['wanted'], 'available': available,
                'short_by': entry['wanted'] - available,
                'reason': 'insufficient available stock',
            })
    return shortfalls


# --- 3 and 4. reserve, once -----------------------------------------------

@transaction.atomic
def reserve(plan, *, user=None, allow_partial=False, stage_key=None):
    """Reserve everything this plan needs.

    Refuses outright if anything is short, unless allow_partial says otherwise:
    a half-reserved order silently competing for the rest is worse than a clear
    refusal naming what is missing.

    Double allocation is prevented in two places. The database allows only one
    live plan per order, and each line reserves only the difference between what
    it needs and what it already holds -- so calling this twice reserves nothing
    the second time rather than reserving everything again.
    """
    locked = OrderMaterialPlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status not in (OrderMaterialPlan.Status.DRAFT,
                             OrderMaterialPlan.Status.RESERVED):
        raise MaterialPlanError(
            f'A plan that is {locked.get_status_display().lower()} cannot be reserved.')

    shortfalls = check_availability(locked)
    if shortfalls and not allow_partial:
        names = ', '.join(f"{s['material']} (short {s['short_by']})" for s in shortfalls[:5])
        raise MaterialPlanError(f'Not enough stock to reserve: {names}.')

    reserved = []
    for line in locked.lines.select_related('item'):
        if line.is_customer_supplied or line.item is None:
            continue
        outstanding = _still_to_reserve(line)
        if outstanding <= 0:
            continue
        # Re-read: an earlier line in this same loop may have reserved from the
        # very same item, so the copy loaded with the queryset is already stale.
        line.item.refresh_from_db(fields=['current_stock', 'reserved_stock'])
        available = line.item.available_stock
        quantity = min(outstanding, available) if allow_partial else outstanding
        if quantity <= 0:
            continue
        InventoryService.reserve(
            line.item, quantity, user=user, order=locked.order,
            garment_job=line.garment_job, stage_key=stage_key,
            remarks=f'Reserved for {locked.order.order_id}')
        line.reserved_quantity += quantity
        line.save(update_fields=['reserved_quantity'])
        reserved.append({'material': line.material_name, 'quantity': quantity})

    locked.status = OrderMaterialPlan.Status.RESERVED
    locked.save(update_fields=['status', 'updated_at'])
    return {'reserved': reserved, 'shortfalls': shortfalls}


# --- 5, 6 and 7. consume, and record waste --------------------------------

@transaction.atomic
def confirm_consumption(line, used, *, wasted=0, user=None, from_location=None,
                        stage_key=None):
    """Production confirms what it actually used, and what it spoiled.

    This is the only place boutique stock leaves for an order. Reserving does
    not deduct anything -- material sits on the shelf, spoken for -- and it is
    this call, made when the work is done, that takes it off.
    """
    used = _quantity(used, 'used')
    wasted = _quantity(wasted, 'wasted')
    if used == 0 and wasted == 0:
        raise MaterialPlanError('Nothing to record: both used and wasted are zero.')

    # of=('self',) locks the line row only. `item` is nullable, so select_related
    # makes it a LEFT JOIN, and Postgres refuses FOR UPDATE on the nullable side
    # of an outer join -- the plain form raises NotSupportedError here.
    locked = OrderMaterialLine.objects.select_for_update(of=('self',)).select_related(
        'item', 'plan').get(pk=line.pk)

    if locked.is_customer_supplied:
        raise MaterialPlanError(
            f"'{locked.material_name}' is customer-supplied. Record it against the "
            f"customer's own material, not boutique stock.")
    if locked.item is None:
        raise MaterialPlanError(
            f"'{locked.material_name}' is not linked to a stocked item.")

    # Locked, because the status is read here and written below; without it a
    # consumption racing a close() can resurrect a COMPLETED plan.
    plan = OrderMaterialPlan.objects.select_for_update().get(pk=locked.plan_id)
    if plan.status not in (OrderMaterialPlan.Status.RESERVED,
                           OrderMaterialPlan.Status.IN_PRODUCTION):
        raise MaterialPlanError(
            f'Materials cannot be consumed while the plan is '
            f'{plan.get_status_display().lower()}.')

    # Each movement releases only as much reservation as THIS line is holding.
    # Without the bound, InventoryService clamps against the item's global
    # reserved figure, so consuming more than this order reserved would silently
    # cancel another order's reservation -- and leave that order unable to
    # release what it still believed it held.
    held = locked.outstanding_reservation
    if used:
        backed = max(Decimal('0'), min(used, held))
        InventoryService.consume(
            locked.item, used, reserved_backed=backed, user=user, order=plan.order,
            garment_job=locked.garment_job, stage_key=stage_key,
            from_location=from_location,
            remarks=f'Consumed on {plan.order.order_id}')
        locked.consumed_quantity += used
        held -= backed
    if wasted:
        backed = max(Decimal('0'), min(wasted, held))
        InventoryService.waste(
            locked.item, wasted, reserved_backed=backed, user=user, order=plan.order,
            garment_job=locked.garment_job, stage_key=stage_key,
            from_location=from_location,
            remarks=f'Waste on {plan.order.order_id}')
        locked.wasted_quantity += wasted

    locked.save(update_fields=['consumed_quantity', 'wasted_quantity'])

    if plan.status == OrderMaterialPlan.Status.RESERVED:
        plan.status = OrderMaterialPlan.Status.IN_PRODUCTION
        plan.save(update_fields=['status', 'updated_at'])
    return locked


# --- 8. give back what was not used ---------------------------------------

@transaction.atomic
def release_unused(plan, *, user=None, stage_key=None):
    """Release every reservation this plan is still holding but no longer needs.

    Called when production is finished. Whatever was reserved and neither
    consumed nor wasted goes back to being available for other orders -- which
    is the difference between a reservation and a write-off.
    """
    locked = OrderMaterialPlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status == OrderMaterialPlan.Status.CANCELLED:
        raise MaterialPlanError('A cancelled plan has already released everything.')
    released = []
    for line in locked.lines.select_related('item'):
        if line.is_customer_supplied or line.item is None:
            continue
        outstanding = line.outstanding_reservation
        if outstanding <= 0:
            continue
        InventoryService.release(
            line.item, outstanding, user=user, order=locked.order,
            garment_job=line.garment_job, stage_key=stage_key,
            remarks=f'Unused reservation returned from {locked.order.order_id}')
        line.returned_quantity += outstanding
        line.save(update_fields=['returned_quantity'])
        released.append({'material': line.material_name, 'quantity': outstanding})
    return released


# --- 9. packaging, at dispatch --------------------------------------------

@transaction.atomic
def deduct_packaging(plan, *, user=None, from_location=None, stage_key=None):
    """Consume the packaging and labelling when the order goes out.

    Separate from production consumption because it happens at a different
    moment: a box is used when the garment is dispatched, not while it is being
    stitched. Recorded once -- a second dispatch does not consume a second box.
    """
    locked = OrderMaterialPlan.objects.select_for_update().get(pk=plan.pk)
    # Without this, a cancelled or completed plan could still consume a box --
    # and a cancelled plan has already given its reservation back, so the
    # consumption would come out of another order's.
    if locked.status not in (OrderMaterialPlan.Status.RESERVED,
                             OrderMaterialPlan.Status.IN_PRODUCTION):
        raise MaterialPlanError(
            f'Packaging cannot be deducted while the plan is '
            f'{locked.get_status_display().lower()}.')
    if locked.packaging_deducted_at is not None:
        raise MaterialPlanError(
            f'Packaging for {locked.order.order_id} was already deducted on '
            f'{locked.packaging_deducted_at:%Y-%m-%d}.')

    deducted = []
    for line in locked.lines.select_related('item').filter(role__in=DISPATCH_ROLES):
        if line.is_customer_supplied or line.item is None:
            continue
        # Anything already returned is not taken again, and the reservation
        # released is bounded by what this line actually holds.
        outstanding = (line.required_quantity - line.consumed_quantity
                       - line.wasted_quantity - line.returned_quantity)
        if outstanding <= 0:
            continue
        backed = max(Decimal('0'), min(outstanding, line.outstanding_reservation))
        InventoryService.consume(
            line.item, outstanding, reserved_backed=backed, user=user, order=locked.order,
            garment_job=line.garment_job, stage_key=stage_key,
            from_location=from_location,
            remarks=f'Packaging for {locked.order.order_id}')
        line.consumed_quantity += outstanding
        line.save(update_fields=['consumed_quantity'])
        deducted.append({'material': line.material_name, 'quantity': outstanding})

    locked.packaging_deducted_at = timezone.now()
    locked.save(update_fields=['packaging_deducted_at', 'updated_at'])
    return deducted


# --- the workflow's side of it --------------------------------------------

LIVE_STATUSES = (OrderMaterialPlan.Status.DRAFT,
                 OrderMaterialPlan.Status.RESERVED,
                 OrderMaterialPlan.Status.IN_PRODUCTION)


def live_plan(order):
    """This order's open material plan, or None."""
    return OrderMaterialPlan.objects.filter(order=order, status__in=LIVE_STATUSES).first()


@transaction.atomic
def ensure_plan(order, *, user=None):
    """The order's live plan, built from its garment jobs if it has none.

    Idempotent, because two things want to be sure a plan exists: the wizard,
    as soon as it has written the garments, and the workflow, when production
    reaches the stage that needs material. Whichever gets there first does the
    work and the other finds it already done.
    """
    existing = live_plan(order)
    if existing is not None:
        return existing, []
    return plan_from_garment_jobs(order, user=user)


@transaction.atomic
def sync_order_materials(order, stage_key, new_status, *, user=None):
    """Move this order's materials to match where production has reached.

    The join the product was missing. Materials were chosen on the order form
    and then nothing ever reserved, issued or consumed them, so an order could
    be delivered with the store room's figures untouched.

    Three moments, chosen because they are the ones that mean something to a
    boutique rather than because they are convenient:

      fabric confirmed     the cloth is committed to this order  -> reserve
      stitching completed  the cloth is now in the garment       -> consume
      delivered            nothing more will be taken            -> release,
                                                                    then close

    Returns a report, or None when this stage does not move materials. Never
    raises for a shortfall: a boutique routinely takes an order for cloth it has
    not bought yet, and refusing the transition would stop the work rather than
    the mistake. What it cannot fulfil it reports.
    """
    if new_status != 'COMPLETED':
        return None
    if stage_key not in ('fabric_confirmed', 'stitching_completed', 'delivered'):
        return None

    if stage_key == 'fabric_confirmed':
        plan, skipped = ensure_plan(order, user=user)
        if plan is None:
            return {'stage': stage_key, 'planned': 0, 'skipped': skipped}
        result = reserve(plan, user=user, allow_partial=True, stage_key=stage_key)
        return {'stage': stage_key, 'plan': str(plan.id),
                'reserved': result['reserved'], 'shortfalls': result['shortfalls'],
                'skipped': skipped}

    plan = live_plan(order)

    if stage_key == 'stitching_completed':
        # Fabric Confirmed can be skipped -- every stage has a Skip button --
        # and an order that skipped it would otherwise reach Delivered having
        # moved no stock at all, which is the exact failure this whole change
        # exists to end. Plan and reserve here if nobody has yet, so material is
        # accounted for however production was driven.
        if plan is None:
            plan, _ = ensure_plan(order, user=user)
            if plan is None:
                return None
            reserve(plan, user=user, allow_partial=True, stage_key=stage_key)
    if plan is None:
        return None

    if stage_key == 'stitching_completed':
        consumed, short = [], []
        for line in plan.lines.select_related('item', 'garment_job'):
            if line.is_customer_supplied or line.item is None:
                continue
            outstanding = (line.required_quantity - line.consumed_quantity
                           - line.wasted_quantity - line.returned_quantity)
            if outstanding <= 0:
                continue
            line.item.refresh_from_db(fields=['current_stock', 'reserved_stock'])
            # Consume what is physically there. Over-consuming is impossible --
            # the ledger refuses to drive stock negative -- and refusing the
            # whole transition would block a tailor reporting work that has
            # already happened. The gap is reported instead of hidden.
            #
            # ponytail: consumes the planned quantity. Staff can correct the
            # actual and record waste through the plan's consume endpoint; wire
            # a per-line entry into the stitching screen when the floor asks
            # for it.
            usable = min(outstanding, line.item.current_stock)
            if usable <= 0:
                short.append({'material': line.material_name,
                              'still_needed': outstanding, 'unit': line.unit})
                continue
            confirm_consumption(line, usable, user=user, stage_key=stage_key)
            consumed.append({'material': line.material_name, 'quantity': usable,
                             'unit': line.unit,
                             'garment': (line.garment_job.template.name
                                         if line.garment_job and line.garment_job.template_id
                                         else None)})
            if usable < outstanding:
                short.append({'material': line.material_name,
                              'still_needed': outstanding - usable, 'unit': line.unit})
        return {'stage': stage_key, 'plan': str(plan.id),
                'consumed': consumed, 'shortfalls': short}

    # delivered
    released = release_unused(plan, user=user, stage_key=stage_key)
    report = reconcile(plan)
    plan.status = OrderMaterialPlan.Status.COMPLETED
    plan.save(update_fields=['status', 'updated_at'])
    return {'stage': stage_key, 'plan': str(plan.id),
            'released': released, 'reconciliation': report}


# --- 10. reconcile before closing ------------------------------------------

def reconcile(plan):
    """Whether this order's materials add up, and what is unresolved if not.

    An order should not close holding reservations nobody will ever consume:
    that stock is invisible to every other order for as long as the plan stays
    open. This reports rather than decides, so the caller can show the operator
    what is outstanding.
    """
    outstanding, unplanned = [], []
    for line in plan.lines.select_related('item'):
        if line.is_customer_supplied:
            continue
        if line.outstanding_reservation > 0:
            outstanding.append({
                'material': line.material_name,
                'still_reserved': line.outstanding_reservation,
                'unit': line.unit,
            })
        if line.item is None:
            unplanned.append({'material': line.material_name})

    customer_open = [
        {
            'material': material.name,
            'remaining': material.remaining_quantity,
            'unit': material.unit,
        }
        for material in CustomerMaterial.objects.filter(order=plan.order)
        if material.remaining_quantity > 0
    ]

    return {
        'plan': str(plan.id),
        'order': plan.order.order_id,
        'is_reconciled': not outstanding and not unplanned,
        'outstanding_reservations': outstanding,
        'unlinked_materials': unplanned,
        'customer_material_to_return': customer_open,
    }


@transaction.atomic
def close(plan, *, user=None, release_outstanding=True):
    """Finish the plan. Releases anything still reserved unless told not to."""
    locked = OrderMaterialPlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status == OrderMaterialPlan.Status.COMPLETED:
        raise MaterialPlanError('This plan is already closed.')
    if locked.status == OrderMaterialPlan.Status.CANCELLED:
        raise MaterialPlanError('A cancelled plan cannot be closed.')

    if release_outstanding:
        release_unused(locked, user=user)
    else:
        report = reconcile(locked)
        if not report['is_reconciled']:
            raise MaterialPlanError(
                'The plan still holds reservations. Release them or pass '
                'release_outstanding.')

    locked.status = OrderMaterialPlan.Status.COMPLETED
    locked.save(update_fields=['status', 'updated_at'])
    return locked


@transaction.atomic
def cancel(plan, *, user=None):
    """Abandon the plan, giving every reservation back."""
    locked = OrderMaterialPlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status in (OrderMaterialPlan.Status.COMPLETED,
                         OrderMaterialPlan.Status.CANCELLED):
        raise MaterialPlanError(
            f'A plan that is {locked.get_status_display().lower()} cannot be cancelled.')
    # Released before the status flips: release_unused refuses a cancelled plan,
    # on the grounds that one has already given everything back.
    release_unused(locked, user=user)
    locked.status = OrderMaterialPlan.Status.CANCELLED
    locked.save(update_fields=['status', 'updated_at'])
    return locked


# --- the customer's own materials ------------------------------------------

@transaction.atomic
def receive_customer_material(order, *, name, quantity, unit, kind=None,
                              user=None, description=None, notes=None):
    """Take delivery of something the customer brought.

    Deliberately never touches InventoryItem. The customer's silk is not the
    boutique's to reserve against another order, to value as an asset, or to
    reorder when it runs low.
    """
    quantity = _quantity(quantity, 'quantity')
    if quantity <= 0:
        raise MaterialPlanError('Received quantity must be greater than zero.')

    material = CustomerMaterial.objects.create(
        order=order, name=name, unit=unit,
        kind=kind or CustomerMaterial.Kind.FABRIC,
        description=description, notes=notes, received_quantity=quantity,
    )
    _log_customer_movement(
        material, CustomerMaterialMovement.Type.RECEIVED, quantity,
        previous=Decimal('0'), user=user)
    return material


@transaction.atomic
def record_customer_material(material, movement_type, quantity, *, user=None, remarks=''):
    """Use, return or write off part of a customer's material."""
    quantity = _quantity(quantity)
    if quantity <= 0:
        raise MaterialPlanError('Quantity must be greater than zero.')

    locked = CustomerMaterial.objects.select_for_update().get(pk=material.pk)
    remaining = locked.remaining_quantity
    if quantity > remaining:
        raise MaterialPlanError(
            f"Only {remaining} {locked.get_unit_display()} of '{locked.name}' is left; "
            f"cannot account for {quantity}."
        )

    field = {
        CustomerMaterialMovement.Type.USED: 'used_quantity',
        CustomerMaterialMovement.Type.RETURNED: 'returned_quantity',
        CustomerMaterialMovement.Type.DAMAGED: 'damaged_quantity',
    }.get(movement_type)
    if field is None:
        raise MaterialPlanError(f'{movement_type} is not something that can be recorded.')

    setattr(locked, field, getattr(locked, field) + quantity)
    locked.save(update_fields=[field])
    _log_customer_movement(locked, movement_type, quantity,
                           previous=remaining, user=user, remarks=remarks)
    return locked


def _log_customer_movement(material, movement_type, quantity, *, previous,
                           user=None, remarks=''):
    return CustomerMaterialMovement.objects.create(
        material=material,
        movement_type=movement_type,
        quantity=quantity,
        previous_remaining=previous,
        new_remaining=material.remaining_quantity,
        user=user if (user and user.is_authenticated) else None,
        user_name_snapshot=(
            (user.get_full_name() or user.username)
            if (user and user.is_authenticated) else 'System'),
        remarks=remarks,
    )
