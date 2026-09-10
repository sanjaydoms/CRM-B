import { useMemo, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { Field, Segmented } from '../../components/ui/Atelier';
import { emptyClassification } from './taxonomy';

const GARMENT = 'GARMENT';
const ACCESSORY = 'ACCESSORY';

const blankDraft = { garment: '', section: '', slot: '' };

function UseCard({ taxonomy, use, onRemove }) {
  const garment = (taxonomy.garments || []).find((g) => g.key === use.garment);
  const section = (garment?.sections || []).find((s) => s.key === use.section);
  const slot = (section?.slots || []).find((s) => s.key === use.slot);

  const detail = [use.section ? section?.label : null, slot?.label]
    .filter(Boolean).join(' · ') || 'Anywhere on this garment';

  return (
    <div className="at-row">
      <div className="at-row-main">
        <div className="at-row-title">{garment?.label || use.garment}</div>
        <div className="at-row-sub">{detail}</div>
      </div>
      <button
        type="button"
        aria-label={`Remove ${garment?.label || use.garment}`}
        onClick={onRemove}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: 4, lineHeight: 0 }}
      >
        <X size={15} />
      </button>
    </div>
  );
}

function UseBuilder({ taxonomy, onAdd, onCancel, canCancel }) {
  const [draft, setDraft] = useState(blankDraft);

  const garment = useMemo(
    () => (taxonomy.garments || []).find((g) => g.key === draft.garment),
    [taxonomy, draft.garment]);
  const hasParts = !!garment?.section_label;
  const section = useMemo(() => {
    if (!garment) return null;
    return (garment.sections || []).find(
      (s) => s.key === (hasParts ? draft.section : ''));
  }, [garment, hasParts, draft.section]);

  const ready = !!draft.garment && (!hasParts || !!draft.section);

  return (
    <div className="at-stack" style={{ gap: 'var(--space-3)' }}>
      <Field label="Garment">
        <select
          className="form-control"
          value={draft.garment}
          onChange={(e) => setDraft({ ...draft, garment: e.target.value, section: '', slot: '' })}
        >
          <option value="">Select garment</option>
          {(taxonomy.garments || []).map((g) => (
            <option key={g.key} value={g.key}>{g.label}</option>
          ))}
        </select>
      </Field>

      {hasParts && (
        <Field label="Part">
          <select
            className="form-control"
            value={draft.section}
            onChange={(e) => setDraft({ ...draft, section: e.target.value, slot: '' })}
          >
            <option value="">Select part</option>
            {(garment.sections || []).map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </Field>
      )}

      {ready && (
        <Field label="Component">
          <select
            className="form-control"
            value={draft.slot}
            onChange={(e) => setDraft({ ...draft, slot: e.target.value })}
          >
            <option value="">Anywhere on this garment</option>
            {(section?.slots || []).map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </Field>
      )}

      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        <button
          type="button"
          className="btn-primary at-btn-sm"
          disabled={!ready}
          onClick={() => {
            onAdd({ garment: draft.garment, section: hasParts ? draft.section : '', slot: draft.slot });
            setDraft(blankDraft);
          }}
        >
          <Plus size={14} /> Add use
        </button>
        {canCancel && (
          <button type="button" className="btn-secondary at-btn-sm" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

export default function FabricPlacements({ taxonomy, value, onChange }) {
  const selection = value || emptyClassification();
  const [mode, setMode] = useState(selection.kind ? ACCESSORY : GARMENT);
  const [adding, setAdding] = useState(!selection.placements?.length);

  const kinds = taxonomy?.kinds || [];
  const kind = kinds.find((k) => k.key === selection.kind);
  const accessoryKinds = kinds.filter((k) => k.accessory);

  const set = (patch) => onChange({ ...selection, ...patch });

  const add = (use) => {
    const exists = selection.placements.some(
      (p) => p.garment === use.garment && p.section === use.section && p.slot === use.slot);
    if (!exists) set({ placements: [...selection.placements, use] });
    setAdding(false);
  };

  if (!taxonomy) return <div className="at-field-hint">Loading…</div>;

  return (
    <div className="at-stack" style={{ gap: 'var(--space-4)' }}>
      <Segmented
        ariaLabel="Where can you use this material"
        value={mode}
        options={[{ key: GARMENT, label: 'Garment' }, { key: ACCESSORY, label: 'Accessory' }]}
        onChange={(next) => {
          setMode(next);
          if (next === ACCESSORY) set({ placements: [] });
          else set({ kind: '', variant: '' });
          setAdding(next === GARMENT && !selection.placements.length);
        }}
      />

      {mode === ACCESSORY ? (
        <div className="at-form-grid">
          <Field label="Accessory Type">
            <select
              className="form-control"
              value={selection.kind}
              onChange={(e) => set({ kind: e.target.value, variant: '' })}
            >
              <option value="">Select accessory</option>
              {accessoryKinds.map((k) => (
                <option key={k.key} value={k.key}>{k.label}</option>
              ))}
            </select>
          </Field>
          {!!kind?.variants?.length && (
            <Field label={kind.variant_label || 'Type'}>
              <select
                className="form-control"
                value={selection.variant}
                onChange={(e) => set({ variant: e.target.value })}
              >
                <option value="">Select type</option>
                {kind.variants.map((v) => (
                  <option key={v.key} value={v.key}>{v.label}</option>
                ))}
              </select>
            </Field>
          )}
        </div>
      ) : (
        <>
          {selection.placements.length > 0 && (
            <div>
              <span className="at-field-label">Uses</span>
              <div style={{ marginTop: '4px' }}>
                {selection.placements.map((p, i) => (
                  <UseCard
                    key={`${p.garment}-${p.section}-${p.slot}`}
                    taxonomy={taxonomy}
                    use={p}
                    onRemove={() => set({
                      placements: selection.placements.filter((_, idx) => idx !== i),
                    })}
                  />
                ))}
              </div>
            </div>
          )}

          {adding ? (
            <UseBuilder
              taxonomy={taxonomy}
              onAdd={add}
              onCancel={() => setAdding(false)}
              canCancel={selection.placements.length > 0}
            />
          ) : (
            <button
              type="button"
              className="btn-secondary at-btn-sm"
              style={{ alignSelf: 'flex-start', borderStyle: 'dashed' }}
              onClick={() => setAdding(true)}
            >
              <Plus size={14} /> Add another use
            </button>
          )}
        </>
      )}
    </div>
  );
}
