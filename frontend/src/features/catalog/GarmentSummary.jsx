import { useEffect, useMemo, useState } from 'react';

import { api } from '../../services/api';
import { isVisible } from '../../services/templates';

/**
 * Read-only recap of every dress on the order, for the review step.
 *
 * The review used to print `customerForm.garment_type` and the handful of legacy
 * style dropdowns, so none of the per-dress answers -- the measurements, the
 * neck, the materials -- reached the confirmation screen. Staff were asked to
 * approve an order without being shown what they had entered.
 *
 * Values are rendered through the template metadata rather than raw: an option
 * shows its label, not `fall_pico`.
 */

const formatKey = (key) => key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

function useInventoryNames(needed) {
  const [names, setNames] = useState({});

  useEffect(() => {
    if (!needed) return;
    let cancelled = false;
    api
      .getInventoryItems({})
      .then((data) => {
        if (cancelled) return;
        const items = data.results || data;
        setNames(Object.fromEntries(items.map((i) => [String(i.id), i.name])));
      })
      .catch(() => {
        /* Names are a nicety here; the id still identifies the line. */
      });
    return () => {
      cancelled = true;
    };
  }, [needed]);

  return names;
}

function displayValue(field, value, inventoryNames) {
  if (value === null || value === undefined || value === '') return null;

  if (field.field_type === 'boolean') return value ? 'Yes' : 'No';

  if (field.field_type === 'select') {
    return field.options.find((o) => o.value === value)?.label ?? value;
  }

  if (field.field_type === 'multiselect') {
    const chosen = Array.isArray(value) ? value : [value];
    if (!chosen.length) return null;
    return chosen
      .map((v) => field.options.find((o) => o.value === v)?.label ?? v)
      .join(', ');
  }

  if (field.field_type === 'inventory_ref') {
    return inventoryNames[String(value)] || 'Selected from stock';
  }

  if (field.field_type === 'file') {
    // Kept for any value already stored on an existing garment job, but it can
    // no longer say "Attached" for something that was never saved. TemplateForm
    // stops rendering file inputs at all (see the comment there): the browser's
    // File object does not survive JSON.stringify, so what reached the database
    // was `{}` or `[{}]` while this line reported success. A summary that
    // confirms an upload the product cannot perform is worse than no summary.
    if (Array.isArray(value)) {
      const named = value.filter((v) => v && v.name);
      return named.length ? named.map((v) => v.name).join(', ') : 'Not saved';
    }
    return value?.name || 'Not saved';
  }

  const text = String(value);
  return field.unit ? `${text} ${field.unit}` : text;
}

export default function GarmentSummary({ jobs, onEdit }) {
  const needsInventory = useMemo(
    () =>
      jobs.some((job) =>
        job.template.sections.some((s) =>
          s.fields.some((f) => f.field_type === 'inventory_ref' && job.values[f.key])
        )
      ),
    [jobs]
  );
  const inventoryNames = useInventoryNames(needsInventory);

  if (!jobs.length) {
    return (
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
        No garment was added to this order.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {jobs.map((job) => {
        // Only what was actually answered, and only fields that still apply --
        // an answer left behind by a since-hidden field must not resurface here.
        const sections = job.template.sections
          .map((section) => ({
            ...section,
            answered: section.fields
              .filter((f) => isVisible(f, job.values))
              .map((f) => ({ field: f, text: displayValue(f, job.values[f.key], inventoryNames) }))
              .filter((entry) => entry.text !== null),
          }))
          .filter((section) => section.answered.length > 0);

        const total = sections.reduce((n, s) => n + s.answered.length, 0);

        return (
          <div
            key={job.key}
            style={{
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '16px',
              backgroundColor: '#fcfdfd',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontSize: '14px', fontWeight: 700 }}>{job.template.name}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  {total} detail{total === 1 ? '' : 's'} recorded
                </span>
                {onEdit && (
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ padding: '4px 10px', fontSize: '11px' }}
                    onClick={onEdit}
                  >
                    Edit
                  </button>
                )}
              </span>
            </div>

            {sections.map((section) => (
              <div key={section.key} style={{ marginBottom: '12px' }}>
                <span
                  style={{
                    fontSize: '9px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    color: 'var(--text-secondary)',
                    fontWeight: 700,
                    display: 'block',
                    marginBottom: '6px',
                  }}
                >
                  {section.title}
                </span>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
                    gap: '10px',
                  }}
                >
                  {section.answered.map(({ field, text }) => (
                    <div key={field.key}>
                      <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>
                        {field.label || formatKey(field.key)}
                      </span>
                      <span style={{ fontSize: '11.5px', fontWeight: 600, wordBreak: 'break-word' }}>{text}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
