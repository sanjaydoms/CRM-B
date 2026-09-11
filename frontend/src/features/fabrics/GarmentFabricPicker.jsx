import { useMemo, useRef, useEffect, useState } from 'react';
import { Check, Layers, X } from 'lucide-react';

import { resolveMediaUrl } from '../../services/media';
import { PartTabStrip } from '../designStudio/GarmentPartTabs';
import { ACCESSORY_OPTIONS } from '../designStudio/GarmentPartPicker';

/**
 * Fabric, garment by garment and part by part.
 *
 * The fabric step used to be one grid of every roll the boutique owns and one
 * `selectedFabric` for the whole order. An order for a saree and a blouse got
 * the same list twice and could record one cloth between them, so "chanderi for
 * the body, organza for the pallu, net for the sleeves" -- which is what the
 * order actually is -- could not be said at all.
 *
 * Nothing here is new vocabulary. `FabricPlacement` already records which
 * garment, section and slot a roll suits, Manage Fabrics already edits those,
 * and `/fabrics/taxonomy/` already serves the garment -> section -> slot tree
 * keyed by GarmentTemplate.key. This reads all three and lays the fabrics the
 * boutique has already filed under the parts they were filed under.
 *
 * So a part the boutique adds to the taxonomy appears here on its own, and no
 * list of garments or parts is written down in this file.
 */

function AccessoryMultiSelectDropdown({
  options = ACCESSORY_OPTIONS,
  selectedKeys = [],
  onToggleKey,
  activeKey,
  onSelectActiveKey,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedCount = selectedKeys.length;

  return (
    <div style={{ marginBottom: '16px', position: 'relative' }} ref={dropdownRef}>
      <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>
        Select Accessories (Choose one or more options):
      </label>

      {/* Multi-Select Dropdown Header */}
      <button
        type="button"
        className="form-control"
        onClick={() => setIsOpen((v) => !v)}
        style={{
          width: '100%',
          maxWidth: '420px',
          padding: '8px 12px',
          fontSize: '13px',
          fontWeight: 600,
          borderRadius: '8px',
          border: '1.5px solid var(--border-color, #d1d5db)',
          background: 'var(--surface-color, #fff)',
          color: 'var(--text-primary)',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          textAlign: 'left',
        }}
      >
        <span>
          {selectedCount === 0
            ? 'Select accessories from dropdown...'
            : `${selectedCount} Accessor${selectedCount === 1 ? 'y' : 'ies'} Selected`}
        </span>
        <span style={{ fontSize: '11px', opacity: 0.7 }}>{isOpen ? '▲' : '▼'}</span>
      </button>

      {/* Dropdown Menu Overlay */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            zIndex: 99,
            width: '100%',
            maxWidth: '420px',
            marginTop: '4px',
            maxHeight: '260px',
            overflowY: 'auto',
            background: 'var(--surface-color, #ffffff)',
            border: '1.5px solid var(--border-color, #d1d5db)',
            borderRadius: '8px',
            boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
            padding: '8px',
          }}
        >
          {options.map((opt) => {
            const isChecked = selectedKeys.includes(opt.key);
            return (
              <label
                key={opt.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '12.5px',
                  fontWeight: isChecked ? 600 : 400,
                  background: isChecked ? 'rgba(16, 124, 65, 0.08)' : 'transparent',
                  color: isChecked ? '#107c41' : 'var(--text-primary)',
                  marginBottom: '2px',
                }}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => onToggleKey(opt.key)}
                  style={{ width: '15px', height: '15px', accentColor: '#107c41', cursor: 'pointer' }}
                />
                <span>{opt.label}</span>
              </label>
            );
          })}
        </div>
      )}

      {/* Selected Accessories Pills/Tabs */}
      {selectedKeys.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
          {selectedKeys.map((key) => {
            const opt = options.find((o) => o.key === key);
            if (!opt) return null;
            const isActive = activeKey === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => onSelectActiveKey(key)}
                style={{
                  padding: '4px 10px',
                  borderRadius: '16px',
                  border: isActive ? '1.5px solid #107c41' : '1px solid var(--border-color)',
                  background: isActive ? '#107c41' : 'var(--surface-color, #f3f4f6)',
                  color: isActive ? '#fff' : 'var(--text-primary)',
                  fontSize: '11.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <span>{opt.label}</span>
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleKey(key);
                  }}
                  style={{ opacity: 0.8, fontSize: '11px', fontWeight: 700, padding: '0 2px' }}
                  title="Remove accessory"
                >
                  ✕
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

const FABRIC_FALLBACK =
  'https://images.unsplash.com/photo-1574169208507-84376144848b?w=400';

/** Does one placement cover this garment, section and slot?
 *
 *  A placement narrows: naming only the garment means anywhere on it, which is
 *  what Manage Fabrics shows as "Anywhere on this garment". So an empty section
 *  or slot on the placement matches every one of them rather than none.
 */
const placementCovers = (placement, garment, section, slot) =>
  placement.garment === garment
  && (!placement.section || placement.section === section)
  && (!placement.slot || placement.slot === slot);

function FabricCard({ fabric, picked, onToggle }) {
  const image = resolveMediaUrl(fabric.image_url) || FABRIC_FALLBACK;
  return (
    <div className={`fabric-card ${picked ? 'selected' : ''}`}
         role="button"
         tabIndex={0}
         onClick={onToggle}
         onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(); } }}>
      <div className="fabric-image-container">
        <img src={image} alt={fabric.name}
             onError={(e) => { e.currentTarget.src = FABRIC_FALLBACK; }} />
        {picked && <div className="fabric-badge"><Check size={14} /></div>}
      </div>
      <div className="fabric-details">
        <span className="fabric-title">{fabric.name}</span>
        <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>
          {[fabric.material, fabric.color].filter(Boolean).join(' · ')}
        </span>
        {Number(fabric.price_per_meter) > 0 && (
          <span style={{ fontWeight: 600, display: 'block', marginTop: '4px', fontSize: '12px' }}>
            ₹{Number(fabric.price_per_meter).toLocaleString('en-IN')}/mtr
          </span>
        )}
      </div>
    </div>
  );
}


/** One part of one garment, and the fabrics filed under it. */
function SlotRow({ label, fabrics, chosen, onToggle, accessoriesOnly = false }) {
  const chosenFabrics = fabrics.filter(f => chosen.includes(String(f.id)));
  const itemCategoryName = accessoriesOnly ? 'Accessories' : 'Fabrics';

  return (
    <div style={{ marginBottom: '18px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '12px',
                    borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
        <span style={{ fontSize: '13.5px', fontWeight: 700 }}>{label} {itemCategoryName}</span>
        <span style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
          {chosen.length > 0 ? `${chosen.length} chosen` : `${fabrics.length} available`}
        </span>
      </div>

      {fabrics.length === 0 ? (
        // Never another part's fabrics as a fallback: an empty part is a gap in
        // the boutique's own filing, and showing it is how that gets noticed.
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '8px 0' }}>
          No {itemCategoryName.toLowerCase()} available for this part.
        </div>
      ) : (
        <div className="fabrics-grid">
          {fabrics.map((fabric) => (
            <FabricCard key={fabric.id} fabric={fabric}
                        picked={chosen.includes(String(fabric.id))}
                        onToggle={() => onToggle(String(fabric.id))} />
          ))}
        </div>
      )}

      {/* Display selected fabrics for this part at the bottom */}
      {chosenFabrics.length > 0 && (
        <div
          style={{
            marginTop: '16px',
            padding: '14px 16px',
            background: 'var(--background-secondary, #f8f9fa)',
            border: '1.5px solid #18181b',
            borderRadius: '10px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.04)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '10px',
              paddingBottom: '6px',
              borderBottom: '1px solid var(--border-color, #e2e8f0)',
            }}
          >
            <span style={{ fontSize: '12.5px', fontWeight: 700, color: 'var(--text-primary, #0f172a)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Check size={14} style={{ color: '#16a34a', strokeWidth: 3 }} />
              Selected Fabric{chosenFabrics.length > 1 ? 's' : ''} for {label}:
            </span>
            <span style={{ fontSize: '11px', fontWeight: 600, color: '#16a34a', background: '#dcfce7', padding: '2px 8px', borderRadius: '10px' }}>
              {chosenFabrics.length} selected
            </span>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
            {chosenFabrics.map((fabric) => {
              const image = resolveMediaUrl(fabric.image_url) || FABRIC_FALLBACK;
              return (
                <div
                  key={fabric.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    background: '#ffffff',
                    border: '1px solid var(--border-color, #e2e8f0)',
                    borderRadius: '8px',
                    padding: '6px 12px 6px 6px',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
                  }}
                >
                  <img
                    src={image}
                    alt={fabric.name}
                    style={{ width: '38px', height: '38px', borderRadius: '6px', objectFit: 'cover' }}
                    onError={(e) => { e.currentTarget.src = FABRIC_FALLBACK; }}
                  />
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary, #0f172a)' }}>
                      {fabric.name}
                    </div>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-secondary, #64748b)' }}>
                      {[fabric.material, fabric.color].filter(Boolean).join(' · ')}
                      {Number(fabric.price_per_meter) > 0 && ` · ₹${Number(fabric.price_per_meter).toLocaleString('en-IN')}/mtr`}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onToggle(String(fabric.id))}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-secondary, #94a3b8)',
                      cursor: 'pointer',
                      padding: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: '50%',
                      marginLeft: '4px',
                    }}
                    title="Remove fabric selection"
                  >
                    <X size={14} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}


export default function GarmentFabricPicker({
  garmentJobs = [], fabrics = [], taxonomy = null, selection = {}, onChange, loading = false, accessoriesOnly = false,
}) {
  const [activeSlotMap, setActiveSlotMap] = useState({});

  // In stock only, the same rule the flat grid applied: Manage Fabrics is the
  // screen that sets the flag and legitimately still lists what this hides.
  const inStock = useMemo(
    () => (fabrics || []).filter(f => f.is_available !== false), [fabrics]);

  // A roll nobody has filed against any garment yet. Every part offers these,
  // because a boutique that has not started using placements still has to be
  // able to pick fabric -- and their rolls are not "another garment's", they
  // are simply unfiled.
  const unfiled = useMemo(
    () => inStock.filter(f => !(f.placements || []).length), [inStock]);

  const garmentsByKey = useMemo(() => Object.fromEntries(
    (taxonomy?.garments || []).map(g => [g.key, g])), [taxonomy]);

  const [selectedAccessoryMap, setSelectedAccessoryMap] = useState({});

  if (garmentJobs.length === 0) {
    return (
      <div style={{ fontSize: '13.5px', color: 'var(--text-secondary)', padding: '16px 0' }}>
        No garment was chosen yet, so there is nothing to pick {accessoriesOnly ? 'accessories' : 'fabric'} for. Go back and
        pick at least one dress.
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '18px 0' }}>
        Loading {accessoriesOnly ? 'accessories' : 'fabrics'}…
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {garmentJobs.map((job) => {
        const garmentKey = job.template?.key || job.key;
        const garmentName = job.template?.name || job.key;
        const spec = garmentsByKey[garmentKey];
        const chosenForJob = selection[job.key] || {};

        let allSlots;
        if (accessoriesOnly) {
          allSlots = ACCESSORY_OPTIONS.map(opt => ({
            key: opt.key,
            label: opt.label,
            sectionKey: '',
            sectionLabel: '',
            slot: { key: opt.key, label: opt.label },
          }));
        } else {
          allSlots = (spec?.sections || []).flatMap(section =>
            (section.slots || []).map(slot => ({
              key: slot.key,
              label: slot.label,
              sectionKey: section.key,
              sectionLabel: section.label,
              slot,
            }))
          );
        }

        const selectedKeys = selectedAccessoryMap[job.key] || ACCESSORY_OPTIONS.map(o => o.key);
        const toggleAccessoryKey = (key) => {
          setSelectedAccessoryMap((prev) => {
            const current = prev[job.key] || ACCESSORY_OPTIONS.map(o => o.key);
            const next = current.includes(key)
              ? current.filter(k => k !== key)
              : [...current, key];
            return { ...prev, [job.key]: next };
          });
        };

        const activeSlotKey = activeSlotMap[job.key] || allSlots[0]?.key;
        const activeSlotItem = allSlots.find(s => s.key === activeSlotKey) || allSlots[0];

        const toggle = (slotKey) => (fabricId) => {
          const current = chosenForJob[slotKey] || [];
          const next = current.includes(fabricId)
            ? current.filter(id => id !== fabricId)
            : [...current, fabricId];
          // The slot's key goes with its last fabric rather than sitting on the
          // order as an empty list.
          const forJob = { ...chosenForJob };
          if (next.length) forJob[slotKey] = next; else delete forJob[slotKey];
          onChange?.(job.key, forJob);
        };

        return (
          // One card per dress, so a saree's fabrics and a blouse's can never
          // read as one list.
          <div className="content-card" key={job.key}>
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <Layers size={18} /> {garmentName} {accessoriesOnly ? 'Accessories' : ''}
            </div>

            {!spec || allSlots.length === 0 ? (
              // A garment the fabric taxonomy does not describe yet. Said out
              // loud rather than showing an empty card or, worse, another
              // garment's rolls.
              <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                No {accessoriesOnly ? 'accessory' : 'fabric'} parts are configured for {garmentName} yet. Add them under
                Manage Fabrics to pick {accessoriesOnly ? 'accessories' : 'fabric'} part by part.
              </div>
            ) : (
              <div>
                {accessoriesOnly ? (
                  <AccessoryMultiSelectDropdown
                    options={ACCESSORY_OPTIONS}
                    selectedKeys={selectedKeys}
                    onToggleKey={toggleAccessoryKey}
                    activeKey={activeSlotKey}
                    onSelectActiveKey={(key) => setActiveSlotMap(prev => ({ ...prev, [job.key]: key }))}
                  />
                ) : (
                  <PartTabStrip
                    parts={allSlots.map(s => {
                      const chosenCount = (chosenForJob[s.key] || []).length;
                      const sectionPrefix = (spec.sections?.length > 1 && s.sectionLabel) ? `${s.sectionLabel} - ` : '';
                      return {
                        key: s.key,
                        label: chosenCount > 0 ? `✓ ${sectionPrefix}${s.label} (${chosenCount})` : `${sectionPrefix}${s.label}`,
                      };
                    })}
                    active={activeSlotKey}
                    allLabel={null}
                    onChange={(key) => setActiveSlotMap(prev => ({ ...prev, [job.key]: key }))}
                  />
                )}

                {/* Fabrics available for active part tab */}
                {activeSlotItem && (() => {
                  const { sectionKey, slot } = activeSlotItem;
                  const filed = inStock.filter(f => (f.placements || []).some(
                    p => placementCovers(p, garmentKey, sectionKey, slot.key)));
                  // Unfiled rolls come after the ones actually filed here, so
                  // the boutique's own filing leads.
                  const forSlot = [...filed,
                                   ...unfiled.filter(f => !filed.includes(f))];
                  return (
                    <SlotRow
                      key={`${sectionKey}:${slot.key}`}
                      label={slot.label}
                      fabrics={forSlot}
                      chosen={chosenForJob[slot.key] || []}
                      onToggle={toggle(slot.key)}
                      accessoriesOnly={accessoriesOnly}
                    />
                  );
                })()}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
