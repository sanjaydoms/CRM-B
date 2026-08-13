import { useEffect, useMemo, useState } from 'react';

import { api } from '../../services/api';
import { getSection, isVisible, pruneHidden } from '../../services/templates';

/**
 * Renders one section of a garment template.
 *
 * This replaces the hardcoded garment dropdown, stitch-part grid and seven fixed
 * measurement inputs the wizard used to carry. Everything shown here comes from
 * /api/catalog/templates/, so adding Sharara or a new saree type is a data
 * change.
 */

// Inventory pickers all want the same shape, and several fields on one form ask
// for the same category. Fetch once per category and share it across fields.
function useInventoryOptions(categories) {
  const [byCategory, setByCategory] = useState({});

  const wanted = useMemo(() => [...new Set(categories)].sort().join(','), [categories]);

  useEffect(() => {
    if (!wanted) return;
    let cancelled = false;
    Promise.all(
      wanted.split(',').map((category) =>
        api
          .getInventoryItems({ category })
          .then((items) => [category, items.results || items])
          .catch(() => [category, []])
      )
    ).then((pairs) => {
      if (!cancelled) setByCategory(Object.fromEntries(pairs));
    });
    return () => {
      cancelled = true;
    };
  }, [wanted]);

  return byCategory;
}

function Field({ field, value, error, onChange, inventory }) {
  const common = {
    className: 'form-control',
    id: `tf-${field.key}`,
    value: value ?? '',
    onChange: (e) => onChange(field.key, e.target.value),
  };

  let control;
  switch (field.field_type) {
    case 'textarea':
      control = <textarea {...common} rows={3} placeholder={field.help_text || ''} />;
      break;

    case 'number':
      control = (
        <input
          {...common}
          type="number"
          step={field.validation?.step || 0.25}
          min={field.validation?.min}
          max={field.validation?.max}
          placeholder="0.00"
        />
      );
      break;

    case 'date':
      control = <input {...common} type="date" />;
      break;

    case 'boolean':
      control = (
        <select
          {...common}
          value={value === true ? 'yes' : value === false ? 'no' : ''}
          onChange={(e) =>
            onChange(field.key, e.target.value === '' ? null : e.target.value === 'yes')
          }
        >
          <option value="">Select</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      );
      break;

    case 'select':
      control = (
        <select {...common}>
          <option value="">Select</option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
      break;

    case 'multiselect': {
      const chosen = Array.isArray(value) ? value : [];
      control = (
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', paddingTop: '6px' }}>
          {field.options.map((option) => (
            <label
              key={option.value}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13.5px',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={chosen.includes(option.value)}
                onChange={(e) =>
                  onChange(
                    field.key,
                    e.target.checked
                      ? [...chosen, option.value]
                      : chosen.filter((v) => v !== option.value)
                  )
                }
              />
              {option.label}
            </label>
          ))}
        </div>
      );
      break;
    }

    case 'inventory_ref': {
      const items = inventory[field.inventory_category] || [];
      control = (
        <select {...common}>
          <option value="">
            {items.length ? 'Select from stock' : 'Nothing in stock for this category'}
          </option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
              {item.available_stock !== undefined
                ? ` — ${item.available_stock} ${item.unit || ''} available`
                : ''}
            </option>
          ))}
        </select>
      );
      break;
    }

    case 'file':
      // Uploads run through the existing media service on save, so the form only
      // records the intent here.
      control = (
        <input
          className="form-control"
          type="file"
          multiple={field.is_repeatable}
          onChange={(e) =>
            onChange(field.key, field.is_repeatable ? [...e.target.files] : e.target.files[0])
          }
        />
      );
      break;

    default:
      control = <input {...common} type="text" placeholder={field.help_text || ''} />;
  }

  return (
    <div className="form-group">
      <label className="form-label" htmlFor={`tf-${field.key}`}>
        {field.label}
        {field.unit ? ` (${field.unit})` : ''}
        {field.is_required && <span className="required"> *</span>}
      </label>
      {control}
      {field.help_text && field.field_type !== 'text' && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          {field.help_text}
        </div>
      )}
      {error && (
        <div style={{ fontSize: '12px', color: '#c0392b', marginTop: '4px' }}>{error}</div>
      )}
    </div>
  );
}

export default function TemplateForm({ template, section, values, errors = {}, onChange }) {
  const definition = getSection(template, section);
  // File fields are not rendered, because nothing in this product can save one.
  //
  // The four of them -- Measurement Sheet, Reference Images, Audio Note, Final
  // Approved Design -- stored the browser's raw File object in `values`, and
  // saveGarmentJobs sends that through JSON.stringify, which turns a File into
  // `{}`. core/templates.py then treats `{}` as empty and drops the key with no
  // error; a repeatable one becomes `[{}]` and is stored verbatim, reaching the
  // tailor's "What to make" panel as `reference images: [object Object]`.
  // Meanwhile GarmentSummary printed "Attached".
  //
  // So a staff member photographed the customer's handwritten measurement
  // sheet, the wizard advanced with no complaint, and the artefact proving what
  // was actually measured was gone at the moment of capture.
  //
  // Removing the affordance rather than hardening the write path, deliberately.
  // Rejecting the value server-side would be worse: saveGarmentJobs runs AFTER
  // the order is created, so a hard 400 there strands an order with no garment
  // job behind a dead wizard. Real uploads need a multipart endpoint and a
  // FormData path, which is a feature -- see the audit's Missing Features
  // table. Until it exists, offering the input is the bug.
  const fields = (definition?.fields || [])
    .filter((f) => f.field_type !== 'file')
    .filter((f) => isVisible(f, values));

  const inventory = useInventoryOptions(
    fields.filter((f) => f.field_type === 'inventory_ref').map((f) => f.inventory_category)
  );

  const handleChange = (key, value) => {
    // Prune after every edit: switching Peplum to Corset must take the flare
    // length with it, or the cutter is handed a measurement for a panel that is
    // not being made.
    onChange(pruneHidden(template, { ...values, [key]: value }));
  };

  if (!definition) return null;
  if (!fields.length) {
    return (
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', padding: '8px 0' }}>
        Nothing to record here for a {template.name.toLowerCase()}.
      </div>
    );
  }

  return (
    <div className="form-grid-2">
      {fields.map((field) => (
        <Field
          key={field.key}
          field={field}
          value={values[field.key]}
          error={errors[field.key]}
          onChange={handleChange}
          inventory={inventory}
        />
      ))}
    </div>
  );
}
