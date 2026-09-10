"""The alteration state machine and who may drive it.

Two rules, kept apart on purpose:

  validate_transition -- is this move legal at all?
  check_permission    -- may THIS person make it?

Roles are the ones the product actually has: 'Owner' and 'Designer' from
core.roles, plus the nine strings in Tailor.ROLE_CHOICES. There is no
front-desk role in this product; counter work is the Owner's and the Master's,
so those two are the roles that take a garment in and hand it back.
"""

from apps.alterations.models import AlterationStatus, AlterationType
from core.roles import DESIGNER, OWNER


class TransitionError(ValueError):
    """An illegal move through the alteration lifecycle."""


#: RECEIVED -> INSPECTION -> PENDING_APPROVAL -> APPROVED -> ASSIGNED ->
#: IN_PROGRESS -> QC -> READY_FOR_PICKUP -> COMPLETED, with QC -> IN_PROGRESS
#: as the rework path and CANCELLED reachable from anything unfinished.
#:
#: Intentionally strict: no skipping inspection, and no route out of a
#: terminal state. A garment that was handed back cannot quietly re-enter the
#: workroom under the same alteration number; that is a new alteration.
ALLOWED_TRANSITIONS = {
    AlterationStatus.RECEIVED: {
        AlterationStatus.INSPECTION,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.INSPECTION: {
        AlterationStatus.PENDING_APPROVAL,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.PENDING_APPROVAL: {
        AlterationStatus.APPROVED,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.APPROVED: {
        AlterationStatus.ASSIGNED,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.ASSIGNED: {
        # Re-assignment before the work starts: the tailor it was given to has
        # gone home sick, and a supervisor hands it to someone else.
        AlterationStatus.ASSIGNED,
        AlterationStatus.IN_PROGRESS,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.IN_PROGRESS: {
        AlterationStatus.QC,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.QC: {
        AlterationStatus.READY_FOR_PICKUP,
        # QC failure. Returning to IN_PROGRESS *is* the rework state; there is
        # deliberately no separate "start rework" step to get wrong.
        AlterationStatus.IN_PROGRESS,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.READY_FOR_PICKUP: {
        AlterationStatus.COMPLETED,
        AlterationStatus.CANCELLED,
    },
    AlterationStatus.COMPLETED: set(),
    AlterationStatus.CANCELLED: set(),
}


#: Every production role, i.e. everyone who can hold a garment and work on it.
#: Mirrors Tailor.ROLE_CHOICES.
PRODUCTION_ROLES = frozenset({
    'Master', 'Tailor', 'Measurement Master', 'Pattern Master', 'Cutting Master',
    'Maggam Master', 'Finishing Master', 'Pressing Staff', 'QC Master',
})

#: Runs the floor. Mirrors core.permissions.SUPERVISOR_ROLES.
SUPERVISOR_ROLES = frozenset({'Master'})

#: The counter: taking a garment in, quoting it, approving it, taking the
#: money, handing it back, cancelling it. No front-desk role exists, so this
#: is the owner and the floor supervisor.
COUNTER_ROLES = frozenset({OWNER}) | SUPERVISOR_ROLES

#: Who may sign off a quality check. QC Master is a real role in this product.
QC_ROLES = COUNTER_ROLES | {'QC Master'}

#: Who may do the sewing. Any production role -- but a bench worker also has
#: to be the person the alteration is actually assigned to; see
#: `assigned_tailor_ids` below.
WORK_ROLES = frozenset({OWNER}) | PRODUCTION_ROLES


#: Roles permitted to move an alteration *into* each status.
ALLOWED_ROLES_PER_STATUS = {
    AlterationStatus.INSPECTION: COUNTER_ROLES,
    AlterationStatus.PENDING_APPROVAL: COUNTER_ROLES,
    AlterationStatus.APPROVED: COUNTER_ROLES,
    AlterationStatus.ASSIGNED: COUNTER_ROLES,
    AlterationStatus.IN_PROGRESS: WORK_ROLES,
    AlterationStatus.QC: WORK_ROLES,
    AlterationStatus.READY_FOR_PICKUP: QC_ROLES,
    AlterationStatus.COMPLETED: COUNTER_ROLES,
    AlterationStatus.CANCELLED: COUNTER_ROLES,
}

#: Recording money. The counter's job, like every other payment in the shop.
PAYMENT_ROLES = COUNTER_ROLES

#: Consuming stock. Owner only, and NOT because alterations are special:
#: inventory.InventoryItemViewSet is OwnerOnly, so the owner is already the
#: only role that can even see the item list. Letting anyone else consume
#: would be broadening inventory access through a side door.
MATERIAL_ROLES = frozenset({OWNER})


def validate_transition(current_status, new_status):
    """Raise TransitionError unless current_status -> new_status is legal."""
    if current_status not in ALLOWED_TRANSITIONS:
        raise TransitionError(f"Unknown alteration status '{current_status}'.")

    if new_status not in ALLOWED_TRANSITIONS[current_status]:
        raise TransitionError(
            f"Cannot move an alteration from '{current_status}' to '{new_status}'."
        )


def check_role(role, allowed, *, what):
    """Raise PermissionError unless `role` is in `allowed`.

    A missing role is a refusal, never a pass. `resolve_user_role` returns None
    for an authenticated account that no Tailor or Designer profile claims --
    the state a removed staff member's un-revoked token lands in -- and that
    account must not be able to touch a garment, a charge or the stock room.
    Designers are denied for the same reason core.permissions.RolePermission
    denies them: they never handle orders or money.
    """
    if not role or role == DESIGNER:
        raise PermissionError(f"Your role does not permit {what}.")
    if role == OWNER:
        return
    if role not in allowed:
        raise PermissionError(f"Role '{role}' is not permitted {what}.")


def check_permission(target_status, *, role, alteration=None, tailor_id=None):
    """Gate a transition into `target_status`.

    Beyond the role matrix there is one extra rule: a bench worker may only
    drive the alteration that is actually assigned to them. Without it any
    Pressing Staff account could start and finish anyone else's work.

    QC failure does not come through here -- `fail_quality_check` checks
    QC_ROLES directly -- so a QC Master gets no back door onto the bench.
    """
    allowed = ALLOWED_ROLES_PER_STATUS.get(target_status, frozenset())
    check_role(role, allowed, what=f"moving an alteration to {target_status}")

    if role in COUNTER_ROLES:
        return
    if target_status in (AlterationStatus.IN_PROGRESS, AlterationStatus.QC):
        if alteration is None:
            return
        if tailor_id is None or tailor_id not in assigned_tailor_ids(alteration):
            raise PermissionError('This alteration is not assigned to you.')


def assigned_tailor_ids(alteration):
    """Tailor ids holding work on this alteration."""
    return {t.assigned_to_id for t in alteration.tasks.all() if t.assigned_to_id}


def available_actions(alteration, role, tailor_id=None):
    """Action keys the given person may perform right now.

    Used by the API so the UI never has to re-derive the state machine, and so
    the buttons a person sees are exactly the ones the server will accept.
    """
    actions = []
    if not role or role == DESIGNER:
        return actions

    candidates = [
        ('start-inspection', AlterationStatus.INSPECTION),
        ('submit-for-approval', AlterationStatus.PENDING_APPROVAL),
        ('approve', AlterationStatus.APPROVED),
        ('assign', AlterationStatus.ASSIGNED),
        ('start-work', AlterationStatus.IN_PROGRESS),
        ('send-to-qc', AlterationStatus.QC),
        ('pass-qc', AlterationStatus.READY_FOR_PICKUP),
        ('complete', AlterationStatus.COMPLETED),
        ('cancel', AlterationStatus.CANCELLED),
    ]
    for key, target in candidates:
        try:
            validate_transition(alteration.status, target)
            check_permission(target, role=role, alteration=alteration, tailor_id=tailor_id)
        except (TransitionError, PermissionError):
            continue
        actions.append(key)

    # fail-qc also lands on IN_PROGRESS but is only offered from QC.
    if alteration.status == AlterationStatus.QC:
        try:
            check_role(role, QC_ROLES, what='failing a quality check')
            actions.append('fail-qc')
        except PermissionError:
            pass

    if alteration.status not in (AlterationStatus.COMPLETED, AlterationStatus.CANCELLED):
        # Only when there is genuinely something to collect. record_alteration_payment
        # refuses a free alteration and one with nothing outstanding, and this
        # list exists so the buttons on screen are the ones the server accepts.
        owes = (alteration.alteration_type != AlterationType.FREE_BOUTIQUE_FAULT
                and (alteration.charge_amount or 0) > (alteration.amount_paid or 0))
        if owes:
            try:
                check_role(role, PAYMENT_ROLES, what='recording a payment')
                actions.append('record-payment')
            except PermissionError:
                pass
        try:
            check_role(role, MATERIAL_ROLES, what='recording material usage')
            actions.append('record-material')
        except PermissionError:
            pass

    return actions
