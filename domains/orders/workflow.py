
VALID_STATUSES = ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'PAUSED')

SETTLED_STATUSES = ('COMPLETED', 'SKIPPED')

ENTERING_STATUSES = ('IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'PAUSED')


class TransitionError(ValueError):
    pass


def _requires_measurements(order, stage):

    from domains.orders.services import customer_has_measurements
    if customer_has_measurements(order.customer):
        return None
    return 'Measurements are not completed for this customer.'


def _requires_a_tailor(order, stage):
    if order.tailor_id or stage.assigned_to_id:
        return None
    return 'No tailor is assigned to this order.'


REQUIRED_DATA = {
    'assigned_to_tailor': _requires_measurements,
    'stitching_in_progress': _requires_a_tailor,
}


def ordered_stages(config):

    return [s for s in (config or []) if s.get('key')]


def stage_position(config, stage_key):

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
    position = stage_position(config, stage_key)
    if position is None:
        return []
    return [s for s in ordered_stages(config)[:position] if not s.get('optional')]


def check_transition(order, stage, new_status, *, config, role, owner_role):
    stage_key = stage.stage_key
    label = stage.stage_name or stage_key

    if new_status not in VALID_STATUSES:
        raise TransitionError(f'Invalid stage status "{new_status}"')

    declared = next(
        (s for s in ordered_stages(config) if s['key'] == stage_key), None)
    if declared is None:
        raise TransitionError(
            f'"{stage_key}" is not a stage in this boutique\'s workflow.')

    allowed_roles = declared.get('roles', [])
    if role != owner_role and allowed_roles and role not in allowed_roles:
        raise TransitionError(f'Role {role} is not authorized to update {label}')

    if stage.status == 'COMPLETED' and new_status != 'COMPLETED':
        raise TransitionError(
            f'{label} is already completed. Reopening a completed stage is not '
            f'supported; use an alteration or rework to revisit it.')

    if new_status == 'SKIPPED' and not declared.get('optional'):
        raise TransitionError(
            f'{label} is a required stage and cannot be skipped.')

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

    validator = REQUIRED_DATA.get(stage_key)
    if validator is not None and new_status in ('IN_PROGRESS', 'COMPLETED'):
        problem = validator(order, stage)
        if problem:
            raise TransitionError(f'Cannot move to {label}. {problem}')
