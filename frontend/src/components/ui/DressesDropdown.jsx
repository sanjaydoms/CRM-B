import { Check, X, Shirt } from 'lucide-react';

/**
 * DressesDropdown - a native select for adding garments to the order, with the
 * chosen ones shown as removable pills above it. An order holds several
 * dresses, so picking one adds it and the select resets to ask for the next.
 */
export default function DressesDropdown({
  title = "Dresses in this Order",
  subtitle = "Pick every garment being stitched. Each one opens its own design parts below.",
  isRequired = false,
  garmentTemplates = [],
  garmentJobs = [],
  addingGarmentKey = null,
  garmentTemplatesError = null,
  loadGarmentTemplates = null,
  addGarment,
  removeGarment,
}) {
  const chosenKeys = new Set(garmentJobs.map((job) => job.key));
  const available = garmentTemplates.filter((t) => !chosenKeys.has(t.key));

  return (
    <div
      style={{
        background: 'var(--surface-color, #ffffff)',
        border: '1px solid var(--border-color, #e5e1d7)',
        borderRadius: '12px',
        padding: '16px 18px',
        marginBottom: '20px',
        textAlign: 'left',
        boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
      }}
    >
      {/* Section Header */}
      <div style={{ marginBottom: '12px' }}>
        <label
          className="form-label"
          style={{
            fontWeight: 700,
            fontSize: '14.5px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            margin: 0,
            color: 'var(--text-primary, #1e293b)',
          }}
        >
          <Shirt size={16} style={{ color: 'var(--accent-text, #18181b)' }} />
          <span>{title}</span>
          {isRequired && <span className="required" style={{ color: '#ef4444' }}>*</span>}
        </label>
        {subtitle && (
          <div style={{ fontSize: '12.5px', color: 'var(--text-secondary, #64748b)', marginTop: '4px' }}>
            {subtitle}
          </div>
        )}
      </div>

      {/* Chosen garments */}
      {garmentJobs.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center', marginBottom: '10px' }}>
          {garmentJobs.map((job) => {
            const name = job.template?.name || job.key;
            return (
              <span
                key={job.key}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '4px 10px',
                  borderRadius: '20px',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  background: '#18181b',
                  color: '#ffffff',
                  boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
                }}
              >
                <Check size={12} style={{ color: '#4ade80' }} />
                {name}
                <button
                  type="button"
                  onClick={() => removeGarment?.(job.key)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'rgba(255,255,255,0.7)',
                    cursor: 'pointer',
                    padding: '0 2px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: '50%',
                    marginLeft: '2px',
                  }}
                  title={`Remove ${name}`}
                >
                  <X size={12} />
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* Garment picker. Value is pinned to '' so every pick re-arms it. */}
      <select
        className="form-control"
        value=""
        disabled={!!addingGarmentKey || available.length === 0}
        onChange={(e) => { if (e.target.value) addGarment?.(e.target.value); }}
      >
        <option value="">
          {addingGarmentKey
            ? 'Loading…'
            : available.length === 0 && garmentTemplates.length > 0
              ? 'All garments added'
              : 'Select Garment'}
        </option>
        {available.map((template) => (
          <option key={template.key} value={template.key}>{template.name}</option>
        ))}
      </select>

      {/* Error state if templates fail to load */}
      {garmentTemplates.length === 0 && garmentTemplatesError && (
        <div style={{ fontSize: '12.5px', color: '#c0392b', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span>The garment list could not be loaded — {garmentTemplatesError}</span>
          {loadGarmentTemplates && (
            <button
              type="button"
              className="btn-secondary"
              style={{ padding: '3px 8px', fontSize: '12px' }}
              onClick={loadGarmentTemplates}
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
