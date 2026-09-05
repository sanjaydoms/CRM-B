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

function Field({ field, value, error, onChange, inventory, quantity, quantityError, onQuantityChange }) {
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
      const selected = items.find((item) => String(item.id) === String(value ?? ''));
      // Picking the roll is half the answer. Without "how much", the order can
      // name a material but the inventory ledger can never reserve or consume
      // it -- which is exactly how a delivered order used to leave stock
      // untouched. So the quantity is asked for here, at the moment the choice
      // is made, rather than defaulted to a number nobody decided.
      control = (
        <>
          <select {...common}>
            <option value="">
              {items.length ? 'Select from stock' : 'Nothing in stock for this category'}
            </option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
                {item.available_stock !== undefined
                  ? ` — ${item.available_stock} ${item.unit_display || item.unit || ''} available`
                  : ''}
              </option>
            ))}
          </select>
          {selected && (
            <div style={{ marginTop: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  className="form-control"
                  id={`tf-${field.key}-qty`}
                  type="number"
                  min="0"
                  step="0.001"
                  style={{ maxWidth: '120px' }}
                  placeholder="Quantity"
                  aria-label={`Quantity of ${selected.name} for ${field.label}`}
                  value={quantity ?? ''}
                  onChange={(e) => onQuantityChange(field.key, e.target.value)}
                />
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  {selected.unit_display || selected.unit || 'units'}
                  {selected.available_stock !== undefined
                    && ` · ${selected.available_stock} available`}
                </span>
              </div>
              {quantityError && (
                <div style={{ fontSize: '12px', color: '#c0392b', marginTop: '4px' }}>
                  {quantityError}
                </div>
              )}
            </div>
          )}
        </>
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

export default function TemplateForm({
  template, section, values, errors = {}, onChange,
  // How much of each selected material this garment needs, keyed by field key.
  // Kept beside `values` rather than inside it because `spec` is validated
  // against the template's own field list, and a quantity is not one of its
  // fields -- it belongs to the material line, not to the garment's spec.
  quantities = {}, quantityErrors = {}, onQuantityChange = () => {},
  // Where to send someone whose inventory is empty. Optional because this form
  // also renders in places that have no navigation to offer.
  onGoToInventory = null,
}) {
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

  const inventoryCategories = fields
    .filter((f) => f.field_type === 'inventory_ref')
    .map((f) => f.inventory_category);
  const inventory = useInventoryOptions(inventoryCategories);

  // Loaded-and-empty across every category this section asks about. A new
  // boutique used to discover mid-order that every picker says "Nothing in
  // stock" -- the guidance belongs before the choices, not scattered under
  // them. Distinguished from still-loading so established boutiques never see
  // the banner flash.
  const inventoryLoaded = inventoryCategories.length > 0
    && inventoryCategories.every((c) => c in inventory);
  const inventoryEmpty = inventoryLoaded
    && inventoryCategories.every((c) => (inventory[c] || []).length === 0);

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
    <div>
      {inventoryEmpty && onGoToInventory && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
          padding: '12px 14px', marginBottom: '14px', borderRadius: '8px',
          border: '1px dashed var(--border-color)', background: 'var(--surface-color, #fafafa)',
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Your inventory has nothing to pick from yet. Add fabrics and materials
            first — this order is saved as a draft, so you can come straight back.
          </div>
          <button type="button" className="btn-secondary" style={{ flexShrink: 0, fontSize: '12px', padding: '6px 12px' }} onClick={onGoToInventory}>
            Set up inventory
          </button>
        </div>
      )}
      <div className="form-grid-2">
      {fields.map((field) => (
        <Field
          key={field.key}
          field={field}
          value={values[field.key]}
          error={errors[field.key]}
          onChange={handleChange}
          inventory={inventory}
          quantity={quantities[field.key]}
          quantityError={quantityErrors[field.key]}
          onQuantityChange={onQuantityChange}
        />
      ))}
      </div>
    </div>
  );
}
