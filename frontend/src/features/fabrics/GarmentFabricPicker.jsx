import { useMemo, useRef, useEffect, useState } from 'react';
import { Check, ChevronDown, Inbox, Layers, X } from 'lucide-react';

import { resolveMediaUrl } from '../../services/media';
import { PartTabStrip } from '../designStudio/GarmentPartTabs';
import { ACCESSORY_OPTIONS } from '../designStudio/GarmentPartPicker';

// "m" for cloth, "pcs" for anything counted; the ledger's own unit otherwise.
const unitShort = (f) => (
  !f?.unit || f.unit === 'METER' ? 'm' : f.unit === 'PIECE' ? 'pcs' : String(f.unit).toLowerCase());

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
    <div ref={dropdownRef} style={{ position: 'relative' }}>
      <label style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em',
                      textTransform: 'uppercase', color: 'var(--text-secondary)',
                      display: 'block', marginBottom: '8px' }}>
        Select Accessories (Choose one or more options):
      </label>

      {/* Multi-Select Dropdown Header */}
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        style={{
          width: '100%',
          maxWidth: '440px',
          padding: '10px 12px 10px 14px',
          fontSize: '13px',
          fontWeight: 600,
          borderRadius: '10px',
          border: isOpen ? '1.5px solid #107c41' : '1.5px solid var(--border-color, #d1d5db)',
          background: 'var(--surface-color, #fff)',
          color: selectedCount === 0 ? 'var(--text-secondary)' : 'var(--text-primary)',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '10px',
          textAlign: 'left',
          boxShadow: isOpen ? '0 0 0 3px rgba(16,124,65,0.12)' : 'none',
          transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
        }}
      >
        <span>
          {selectedCount === 0
            ? 'Select accessories from dropdown...'
            : `${selectedCount} Accessor${selectedCount === 1 ? 'y' : 'ies'} Selected`}
        </span>
        <ChevronDown size={16} style={{ flexShrink: 0, color: 'var(--text-secondary)',
                                        transform: isOpen ? 'rotate(180deg)' : 'none',
                                        transition: 'transform 0.15s ease' }} />
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
            maxWidth: '440px',
            marginTop: '6px',
            maxHeight: '280px',
            overflowY: 'auto',
            background: 'var(--surface-color, #ffffff)',
            border: '1px solid var(--border-color, #d1d5db)',
            borderRadius: '12px',
            boxShadow: '0 12px 32px rgba(0,0,0,0.12)',
            padding: '6px',
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
                  gap: '10px',
                  padding: '9px 12px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: isChecked ? 600 : 500,
                  background: isChecked ? 'rgba(16, 124, 65, 0.08)' : 'transparent',
                  color: isChecked ? '#107c41' : 'var(--text-primary)',
                }}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => onToggleKey(opt.key)}
                  style={{ width: '16px', height: '16px', accentColor: '#107c41', cursor: 'pointer', margin: 0 }}
                />
                <span>{opt.label}</span>
              </label>
            );
          })}
        </div>
      )}

      {/* Selected Accessories Pills/Tabs */}
      {selectedKeys.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '12px' }}>
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
                  padding: '6px 6px 6px 14px',
                  borderRadius: '999px',
                  border: isActive ? '1.5px solid #107c41' : '1.5px solid var(--border-color)',
                  background: isActive ? '#107c41' : 'var(--surface-color, #fff)',
                  color: isActive ? '#fff' : 'var(--text-primary)',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  boxShadow: isActive ? '0 2px 8px rgba(16,124,65,0.25)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                <span>{opt.label}</span>
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleKey(key);
                  }}
                  title="Remove accessory"
                  style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                           width: '20px', height: '20px', borderRadius: '50%',
                           background: isActive ? 'rgba(255,255,255,0.22)' : 'var(--surface-inset, #f3f4f6)',
                           color: isActive ? '#fff' : 'var(--text-secondary)' }}
                >
                  <X size={12} />
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
          {[fabric.material_type, fabric.color].filter(Boolean).join(' · ')}
        </span>
        {Number(fabric.selling_price) > 0 && (
          <span style={{ fontWeight: 600, display: 'block', marginTop: '4px', fontSize: '12px' }}>
            ₹{Number(fabric.selling_price).toLocaleString('en-IN')}/{unitShort(fabric)}
          </span>
        )}
        {fabric.available_stock !== undefined && (
          <span style={{ display: 'block', marginTop: '2px', fontSize: '10.5px',
                         color: Number(fabric.available_stock) > 0 ? '#107c41' : 'var(--danger-color, #b91c1c)' }}>
            {Number(fabric.available_stock) > 0
              ? `${Number(fabric.available_stock)} ${unitShort(fabric)} in stock`
              : 'Out of stock'}
          </span>
        )}
      </div>
    </div>
  );
}


/** One part of one garment, and the fabrics filed under it. */
function SlotRow({ label, fabrics, chosen, onToggle, accessoriesOnly = false,
                   slotKey = '', quantities = {}, onQuantity }) {
  const chosenFabrics = fabrics.filter(f => chosen.includes(String(f.id)));
  const itemCategoryName = accessoriesOnly ? 'Accessories' : 'Fabrics';

  return (
    <div style={{ marginTop: '4px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: '16px', fontWeight: 500,
                       color: 'var(--text-primary)' }}>
          {label} {itemCategoryName}
        </span>
        <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 9px', borderRadius: '999px',
                       background: chosen.length > 0 ? 'rgba(16,124,65,0.1)' : 'var(--surface-inset, #f3f4f6)',
                       color: chosen.length > 0 ? '#107c41' : 'var(--text-secondary)' }}>
          {chosen.length > 0 ? `${chosen.length} chosen` : `${fabrics.length} available`}
        </span>
      </div>

      {fabrics.length === 0 ? (
        // Never another part's fabrics as a fallback: an empty part is a gap in
        // the boutique's own filing, and showing it is how that gets noticed.
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
                      padding: '28px 16px', borderRadius: '12px',
                      border: '1px dashed var(--border-color)',
                      background: 'var(--surface-inset, #fafafa)', color: 'var(--text-secondary)' }}>
          <span style={{ width: '40px', height: '40px', borderRadius: '50%', display: 'flex',
                         alignItems: 'center', justifyContent: 'center',
                         background: 'var(--surface-color, #fff)', border: '1px solid var(--border-color)' }}>
            <Inbox size={18} />
          </span>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            No {itemCategoryName.toLowerCase()} available for this part.
          </div>
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
            background: 'rgba(16, 124, 65, 0.04)',
            border: '1px solid rgba(16, 124, 65, 0.35)',
            borderRadius: '12px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '12px',
              paddingBottom: '8px',
              borderBottom: '1px solid rgba(16, 124, 65, 0.18)',
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
                      {[fabric.material_type, fabric.color].filter(Boolean).join(' · ')}
                      {Number(fabric.selling_price) > 0 && ` · ₹${Number(fabric.selling_price).toLocaleString('en-IN')}/${unitShort(fabric)}`}
                    </div>
                  </div>
                  {/* How much of it: the number the ledger reserves at Fabric
                      Confirmed and the cutting table later consumes. */}
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', marginLeft: '6px' }}>
                    <input
                      type="number" min="0" step="0.01" className="form-control"
                      style={{ width: '84px', padding: '4px 8px', fontSize: '12px' }}
                      placeholder={accessoriesOnly ? 'Qty' : 'Metres'}
                      value={quantities[`${slotKey}:${fabric.id}`] ?? ''}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => onQuantity?.(slotKey, String(fabric.id), e.target.value)}
                    />
                    <span style={{ color: 'var(--text-secondary)' }}>{unitShort(fabric)}</span>
                  </label>
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
  quantities = {}, onQuantityChange,
}) {
  const [activeSlotMap, setActiveSlotMap] = useState({});

  // Every active roll the server sent. Stock levels are shown on the card
  // rather than used to hide it: an empty roll can still be the right one,
  // and the reservation reports the shortfall when the order is confirmed.
  const inStock = useMemo(() => fabrics || [], [fabrics]);

  // A roll nobody has filed against any garment yet. Every part offers these,
  // because a boutique that has not started using placements still has to be
  // able to pick fabric -- and their rolls are not "another garment's", they
  // are simply unfiled.
  const unfiled = useMemo(
    () => inStock.filter(f => !(f.placements || []).length), [inStock]);

  const garmentsByKey = useMemo(() => Object.fromEntries(
    (taxonomy?.garments || []).map(g => [g.key, g])), [taxonomy]);

  const [selectedAccessoryMap, setSelectedAccessoryMap] = useState({});
  const [accessorySubtypes, setAccessorySubtypes] = useState({});
  const [accessoryMeasurements, setAccessoryMeasurements] = useState({});

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

        const initialAccessoryKeys = Object.keys(chosenForJob || {});
        const selectedKeys = selectedAccessoryMap[job.key] !== undefined
          ? selectedAccessoryMap[job.key]
          : initialAccessoryKeys;

        const toggleAccessoryKey = (key) => {
          setSelectedAccessoryMap((prev) => {
            const current = prev[job.key] !== undefined ? prev[job.key] : initialAccessoryKeys;
            const isAdding = !current.includes(key);
            const next = isAdding
              ? [...current, key]
              : current.filter(k => k !== key);
            if (isAdding) {
              setActiveSlotMap(sPrev => ({ ...sPrev, [job.key]: key }));
            }
            return { ...prev, [job.key]: next };
          });
        };

        const activeSlotKey = activeSlotMap[job.key] || (selectedKeys.length > 0 ? selectedKeys[0] : null);
        const activeSlotItem = accessoriesOnly
          ? (activeSlotKey ? allSlots.find(s => s.key === activeSlotKey) : null)
          : (allSlots.find(s => s.key === activeSlotKey) || allSlots[0]);

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

        const currentAccOption = accessoriesOnly && activeSlotKey && ACCESSORY_OPTIONS.find(o => o.key === activeSlotKey);

        return (
          // One card per dress, so a saree's fabrics and a blouse's can never
          // read as one list.
          <div className="content-card" key={job.key}>
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <span style={{ width: '34px', height: '34px', borderRadius: '10px', display: 'flex',
                             alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                             background: 'rgba(16,124,65,0.1)', color: '#107c41' }}>
                <Layers size={17} />
              </span>
              <span>{garmentName} {accessoriesOnly ? 'Accessories' : ''}</span>
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
                  <>
                    <div style={{ padding: '16px 18px', borderRadius: '12px',
                                  border: '1px solid var(--border-color)',
                                  background: 'var(--surface-color, #fff)' }}>
                    <AccessoryMultiSelectDropdown
                      options={ACCESSORY_OPTIONS}
                      selectedKeys={selectedKeys}
                      onToggleKey={toggleAccessoryKey}
                      activeKey={activeSlotKey}
                      onSelectActiveKey={(key) => setActiveSlotMap(prev => ({ ...prev, [job.key]: key }))}
                    />
                    </div>
                    {currentAccOption && (
                      <div style={{ margin: '16px 0 20px', padding: '16px 18px', borderRadius: '12px',
                                    border: '1px solid var(--border-color)',
                                    background: 'var(--surface-inset, #fafafa)',
                                    display: 'grid', gap: '16px',
                                    gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))' }}>
                        {currentAccOption.subtypes?.length > 0 && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em',
                                           textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                              {currentAccOption.label} Option / Style:
                            </span>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                              {currentAccOption.subtypes.map(sub => {
                                const activeSub = accessorySubtypes[`${job.key}:${activeSlotKey}`] || currentAccOption.subtypes[0];
                                const isSelected = activeSub === sub;
                                return (
                                  <button
                                    key={sub}
                                    type="button"
                                    onClick={() => setAccessorySubtypes(prev => ({ ...prev, [`${job.key}:${activeSlotKey}`]: sub }))}
                                    style={{
                                      padding: '7px 14px',
                                      fontSize: '12.5px',
                                      borderRadius: '999px',
                                      border: isSelected ? '1.5px solid #107c41' : '1.5px solid var(--border-color)',
                                      background: isSelected ? '#107c41' : 'var(--surface-color, #fff)',
                                      color: isSelected ? '#fff' : 'var(--text-primary)',
                                      fontWeight: 600,
                                      whiteSpace: 'nowrap',
                                      cursor: 'pointer',
                                      boxShadow: isSelected ? '0 2px 8px rgba(16,124,65,0.25)' : 'none',
                                      transition: 'all 0.15s ease',
                                    }}
                                  >
                                    {sub}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {currentAccOption.measurementLabel && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <label style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em',
                                            textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                              {currentAccOption.label} {currentAccOption.measurementLabel}:
                            </label>
                            <input
                              type="text"
                              className="form-control"
                              placeholder={currentAccOption.placeholder || 'Enter measurement or size...'}
                              value={accessoryMeasurements[`${job.key}:${activeSlotKey}`] || ''}
                              onChange={(e) => {
                                const val = e.target.value;
                                setAccessoryMeasurements(prev => ({ ...prev, [`${job.key}:${activeSlotKey}`]: val }));
                              }}
                              style={{ maxWidth: '300px', padding: '9px 12px', fontSize: '13px', borderRadius: '10px' }}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </>
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
                      slotKey={slot.key}
                      quantities={quantities[job.key] || {}}
                      onQuantity={(s, id, q) => onQuantityChange?.(job.key, s, id, q)}
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
