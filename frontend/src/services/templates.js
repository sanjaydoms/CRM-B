/**
 * Visibility and validation for garment templates.
 *
 * The exact mirror of core/templates.py. If you change a rule here, change it
 * there in the same commit: the browser hiding a field the server still demands
 * is how a form saves an order with the wrong measurements on it.
 *
 * A hidden field is never required and is never stored.
 */

const asList = (value) => (Array.isArray(value) ? value : [value]);

const isEmpty = (value) =>
  value === null ||
  value === undefined ||
  value === '' ||
  (Array.isArray(value) && value.length === 0);

export function evaluateRule(rule, values) {
  if (!rule) return true;
  if (rule.all) return rule.all.every((r) => evaluateRule(r, values));
  if (rule.any) return rule.any.some((r) => evaluateRule(r, values));

  const actual = values[rule.field];
  const op = rule.op || 'eq';
  const expected = rule.value;

  if (op === 'is_set') return !isEmpty(actual);
  // A multiselect answer is a list, so 'in' means "any chosen value matches" --
  // picking Fall + Pico must reveal both the fall and the pico field.
  if (op === 'in') {
    const chosen = new Set(asList(actual));
    return asList(expected).some((v) => chosen.has(v));
  }
  if (op === 'not_in') {
    const chosen = new Set(asList(actual));
    return !asList(expected).some((v) => chosen.has(v));
  }
  if (op === 'neq') return actual !== expected;
  return actual === expected;
}

export const isVisible = (field, values) => evaluateRule(field.visible_when, values);

/** Every field of a section that currently applies, in render order. */
export function visibleFields(section, values) {
  if (!section) return [];
  return section.fields.filter((field) => isVisible(field, values));
}

export const getSection = (template, key) =>
  template?.sections?.find((section) => section.key === key);

/**
 * Drop the answers to fields that have become hidden.
 *
 * Called on every change: without it, choosing Peplum, typing a flare length and
 * switching to Corset leaves the flare length behind, and the cutter sees a
 * measurement for a panel that is not being made.
 */
export function pruneHidden(template, values) {
  const kept = {};
  (template?.sections || []).forEach((section) => {
    section.fields.forEach((field) => {
      if (isVisible(field, values) && values[field.key] !== undefined) {
        kept[field.key] = values[field.key];
      }
    });
  });
  return kept;
}

/** Returns {field_key: message}; empty when the spec is good. */
export function validateSpec(template, values, { partial = false } = {}) {
  const errors = {};

  (template?.sections || []).forEach((section) => {
    section.fields.forEach((field) => {
      if (!isVisible(field, values)) return;

      const raw = values[field.key];
      if (isEmpty(raw)) {
        if (field.is_required && !partial) {
          errors[field.key] = `${field.label} is required.`;
        }
        return;
      }

      const rules = field.validation || {};
      if (field.field_type === 'number') {
        const number = Number(raw);
        if (Number.isNaN(number)) {
          errors[field.key] = `${field.label} must be a number.`;
        } else if (rules.min !== undefined && number < rules.min) {
          errors[field.key] = `${field.label} cannot be below ${rules.min}.`;
        } else if (rules.max !== undefined && number > rules.max) {
          errors[field.key] = `${field.label} cannot exceed ${rules.max}.`;
        }
      } else if (field.field_type === 'select' || field.field_type === 'multiselect') {
        const allowed = new Set((field.options || []).map((o) => o.value));
        const unknown = asList(raw).filter((v) => !allowed.has(v));
        if (unknown.length) {
          errors[field.key] = `${field.label}: unknown option ${unknown.join(', ')}.`;
        }
      } else if (rules.max_length && String(raw).length > rules.max_length) {
        errors[field.key] = `${field.label} is limited to ${rules.max_length} characters.`;
      }
    });
  });

  const { trial_date: trial, delivery_date: delivery } = values;
  if (trial && delivery && trial > delivery) {
    errors.trial_date = 'Trial date must fall before the delivery date.';
  }

  return errors;
}

/** Split a flat spec into the two columns GarmentJob stores it in. */
export function splitSpec(template, values) {
  const measurementKeys = new Set(
    (getSection(template, 'measurements')?.fields || []).map((f) => f.key)
  );
  const spec = {};
  const measurements = {};
  Object.entries(values).forEach(([key, value]) => {
    (measurementKeys.has(key) ? measurements : spec)[key] = value;
  });
  return { spec, measurements };
}
