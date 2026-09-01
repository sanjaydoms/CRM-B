"""The order workflow as a state machine, rather than a pile of special cases.

Every rule about what an order may do next used to live as an `if stage_key ==`
block inside transition_order_stage -- five of them, each guarding one stage
somebody had been burned by. Everything nobody had been burned by yet was
allowed. So `POST /transition/ {"stage_key": "ready_for_delivery",
"status": "COMPLETED"}` from an order sitting in pattern cutting returned 200
and moved the customer's tracking page to "Ready for Dispatch", with stitching,
finishing, pressing and quality check all still NOT_STARTED.

Hiding the buttons does not fix that. The rule has to live where the request
lands.

ONE SOURCE OF ORDERING
======================
BoutiqueSettings.workflow_config is already an ordered list, so position in it
*is* the order. Nothing here stores an `allowed_next_stages` beside it: two
declarations of the same fact drift, and the drift is silent.

WHAT `optional` MEANS
=====================
`optional: true` says *this stage may not apply to this order* -- most garments
have no maggam work. It is the only thing that licenses a SKIPPED status.

It does NOT mean "anyone may jump over this stage". Those are different ideas,
and collapsing them recreates the bug: a workflow where every stage can be
skipped at will is a workflow with no order at all. A non-optional stage cannot
be skipped, and must be COMPLETED before anything after it starts.

GOING BACKWARDS
===============
A COMPLETED stage stays completed -- through transition_order_stage. The two
sanctioned ways back both live here, and both are explicit and audited:

* check_reopen / OrderService.reopen_order_stage: a supervisor (Owner or
  Master) undoes a mistaken completion, with a mandatory reason. Only the
  FRONTIER settled stage can be reopened -- the latest one with nothing
  started after it -- so the record rolls back one honest step at a time
  instead of leaving completed work stranded on top of a reopened hole.

* OrderService.fail_quality_check: the one legitimate loop in tailoring.
  QC rejecting a garment is not a rollback, it is a transition of its own:
  the stitching band reopens for rework, the reason lands in the record,
  and the customer-facing status drops to match what is now true.

Anything else that moves a settled stage backwards is still refused.
"""

VALID_STATUSES = ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'PAUSED')

#: A stage is finished with, one way or another.
SETTLED_STATUSES = ('COMPLETED', 'SKIPPED')

#: Statuses that mean work on this stage has begun. Entering a stage is what
#: the ordering rule guards; leaving it alone is always fine.
ENTERING_STATUSES = ('IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'PAUSED')


class TransitionError(ValueError):
    """This transition is not allowed, and nothing has been changed.

    A ValueError subclass because the view layer already turns ValueError into
    400 -- the point is the message, which names what is missing rather than
    saying 'invalid'.
    """


def _requires_measurements(order, stage):
    """A tailor cannot cut to measurements nobody has taken."""
    from domains.orders.services import customer_has_measurements
    # Deliberately NOT satisfied by the measurements_completed stage being
    # marked done. Ordering already requires that stage, so accepting it here
    # would make this check unreachable -- and a stage marked complete is a
    # claim that somebody measured, not evidence of it. What the tailor needs
    # is the numbers, so the numbers are what this asks for.
    if customer_has_measurements(order.customer):
        return None
    return 'Measurements are not completed for this customer.'


def _requires_a_tailor(order, stage):
    """Somebody has to be holding the garment before stitching can start.

    Two fields answer "who is stitching this": order.tailor, set when the order
    is taken, and stage.assigned_to, set by assign_stage -- which is the only
    assignment write a Master is permitted, since setting order.tailor needs an
    Owner-only PATCH. Reading just order.tailor meant a Master could hand the
    stitching to a tailor, see it recorded, and have that tailor refused when
    they tried to start.
    """
    if order.tailor_id or stage.assigned_to_id:
        return None
    return 'No tailor is assigned to this order.'


#: What an order must already contain to enter a stage, beyond the ordering
#: rule. Keyed by stage; each returns None when satisfied, or the reason it is
#: not. Ordering is handled generically -- this is only for facts about the
#: order that the sequence cannot express.
REQUIRED_DATA = {
    'assigned_to_tailor': _requires_measurements,
    'stitching_in_progress': _requires_a_tailor,
}


def ordered_stages(config):
    """The workflow as declared, in order. The only ordering source."""
    return [s for s in (config or []) if s.get('key')]


def stage_position(config, stage_key):
    """Where this stage sits in the workflow, or None if it is not in it."""
    for index, stage in enumerate(ordered_stages(config)):
        if stage['key'] == stage_key:
            return index
    return None


def is_optional(config, stage_key):
    for stage in ordered_stages(config):
        if stage['key'] == stage_key:
            return bool(stage.get('optional'))
    return False


def prerequisites(config, stage_key):
    """Every stage that must be COMPLETED before this one may be entered.

    Derived from position: everything earlier that is not optional. Optional
    stages are left out because an order that legitimately has no maggam work
    should not be stuck behind it.
    """
    position = stage_position(config, stage_key)
    if position is None:
        return []
    return [s for s in ordered_stages(config)[:position] if not s.get('optional')]


def check_transition(order, stage, new_status, *, config, role, owner_role):
    """Decide whether this transition may happen. Raise if it may not.

    `stage` is the order's own OrderStage row, so the answer is about this
    order's actual state rather than about the workflow in the abstract.

    Returns None when the transition is allowed. Every rejection raises
    TransitionError before anything is written, so a refused transition leaves
    the order exactly as it was -- status, stage, inventory, activity log,
    assignments and timestamps all untouched.
    """
    stage_key = stage.stage_key
    label = stage.stage_name or stage_key

    if new_status not in VALID_STATUSES:
        raise TransitionError(f'Invalid stage status "{new_status}"')

    declared = next(
        (s for s in ordered_stages(config) if s['key'] == stage_key), None)
    if declared is None:
        raise TransitionError(
            f'"{stage_key}" is not a stage in this boutique\'s workflow.')

    # Role. The owner runs the boutique and is never gated by the roster.
    allowed_roles = declared.get('roles', [])
    if role != owner_role and allowed_roles and role not in allowed_roles:
        raise TransitionError(f'Role {role} is not authorized to update {label}')

    # A stage that is settled is settled. Re-completing is a no-op handled by
    # the caller, and SKIPPED -> COMPLETED stays open (the optional work was
    # done after all -- that moves the record forward, not back). Everything
    # else is a reversal, and reversals go through their own audited doors.
    #
    # SKIPPED is pinned here too, deliberately: it used to be that only
    # COMPLETED was, and a staff member whose role appears on an optional
    # stage could move its settled SKIPPED backwards through this very gate --
    # which rewrote order_status from the touched stage and dropped a
    # Delivered order to 'Design & Creation', customer notification included,
    # with no reason and no supervisor anywhere in the story.
    if stage.status in SETTLED_STATUSES and new_status not in SETTLED_STATUSES:
        raise TransitionError(
            f'{label} is already {stage.status.lower()}. Moving a settled '
            f'stage backwards needs a supervisor: use Reopen Stage (or Fail '
            f'QC for rework), which records who and why.')

    # Skipping is a property of the stage, not a privilege of the caller.
    if new_status == 'SKIPPED' and not declared.get('optional'):
        raise TransitionError(
            f'{label} is a required stage and cannot be skipped.')

    # Ordering. Only guards *entering* a stage: setting one back to NOT_STARTED
    # takes nothing forward and needs no prerequisite.
    #
    # values_list rather than order.stages.all(): the order is usually loaded
    # with its stages prefetched, and that cache is written once when the order
    # is fetched. A caller walking several stages in one request -- the status
    # dropdown covering a whole band, the tailor's submit driving start then
    # finish -- would read every prerequisite at its ORIGINAL status and refuse
    # a hop whose predecessor it had itself just completed. One fresh query,
    # every time, because the whole point of this function is to be right about
    # the order's state now.
    if new_status in ENTERING_STATUSES:
        live = dict(order.stages.values_list('stage_key', 'status'))
        outstanding = [
            s for s in prerequisites(config, stage_key)
            if live.get(s['key'], 'NOT_STARTED') not in SETTLED_STATUSES
        ]
        if outstanding:
            names = ', '.join(s.get('name', s['key']) for s in outstanding)
            raise TransitionError(
                f'Cannot move to {label} yet: {names} '
                f'{"is" if len(outstanding) == 1 else "are"} not completed.')

    # Facts about the order that the sequence cannot express.
    validator = REQUIRED_DATA.get(stage_key)
    if validator is not None and new_status in ('IN_PROGRESS', 'COMPLETED'):
        problem = validator(order, stage)
        if problem:
            raise TransitionError(f'Cannot move to {label}. {problem}')


#: Who may reverse settled work. The owner runs the boutique; the Master runs
#: the floor. Nobody else -- a reversal rewrites what the record claims
#: happened, and that is a supervisor's signature.
REOPEN_ROLES = frozenset({'Master'})

#: Who may fail a quality check. The QC Master is the person actually holding
#: the garment at that bench, so they can fail it without fetching a Master.
QC_FAIL_ROLES = frozenset({'Master', 'QC Master'})


def check_reopen(order, stage, *, config, role, owner_role):
    """May this settled stage be reopened, by this caller, right now?

    Raises TransitionError when it may not; PermissionError when the caller's
    role is the problem (the view maps that to 403 rather than 400).
    """
    label = stage.stage_name or stage.stage_key

    if role != owner_role and role not in REOPEN_ROLES:
        raise PermissionError(
            f'Role {role} is not authorized to reopen a completed stage. '
            f'Ask the owner or the Master.')

    if stage.status not in SETTLED_STATUSES:
        raise TransitionError(
            f'{label} is not completed or skipped, so there is nothing to reopen.')

    position = stage_position(config, stage.stage_key)
    if position is None:
        raise TransitionError(
            f'"{stage.stage_key}" is not a stage in this boutique\'s workflow.')

    # The frontier rule: nothing after this stage may have been started. A
    # reopened stage with completed work stacked on top of it would make the
    # record claim the later work happened on a garment whose earlier state is
    # now officially unfinished -- the exact ambiguity reopening exists to fix.
    # To go further back, reopen the later stages first, one honest step at a
    # time.
    live = dict(order.stages.values_list('stage_key', 'status'))
    started_later = [
        s for s in ordered_stages(config)[position + 1:]
        if live.get(s['key'], 'NOT_STARTED') != 'NOT_STARTED'
    ]
    if started_later:
        names = ', '.join(s.get('name', s['key']) for s in started_later)
        raise TransitionError(
            f'Cannot reopen {label} while later work has begun ({names}). '
            f'Reopen the later stages first.')
