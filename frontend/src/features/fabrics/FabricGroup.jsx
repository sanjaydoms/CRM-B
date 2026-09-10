import { Plus, Trash2 } from 'lucide-react';
import { blankMaterial } from './taxonomy';
import FabricEntry from './FabricEntry';
import FabricPlacements from './FabricPlacements';

/**
 * One placement -- Saree > Pallu, or a reusable accessory -- and every material
 * stocked for it. The placement is picked once; materials repeat underneath.
 */
export default function FabricGroup({
  taxonomy, value, onChange, onRemove, canRemove, index, onUploading, allowRepeat,
}) {
  const set = (patch) => onChange({ ...value, ...patch });
  const materials = value.materials;

  return (
    <section className="at-form-section">
      <header className="at-form-section-head">
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="at-section-title">
            {canRemove ? `Section ${index + 1}` : 'Where can you use this?'}
          </div>
          <div className="at-field-hint">
            Select where these materials will be used. You can choose more than one.
          </div>
        </div>
        {canRemove && (
          <button type="button" className="btn-secondary at-btn-sm at-btn-danger" onClick={onRemove}>
            <Trash2 size={14} /> Remove
          </button>
        )}
      </header>

      <FabricPlacements taxonomy={taxonomy} value={value} onChange={onChange} />

      {materials.map((m, i) => (
        <FabricEntry
          key={m._id}
          index={`${index}-${i}`}
          number={i + 1}
          value={m}
          canRemove={allowRepeat && materials.length > 1}
          onUploading={onUploading}
          onChange={(next) => set({
            materials: materials.map((row, idx) => (idx === i ? next : row)),
          })}
          onRemove={() => set({ materials: materials.filter((_, idx) => idx !== i) })}
        />
      ))}

      {allowRepeat && (
        <button
          type="button"
          className="btn-secondary at-btn-sm"
          style={{ alignSelf: 'flex-start', borderStyle: 'dashed' }}
          onClick={() => set({ materials: [...materials, blankMaterial()] })}
        >
          <Plus size={14} /> Add another material here
        </button>
      )}
    </section>
  );
}
