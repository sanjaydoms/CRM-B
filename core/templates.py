
from decimal import Decimal, InvalidOperation


class SpecValidationError(ValueError):


    def __init__(self, errors):
        self.errors = errors
        super().__init__(f"{len(errors)} invalid field(s): {', '.join(sorted(errors))}")



def _as_list(value):
    return value if isinstance(value, (list, tuple)) else [value]


def evaluate_rule(rule, values):

    if not rule:
        return True
    if 'all' in rule:
        return all(evaluate_rule(r, values) for r in rule['all'])
    if 'any' in rule:
        return any(evaluate_rule(r, values) for r in rule['any'])

    actual = values.get(rule['field'])
    op = rule.get('op', 'eq')
    expected = rule.get('value')

    if op == 'is_set':
        return actual not in (None, '', [], {})
    if op == 'in':
        return bool(set(_as_list(actual)) & set(_as_list(expected)))
    if op == 'not_in':
        return not (set(_as_list(actual)) & set(_as_list(expected)))
    if op == 'neq':
        return actual != expected
    return actual == expected


def is_visible(field, values):
    return evaluate_rule(field.visible_when, values)


def visible_fields(template, values):

    result = []
    for section in template.sections.all():
        for field in section.fields.all():
            if is_visible(field, values):
                result.append(field)
    return result



def _clean_number(field, raw, errors):
    try:
        number = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        errors[field.key] = f"{field.label} must be a number."
        return None

    rules = field.validation or {}
    minimum, maximum = rules.get('min'), rules.get('max')
    if minimum is not None and number < Decimal(str(minimum)):
        errors[field.key] = f"{field.label} cannot be below {minimum}."
    elif maximum is not None and number > Decimal(str(maximum)):
        errors[field.key] = f"{field.label} cannot exceed {maximum}."
    return str(number)


def _clean_choice(field, raw, errors, multi):
    allowed = {o.value for o in field.options.all() if o.is_active}
    chosen = _as_list(raw) if multi else [raw]
    unknown = [c for c in chosen if c not in allowed]
    if unknown:
        errors[field.key] = f"{field.label}: unknown option {', '.join(map(str, unknown))}."
        return None
    return list(chosen) if multi else raw


def validate_spec(template, spec, *, partial=False):
    errors = {}
    cleaned = {}
    known = {}

    for section in template.sections.all():
        for field in section.fields.all():
            known[field.key] = field

    unknown_keys = set(spec) - set(known)
    if unknown_keys:
        for key in unknown_keys:
            errors[key] = "Unknown field for this garment."

    for key, field in known.items():
        if not is_visible(field, spec):
            continue  # hidden: not required, not stored

        raw = spec.get(key)
        if raw in (None, '', [], {}):
            if field.is_required and not partial:
                errors[key] = f"{field.label} is required."
            continue

        field_type = field.field_type
        if field_type == 'number':
            value = _clean_number(field, raw, errors)
        elif field_type == 'select':
            value = _clean_choice(field, raw, errors, multi=False)
        elif field_type == 'multiselect':
            value = _clean_choice(field, raw, errors, multi=True)
        elif field_type == 'boolean':
            value = bool(raw)
        else:
            value = raw
            max_length = (field.validation or {}).get('max_length')
            if max_length and isinstance(raw, str) and len(raw) > max_length:
                errors[key] = f"{field.label} is limited to {max_length} characters."

        if key not in errors and value is not None:
            cleaned[key] = value

    _validate_cross_field(cleaned, errors)

    if errors:
        raise SpecValidationError(errors)
    return cleaned


def _validate_cross_field(cleaned, errors):

    trial, delivery = cleaned.get('trial_date'), cleaned.get('delivery_date')
    if trial and delivery and str(trial) > str(delivery):
        errors['trial_date'] = "Trial date must fall before the delivery date."
