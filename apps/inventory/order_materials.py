
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from . import bom as bom_service
from .models import (
    BomLine, Category, CustomerMaterial, CustomerMaterialMovement,
    OrderMaterialLine, OrderMaterialPlan,
)
from .services import InventoryService

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

DISPATCH_ROLES = frozenset({BomLine.Role.PACKAGING, BomLine.Role.LABEL})


class MaterialPlanError(ValueError):



def _still_to_reserve(line):
    unmet = line.required_quantity - line.consumed_quantity - line.wasted_quantity
    return max(Decimal('0'), unmet - line.outstanding_reservation)


PRECISION = Decimal('0.001')


def _quantity(value, field='quantity'):
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



@transaction.atomic
def plan_materials(order, bom, variables=None, *, user=None, include_optional=False):
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



def check_availability(plan):
    shortfalls = []
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



@transaction.atomic
def reserve(plan, *, user=None, allow_partial=False, stage_key=None):
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



@transaction.atomic
def confirm_consumption(line, used, *, wasted=0, user=None, from_location=None,
                        stage_key=None):
    used = _quantity(used, 'used')
    wasted = _quantity(wasted, 'wasted')
    if used == 0 and wasted == 0:
        raise MaterialPlanError('Nothing to record: both used and wasted are zero.')

    locked = OrderMaterialLine.objects.select_for_update(of=('self',)).select_related(
        'item', 'plan').get(pk=line.pk)

    if locked.is_customer_supplied:
        raise MaterialPlanError(
            f"'{locked.material_name}' is customer-supplied. Record it against the "
            f"customer's own material, not boutique stock.")
    if locked.item is None:
        raise MaterialPlanError(
            f"'{locked.material_name}' is not linked to a stocked item.")

    plan = OrderMaterialPlan.objects.select_for_update().get(pk=locked.plan_id)
    if plan.status not in (OrderMaterialPlan.Status.RESERVED,
                           OrderMaterialPlan.Status.IN_PRODUCTION):
        raise MaterialPlanError(
            f'Materials cannot be consumed while the plan is '
            f'{plan.get_status_display().lower()}.')

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



@transaction.atomic
def release_unused(plan, *, user=None, stage_key=None):
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



@transaction.atomic
def deduct_packaging(plan, *, user=None, from_location=None, stage_key=None):
    locked = OrderMaterialPlan.objects.select_for_update().get(pk=plan.pk)
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



LIVE_STATUSES = (OrderMaterialPlan.Status.DRAFT,
                 OrderMaterialPlan.Status.RESERVED,
                 OrderMaterialPlan.Status.IN_PRODUCTION)


def live_plan(order):

    return OrderMaterialPlan.objects.filter(order=order, status__in=LIVE_STATUSES).first()


@transaction.atomic
def ensure_plan(order, *, user=None):
    existing = live_plan(order)
    if existing is not None:
        return existing, []
    return plan_from_garment_jobs(order, user=user)


@transaction.atomic
def sync_order_materials(order, stage_key, new_status, *, user=None):
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

    released = release_unused(plan, user=user, stage_key=stage_key)
    report = reconcile(plan)
    plan.status = OrderMaterialPlan.Status.COMPLETED
    plan.save(update_fields=['status', 'updated_at'])
    return {'stage': stage_key, 'plan': str(plan.id),
            'released': released, 'reconciliation': report}



def reconcile(plan):
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

    locked = OrderMaterialPlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status in (OrderMaterialPlan.Status.COMPLETED,
                         OrderMaterialPlan.Status.CANCELLED):
        raise MaterialPlanError(
            f'A plan that is {locked.get_status_display().lower()} cannot be cancelled.')
    release_unused(locked, user=user)
    locked.status = OrderMaterialPlan.Status.CANCELLED
    locked.save(update_fields=['status', 'updated_at'])
    return locked



@transaction.atomic
def receive_customer_material(order, *, name, quantity, unit, kind=None,
                              user=None, description=None, notes=None):
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
