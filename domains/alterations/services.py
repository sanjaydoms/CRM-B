"""Everything that changes an alteration.

Views call these; they never write the models directly. Each function is
atomic, validates the move, checks the role, writes the audit row and fires
whatever notification belongs to that step.

WHAT THIS MODULE MUST NEVER DO -- the whole reason the feature exists:

  * save() an Order, or touch order_status / production_status /
    current_stage_key / any price / amount_paid / payment_status
  * save() an OrderStage, OrderStageHistory or GarmentJob
  * create or modify a ProductionTask or QCRecord
  * write a StockMovement that carries `order` or `garment_job`

A delivered order is history. apps/alterations/test_regression.py asserts all
of the above after a full alteration lifecycle.
"""

import logging
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.alterations.models import (
    AlterationActivity,
    AlterationMaterialLine,
    AlterationPayment,
    AlterationRequest,
    AlterationStatus,
    AlterationTask,
    AlterationTaskStatus,
    AlterationType,
    PaymentMethod,
    PaymentStatus,
)
from apps.catalog.models import GarmentJob
from apps.inventory.models import InventoryItem
from apps.inventory.services import InventoryService
from crm_api.models import Customer, Order, Tailor
from domains.alterations import notifications
from domains.alterations.workflow import (
    COUNTER_ROLES,
    MATERIAL_ROLES,
    PAYMENT_ROLES,
    QC_ROLES,
    TransitionError,
    check_permission,
    check_role,
    validate_transition,
)

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')

#: Order status an alteration can be raised against. A garment cannot come
#: back before it has gone out.
DELIVERED = 'Delivered'

#: Window in which an identical repeat submission is treated as a double-click
#: rather than a second genuine transaction.
DUPLICATE_WINDOW = timedelta(seconds=10)

DEFAULT_STAGE_KEY = 'alteration_work'


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _money(value, field):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{field} must be a number.')
    return amount.quantize(Decimal('0.01'))


def _quantity(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Quantity must be a number.')


def _actor(user):
    """The User to attribute an action to, or None for anonymous/system."""
    return user if (user is not None and getattr(user, 'is_authenticated', False)) else None


def _actor_name(user):
    actor = _actor(user)
    if actor is None:
        return 'System'
    return actor.get_full_name() or actor.username


def _log(alteration, event_type, *, performed_by=None, from_status='', to_status='',
         **metadata):
    return AlterationActivity.objects.create(
        alteration_request=alteration,
        event_type=event_type,
        performed_by=_actor(performed_by),
        performed_by_name=_actor_name(performed_by),
        from_status=from_status or '',
        to_status=to_status or '',
        metadata=metadata,
    )


def _locked(alteration_request_id):
    """Load an alteration for update.

    select_for_update on every transition: two people tapping "Send to QC" on
    the same garment from the shop floor and the counter is an ordinary event,
    and without the row lock both would pass validation against the same stale
    status.
    """
    return AlterationRequest.objects.select_for_update().get(pk=alteration_request_id)


def _generate_alteration_number(order):
    """ALT-<order id>-<n>, unique across the boutique.

    The count can race, so the caller retries on IntegrityError; the second
    attempt falls back to a random suffix rather than counting again.
    """
    existing = AlterationRequest.objects.filter(original_order=order).count()
    return f"ALT-{order.order_id}-{existing + 1}"


def _fallback_alteration_number(order):
    return f"ALT-{order.order_id}-{uuid.uuid4().hex[:6].upper()}"


def calculate_outstanding_balance(alteration):
    """What the customer still owes on this alteration.

    A free / boutique-fault alteration owes nothing by definition, whatever
    happens to be sitting in charge_amount.
    """
    if alteration.alteration_type == AlterationType.FREE_BOUTIQUE_FAULT:
        return ZERO
    return max(ZERO, (alteration.charge_amount or ZERO) - (alteration.amount_paid or ZERO))


def _resolve_order(order_id):
    """Accept either the numeric pk or the human order_id ('T2B-...')."""
    if isinstance(order_id, int) or (isinstance(order_id, str) and str(order_id).isdigit()):
        order = Order.objects.filter(pk=int(order_id)).first()
        if order is not None:
            return order
    order = Order.objects.filter(order_id=order_id).first()
    if order is None:
        raise ValueError('That order could not be found.')
    return order


# --------------------------------------------------------------------------
# intake
# --------------------------------------------------------------------------

@transaction.atomic
def create_alteration_request(*, customer_id, order_id, garment_job_id,
                              alteration_type=AlterationType.PAID_CLIENT_REQUEST,
                              issue_description='', requested_adjustments=None,
                              charge_amount=ZERO, notes='', performed_by=None, role=None):
    """Take a delivered garment back in.

    Every one of these checks is repeated server-side on purpose: the browser
    decides which buttons to draw, it does not decide what is legal.
    """
    check_role(role, COUNTER_ROLES, what='creating an alteration')

    customer = Customer.objects.filter(pk=customer_id).first()
    if customer is None:
        raise ValueError('That customer could not be found.')

    order = _resolve_order(order_id)

    if order.customer_id != customer.id:
        raise ValueError('That order does not belong to the selected customer.')

    # The core rule. An alteration is a POST-delivery process; anything still
    # in production is handled by the production workflow, not by this one.
    if order.order_status != DELIVERED:
        raise ValueError(
            f"Alterations can only be raised against a Delivered order. "
            f"Order {order.order_id} is currently '{order.order_status}'."
        )

    garment_job = GarmentJob.objects.filter(pk=garment_job_id).first()
    if garment_job is None:
        raise ValueError('That garment could not be found.')
    if garment_job.order_id != order.id:
        raise ValueError('That garment does not belong to the selected order.')

    if alteration_type not in AlterationType.values:
        raise ValueError(f"'{alteration_type}' is not a valid alteration type.")

    charge = _money(charge_amount or ZERO, 'Charge amount')
    if charge < ZERO:
        raise ValueError('Charge amount cannot be negative.')
    if alteration_type == AlterationType.FREE_BOUTIQUE_FAULT and charge > ZERO:
        raise ValueError('A free / boutique-fault alteration cannot carry a charge.')

    if requested_adjustments is not None and not isinstance(requested_adjustments, dict):
        raise ValueError('Requested adjustments must be an object.')

    for attempt in (1, 2):
        number = (_generate_alteration_number(order) if attempt == 1
                  else _fallback_alteration_number(order))
        try:
            with transaction.atomic():
                alteration = AlterationRequest.objects.create(
                    alteration_number=number,
                    customer=customer,
                    original_order=order,
                    garment_job=garment_job,
                    alteration_type=alteration_type,
                    issue_description=issue_description or '',
                    requested_adjustments=requested_adjustments or {},
                    status=AlterationStatus.RECEIVED,
                    charge_amount=charge,
                    amount_paid=ZERO,
                    notes=notes or '',
                    received_at=timezone.now(),
                )
            break
        except IntegrityError:
            if attempt == 2:
                raise
    else:  # pragma: no cover - the loop always breaks or raises
        raise IntegrityError('Could not allocate an alteration number.')

    _log(alteration, 'ALTERATION_CREATED', performed_by=performed_by,
         to_status=AlterationStatus.RECEIVED,
         alteration_type=alteration_type,
         issue_description=issue_description or '',
         charge_amount=str(charge),
         order_id=order.order_id,
         garment=str(garment_job))

    _safe_notify(notifications.alteration_received, alteration)
    return alteration


def _safe_notify(fn, *args):
    """Notifications never fail a transition."""
    try:
        fn(*args)
    except Exception:  # noqa: BLE001
        logger.exception('alteration notification %s failed', getattr(fn, '__name__', fn))


# --------------------------------------------------------------------------
# workflow
# --------------------------------------------------------------------------

def _transition(alteration_request_id, target, *, event_type, performed_by, role,
                tailor_id=None, metadata=None, mutate=None, permission=None,
                require_status=None):
    """The shared body of every transition.

    `permission` overrides the default role gate for the one case that needs
    it -- QC failure, which lands on IN_PROGRESS but is a QC action, not bench
    work. `require_status` pins the source state where the transition table
    alone would be too generous.
    """
    alteration = _locked(alteration_request_id)
    previous = alteration.status

    if permission is not None:
        permission(role)
    else:
        check_permission(target, role=role, alteration=alteration, tailor_id=tailor_id)

    if require_status is not None and previous != require_status:
        raise TransitionError(
            f"This action needs the alteration to be in '{require_status}'; "
            f"it is currently '{previous}'."
        )
    validate_transition(previous, target)

    if mutate is not None:
        mutate(alteration)

    alteration.status = target
    alteration.save()

    resolved = metadata(alteration) if callable(metadata) else (metadata or {})
    _log(alteration, event_type, performed_by=performed_by,
         from_status=previous, to_status=target, **resolved)
    return alteration


@transaction.atomic
def start_inspection(alteration_request_id, *, performed_by=None, role=None, notes=None):
    return _transition(
        alteration_request_id, AlterationStatus.INSPECTION,
        event_type='INSPECTION_STARTED', performed_by=performed_by, role=role,
        metadata={'notes': notes or ''},
    )


@transaction.atomic
def record_inspection(alteration_request_id, *, inspection_notes='', adjustments=None,
                      performed_by=None, role=None):
    """Write down what the inspection found, without moving the status.

    Kept separate from the transition so the findings can be edited while the
    garment is still on the inspection table.
    """
    alteration = _locked(alteration_request_id)
    check_role(role, COUNTER_ROLES, what='recording an inspection')

    if alteration.status != AlterationStatus.INSPECTION:
        raise TransitionError(
            f"Inspection findings can only be recorded while the alteration is "
            f"in Inspection; this one is '{alteration.status}'."
        )
    if adjustments is not None and not isinstance(adjustments, dict):
        raise ValueError('Inspection adjustments must be an object.')

    alteration.inspection_notes = inspection_notes or ''
    if adjustments is not None:
        alteration.inspection_adjustments = adjustments
    alteration.save(update_fields=['inspection_notes', 'inspection_adjustments', 'updated_at'])

    _log(alteration, 'INSPECTION_RECORDED', performed_by=performed_by,
         from_status=alteration.status, to_status=alteration.status,
         notes=inspection_notes or '', adjustments=alteration.inspection_adjustments)
    return alteration


@transaction.atomic
def submit_for_approval(alteration_request_id, *, charge_amount=None, notes=None,
                        performed_by=None, role=None):
    """Quote the job and put it in front of whoever approves it."""

    def mutate(alteration):
        if charge_amount is not None:
            charge = _money(charge_amount, 'Charge amount')
            if charge < ZERO:
                raise ValueError('Charge amount cannot be negative.')
            if alteration.alteration_type == AlterationType.FREE_BOUTIQUE_FAULT and charge > ZERO:
                raise ValueError('A free / boutique-fault alteration cannot carry a charge.')
            if charge < alteration.amount_paid:
                raise ValueError(
                    f'The charge cannot be reduced below the {alteration.amount_paid} '
                    f'already paid.'
                )
            alteration.charge_amount = charge

    alteration = _transition(
        alteration_request_id, AlterationStatus.PENDING_APPROVAL,
        event_type='SUBMITTED_FOR_APPROVAL', performed_by=performed_by, role=role,
        mutate=mutate,
        metadata=lambda alt: {'charge_amount': str(alt.charge_amount),
                              'notes': notes or ''},
    )
    _safe_notify(notifications.estimate_ready, alteration)
    return alteration


@transaction.atomic
def approve_alteration(alteration_request_id, *, performed_by=None, role=None, notes=None):
    alteration = _transition(
        alteration_request_id, AlterationStatus.APPROVED,
        event_type='ALTERATION_APPROVED', performed_by=performed_by, role=role,
        metadata=lambda alt: {'notes': notes or '',
                              'charge_amount': str(alt.charge_amount)},
    )
    _safe_notify(notifications.alteration_approved, alteration)
    return alteration


@transaction.atomic
def assign_alteration(alteration_request_id, *, tailor_id, title=None, stage_key=None,
                      notes=None, performed_by=None, role=None):
    """Hand the work to a member of the existing tailor roster."""
    if not tailor_id:
        raise ValueError('A tailor must be chosen.')

    tailor = Tailor.objects.filter(pk=tailor_id).first()
    if tailor is None:
        raise ValueError('That staff member could not be found.')

    stage = (stage_key or DEFAULT_STAGE_KEY).strip() or DEFAULT_STAGE_KEY
    label = (title or 'Alteration work').strip() or 'Alteration work'

    alteration = _transition(
        alteration_request_id, AlterationStatus.ASSIGNED,
        event_type='ALTERATION_ASSIGNED', performed_by=performed_by, role=role,
        metadata={'tailor_id': str(tailor.id), 'tailor_name': tailor.name,
                  'notes': notes or ''},
    )

    task, created = AlterationTask.objects.get_or_create(
        alteration_request=alteration,
        stage_key=stage,
        defaults={
            'title': label,
            'assigned_to': tailor,
            'status': AlterationTaskStatus.PENDING,
            'notes': notes or '',
        },
    )
    if not created:
        task.title = label
        task.assigned_to = tailor
        if notes:
            task.notes = notes
        task.save(update_fields=['title', 'assigned_to', 'notes', 'updated_at'])

    _safe_notify(notifications.alteration_assigned, alteration, tailor)
    return alteration


@transaction.atomic
def start_alteration_work(alteration_request_id, *, task_id=None, performed_by=None,
                          role=None, tailor_id=None, notes=None):
    alteration = _transition(
        alteration_request_id, AlterationStatus.IN_PROGRESS,
        event_type='WORK_STARTED', performed_by=performed_by, role=role,
        tailor_id=tailor_id, metadata={'notes': notes or ''},
    )

    tasks = alteration.tasks.all()
    task = (tasks.filter(pk=task_id).first() if task_id else tasks.first())
    if task is not None:
        task.status = AlterationTaskStatus.IN_PROGRESS
        if task.started_at is None:
            task.started_at = timezone.now()
        task.completed_at = None
        task.save(update_fields=['status', 'started_at', 'completed_at', 'updated_at'])

    _safe_notify(notifications.work_started, alteration)
    return alteration


@transaction.atomic
def send_to_qc(alteration_request_id, *, task_id=None, performed_by=None, role=None,
               tailor_id=None, notes=None):
    alteration = _transition(
        alteration_request_id, AlterationStatus.QC,
        event_type='SENT_TO_QC', performed_by=performed_by, role=role,
        tailor_id=tailor_id, metadata={'notes': notes or ''},
    )

    tasks = alteration.tasks.all()
    task = (tasks.filter(pk=task_id).first() if task_id else tasks.first())
    if task is not None:
        task.status = AlterationTaskStatus.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'completed_at', 'updated_at'])

    _safe_notify(notifications.sent_to_qc, alteration)
    return alteration


@transaction.atomic
def pass_quality_check(alteration_request_id, *, performed_by=None, role=None, notes=None):
    alteration = _transition(
        alteration_request_id, AlterationStatus.READY_FOR_PICKUP,
        event_type='QC_PASSED', performed_by=performed_by, role=role,
        metadata={'notes': notes or ''},
    )
    alteration.tasks.exclude(status=AlterationTaskStatus.CANCELLED).update(
        status=AlterationTaskStatus.COMPLETED, completed_at=timezone.now(),
    )
    _safe_notify(notifications.ready_for_pickup, alteration)
    return alteration


@transaction.atomic
def fail_quality_check(alteration_request_id, *, reason, performed_by=None, role=None):
    """Send it back to the bench. IN_PROGRESS *is* the rework state."""
    if not reason or not str(reason).strip():
        raise ValueError('A reason is required when a quality check fails.')

    alteration = _transition(
        alteration_request_id, AlterationStatus.IN_PROGRESS,
        event_type='QC_FAILED', performed_by=performed_by, role=role,
        # A QC sign-off, not bench work: gated on QC_ROLES rather than on
        # whoever the garment happens to be assigned to.
        permission=lambda r: check_role(r, QC_ROLES, what='failing a quality check'),
        require_status=AlterationStatus.QC,
        metadata={'reason': str(reason).strip()},
    )
    alteration.tasks.exclude(status=AlterationTaskStatus.CANCELLED).update(
        status=AlterationTaskStatus.IN_PROGRESS, completed_at=None,
    )
    return alteration


@transaction.atomic
def complete_alteration(alteration_request_id, *, performed_by=None, role=None, notes=None):
    """Hand the garment back.

    Enforced here, not in the browser: a chargeable alteration with money
    still owing cannot be closed.
    """

    def mutate(alteration):
        outstanding = calculate_outstanding_balance(alteration)
        if outstanding > ZERO:
            raise ValueError(
                f'This alteration still has an outstanding balance of {outstanding}. '
                f'Record the payment before completing it.'
            )
        alteration.completed_at = timezone.now()

    alteration = _transition(
        alteration_request_id, AlterationStatus.COMPLETED,
        event_type='ALTERATION_COMPLETED', performed_by=performed_by, role=role,
        mutate=mutate, metadata={'notes': notes or ''},
    )
    alteration.tasks.exclude(status=AlterationTaskStatus.CANCELLED).update(
        status=AlterationTaskStatus.COMPLETED, completed_at=timezone.now(),
    )
    _safe_notify(notifications.alteration_completed, alteration)
    return alteration


@transaction.atomic
def cancel_alteration(alteration_request_id, *, reason, performed_by=None, role=None):
    if not reason or not str(reason).strip():
        raise ValueError('A cancellation reason is required.')

    def mutate(alteration):
        alteration.cancelled_at = timezone.now()

    alteration = _transition(
        alteration_request_id, AlterationStatus.CANCELLED,
        event_type='ALTERATION_CANCELLED', performed_by=performed_by, role=role,
        mutate=mutate, metadata={'reason': str(reason).strip()},
    )
    alteration.tasks.update(status=AlterationTaskStatus.CANCELLED)
    _safe_notify(notifications.alteration_cancelled, alteration, str(reason).strip())
    return alteration


# --------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------

@transaction.atomic
def record_alteration_payment(alteration_request_id, *, amount,
                              payment_method=PaymentMethod.CASH,
                              transaction_reference='', received_by=None, role=None,
                              notes=None):
    """Take money against an alteration and nothing else.

    Order.amount_paid, Order.payment_status and Order.total_amount are not
    touched: this is a separate sale, months after the order was closed.
    """
    check_role(role, PAYMENT_ROLES, what='recording a payment')

    alteration = _locked(alteration_request_id)

    if alteration.status == AlterationStatus.CANCELLED:
        raise ValueError('A cancelled alteration cannot take a payment.')
    if alteration.status == AlterationStatus.COMPLETED:
        raise ValueError('A completed alteration cannot take a further payment.')

    if alteration.alteration_type == AlterationType.FREE_BOUTIQUE_FAULT:
        raise ValueError('A free / boutique-fault alteration is not chargeable.')
    if (alteration.charge_amount or ZERO) <= ZERO:
        raise ValueError('No charge has been set on this alteration yet.')

    amount = _money(amount, 'Payment amount')
    if amount <= ZERO:
        raise ValueError('The payment amount must be greater than zero.')

    if payment_method not in PaymentMethod.values:
        raise ValueError(f"'{payment_method}' is not a valid payment method.")

    outstanding = calculate_outstanding_balance(alteration)
    if amount > outstanding:
        raise ValueError(
            f'That payment of {amount} is more than the {outstanding} outstanding.'
        )

    reference = (transaction_reference or '').strip()
    if not reference:
        # No reference to key on, so fall back to "the same amount, the same
        # way, a moment ago" -- a double-tap, not a second payment.
        recent = AlterationPayment.objects.filter(
            alteration_request=alteration,
            amount=amount,
            payment_method=payment_method,
            status=PaymentStatus.COMPLETED,
            created_at__gte=timezone.now() - DUPLICATE_WINDOW,
        ).exists()
        if recent:
            raise ValueError(
                'An identical payment was just recorded. If this really is a '
                'second payment, add a transaction reference.'
            )

    try:
        with transaction.atomic():
            payment = AlterationPayment.objects.create(
                alteration_request=alteration,
                amount=amount,
                payment_method=payment_method,
                transaction_reference=reference,
                status=PaymentStatus.COMPLETED,
                received_by=_actor(received_by),
                received_by_name=_actor_name(received_by),
                received_at=timezone.now(),
                notes=notes or '',
            )
    except IntegrityError:
        # The unique constraint on (alteration, transaction_reference).
        raise ValueError(
            f"A payment with reference '{reference}' has already been recorded "
            f"for this alteration."
        )

    alteration.amount_paid = (alteration.amount_paid or ZERO) + amount
    alteration.save(update_fields=['amount_paid', 'updated_at'])

    _log(alteration, 'PAYMENT_RECEIVED', performed_by=received_by,
         from_status=alteration.status, to_status=alteration.status,
         amount=str(amount), payment_method=payment_method,
         transaction_reference=reference,
         outstanding_balance=str(calculate_outstanding_balance(alteration)))
    return payment


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

@transaction.atomic
def record_alteration_material_usage(alteration_request_id, *, item_id, quantity,
                                     unit=None, recorded_by=None, role=None, remarks=None):
    """Consume stock for an alteration through the existing inventory engine.

    The StockMovement is written with NO `order` and NO `garment_job`. That is
    deliberate: the delivered order's material consumption history is closed,
    and a report that sums an order's movements must not start including
    fabric used months later. The link runs the other way -- this line points
    at its movement -- and the movement's remark names the alteration.
    """
    check_role(role, MATERIAL_ROLES, what='recording material usage')

    alteration = _locked(alteration_request_id)

    if alteration.status == AlterationStatus.CANCELLED:
        raise ValueError('A cancelled alteration cannot consume materials.')
    if alteration.status == AlterationStatus.COMPLETED:
        raise ValueError('A completed alteration cannot consume materials.')

    quantity = _quantity(quantity)
    if quantity <= Decimal('0'):
        raise ValueError('The quantity must be greater than zero.')

    item = InventoryItem.objects.filter(pk=item_id).first()
    if item is None:
        raise ValueError('That inventory item could not be found.')

    if item.available_stock < quantity:
        raise ValueError(
            f"There is not enough '{item.name}' in stock -- "
            f"{item.available_stock} {item.get_unit_display()} available, "
            f"{quantity} requested."
        )

    recent = AlterationMaterialLine.objects.filter(
        alteration_request=alteration,
        item=item,
        quantity=quantity,
        created_at__gte=timezone.now() - DUPLICATE_WINDOW,
    ).exists()
    if recent:
        raise ValueError('That material was just recorded against this alteration.')

    movement = InventoryService.consume(
        item=item,
        quantity=quantity,
        user=_actor(recorded_by),
        stage_key=DEFAULT_STAGE_KEY,
        remarks=(f"Alteration {alteration.alteration_number}"
                 f"{': ' + remarks.strip() if remarks and remarks.strip() else ''}"),
    )

    line = AlterationMaterialLine.objects.create(
        alteration_request=alteration,
        item=item,
        material_name=item.name,
        quantity=quantity,
        unit=(unit or item.unit or 'PIECE'),
        stock_movement=movement,
        recorded_by=_actor(recorded_by),
        recorded_by_name=_actor_name(recorded_by),
        remarks=remarks or '',
    )

    _log(alteration, 'MATERIAL_CONSUMED', performed_by=recorded_by,
         from_status=alteration.status, to_status=alteration.status,
         item_id=str(item.id), material_name=item.name,
         quantity=str(quantity), unit=line.unit,
         stock_movement_id=str(movement.id))
    return line
