import { useEffect, useMemo, useRef, useState } from 'react';
import { Camera, Check, ChevronLeft, ChevronRight, Eye, ImageOff, Link as LinkIcon, Upload, X } from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';
import { PartTabStrip } from './GarmentPartTabs';
import { useFabricTaxonomy } from '../fabrics/taxonomy';

/**
 * Choosing a garment's design, part by part.
 *
 * The boutique's designs are what a customer browses: two sarees show as two
 * sarees, each by its overall photograph. Opening one shows everything filed
 * under it -- pallu, border, body, pleat -- and the customer takes the parts
 * they want from it.
 *
 * The selection is a map of part to photograph, not a design id, which is what
 * lets a customer take THIS pallu off one saree and THAT border off another.
 * Opening a second design and picking its border simply overwrites the border
 * slot; the pallu chosen earlier stays.
 *
 * Parts never cross garments: the designs are filtered by this garment's
 * template, and the part headings come from that template's own vocabulary.
 *
 * Needs no customer and no draft. This is the boutique's own library, and the
 * point of the screen is that a customer browses it before giving any details.
 */

const FALLBACK =
  'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400';

/** One selectable photograph.
 *
 *  No hover zoom. A card that grew under the cursor moved its own neighbours
 *  out from under it, so aiming at the picture you wanted became a moving
 *  target -- and a customer comparing eight parts is doing exactly that. The
 *  View button opens the photograph at full size instead, on purpose rather
 *  than by accident of where the mouse rested.
 */
function PickCard({ src, alt, picked, onClick, onView, children, height = '110px' }) {
  return (
    <div
      style={{
        position: 'relative', background: 'var(--surface-color)', borderRadius: '9px',
        border: picked ? '2px solid #107c41' : '1px solid var(--border-color)',
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={onClick}
        style={{ padding: 0, margin: 0, border: 'none', background: 'none', cursor: 'pointer',
                 textAlign: 'left', display: 'block', width: '100%' }}
      >
        <div style={{ height, background: '#222' }}>
          <img src={resolveMediaUrl(src, FALLBACK)} alt={alt} loading="lazy"
               style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        </div>
        {children}
      </button>

      {picked && (
        <span style={{ position: 'absolute', top: '6px', right: '6px', width: '20px', height: '20px',
                       borderRadius: '50%', background: '#107c41', color: '#fff', display: 'flex',
                       alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
          <Check size={12} />
        </span>
      )}

      {onView && (
        // stopPropagation, because this button sits over a card whose own click
        // chooses the part. Without it, looking at a photograph would also
        // select it.
        <button
          type="button"
          title="View full size"
          onClick={(e) => { e.stopPropagation(); onView(); }}
          style={{ position: 'absolute', top: '6px', left: '6px', display: 'flex',
                   alignItems: 'center', gap: '4px', padding: '3px 8px', cursor: 'pointer',
                   borderRadius: '5px', border: 'none', fontSize: '10.5px', fontWeight: 600,
                   background: 'rgba(0,0,0,0.62)', color: '#fff' }}
        >
          <Eye size={11} /> View
        </button>
      )}
    </div>
  );
}


/** One photograph, full size: look at it, choose it, walk the set.
 *
 *  Takes the whole list and an index rather than a single image, because the
 *  point of opening one is usually to compare it with the next. Arrow keys and
 *  the edge buttons move through it; the selection button means a customer who
 *  has enlarged a photograph to decide can act on the decision without closing
 *  it first.
 */
function Lightbox({ items, index, onIndexChange, onClose, isSelected, onToggle }) {
  const item = items[index];
  const many = items.length > 1;

  // Wraps, so the set has no dead end at either edge.
  const step = (delta) => onIndexChange((index + delta + items.length) % items.length);

  useEffect(() => {
    const onKey = (e) => {
      // Every key handled here is swallowed. The lightbox is the top layer, so
      // a press that moves it must not also reach whatever is underneath.
      if (e.key === 'Escape') { e.stopPropagation(); onClose(); }
      else if (e.key === 'ArrowLeft' && many) { e.preventDefault(); e.stopPropagation(); step(-1); }
      else if (e.key === 'ArrowRight' && many) { e.preventDefault(); e.stopPropagation(); step(1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // Every click here is stopped before it leaves.
  //
  // The lightbox is painted over the design modal but it is a CHILD of it in
  // the React tree, and the modal's own backdrop closes on click. So a click
  // that closed the lightbox went on bubbling into that handler and shut the
  // modal underneath as well -- one Close, both layers gone, and the customer
  // thrown back out to the design list. Closing the top layer must leave the
  // one beneath it exactly where it was.
  const close = (e) => { e.stopPropagation(); onClose(); };
  const stop = (fn) => (e) => { e.stopPropagation(); fn(); };

  const arrow = (side) => ({
    position: 'absolute', [side]: '18px', top: '50%', transform: 'translateY(-50%)',
    width: '44px', height: '44px', borderRadius: '50%', border: 'none', cursor: 'pointer',
    background: 'rgba(255,255,255,0.14)', color: '#fff', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
  });

  return (
    <div onClick={close}
         style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.88)', zIndex: 1100,
                  display: 'flex', flexDirection: 'column', alignItems: 'center',
                  justifyContent: 'center', gap: '14px', padding: '28px' }}>

      {many && (
        <>
          <button type="button" title="Previous (left arrow)"
                  onClick={stop(() => step(-1))} style={arrow('left')}>
            <ChevronLeft size={22} />
          </button>
          <button type="button" title="Next (right arrow)"
                  onClick={stop(() => step(1))} style={arrow('right')}>
            <ChevronRight size={22} />
          </button>
        </>
      )}

      <img src={resolveMediaUrl(item.image_url, FALLBACK)} alt={item.label}
           onClick={(e) => e.stopPropagation()}
           style={{ maxWidth: '100%', maxHeight: '74vh', objectFit: 'contain',
                    borderRadius: '8px', display: 'block' }} />

      <div style={{ color: '#fff', fontSize: '13px', fontWeight: 600, textAlign: 'center' }}
           onClick={(e) => e.stopPropagation()}>
        {item.label}
        {many && (
          <span style={{ opacity: 0.6, fontWeight: 400 }}> · {index + 1} of {items.length}</span>
        )}
      </div>

      <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}
           onClick={(e) => e.stopPropagation()}>
        {onToggle && (
          // The same toggle the grid card has: choosing is not a one-way door,
          // so the button says which way it goes rather than only "Select".
          <button
            type="button"
            className={isSelected ? 'btn-secondary' : 'btn-primary'}
            style={{ padding: '6px 16px', fontSize: '12px' }}
            onClick={stop(onToggle)}
          >
            {isSelected ? <><X size={13} /> Remove selection</> : <><Check size={13} /> Select this</>}
          </button>
        )}
        <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: '12px' }}
                onClick={close}>
          <X size={13} /> Close
        </button>
      </div>
    </div>
  );
}


/** Everything filed under one design, in one grid.
 *
 *  Every photograph of the design at once, four to a row, each labelled with
 *  the part it shows. This replaced a section per part: a design carries one
 *  photograph of each part, so eight sections meant eight headings stacked down
 *  the page with a single image under each, and seeing the whole saree meant
 *  scrolling past all of them. The part is a caption on the card, not a heading
 *  above a grid of one.
 */
function DesignModal({ design, partOrder, partLabels, selection, onChoose, onClose }) {
  // An index into `images`, not a copy of one, so the lightbox can step
  // through the set and stay in sync with a selection made from inside it.
  const [viewIndex, setViewIndex] = useState(null);
  // Template order, so the overall shot leads and the rest read the way the
  // boutique declared them. Anything filed under a part the template no longer
  // names still appears, after the declared ones.
  const images = useMemo(() => {
    const rank = new Map(partOrder.map((k, i) => [k, i]));
    return [...(design.images || [])].sort(
      (a, b) => (rank.get(a.part) ?? 999) - (rank.get(b.part) ?? 999));
  }, [design.images, partOrder]);

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}
         onClick={onClose}>
      <style>{`
        .design-part-grid {
          display: grid;
          gap: 14px;
          overflow: visible;
          /* minmax(0, 1fr) rather than a bare 1fr: a grid track's default
             minimum is its content, so a wide image would push the column past
             its share and break the row of four. */
          grid-template-columns: repeat(4, minmax(0, 1fr));
        }
        @media (max-width: 720px) { .design-part-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        @media (max-width: 400px) { .design-part-grid { grid-template-columns: minmax(0, 1fr); } }
      `}</style>
      <div className="content-card"
           style={{ maxWidth: '980px', width: '100%', maxHeight: '90vh', overflowY: 'auto', margin: 0 }}
           onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                      marginBottom: '18px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '19px' }}>{design.title}</h3>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {design.designer_name || 'Unattributed'} · {images.length} photograph
              {images.length === 1 ? '' : 's'} · click any to choose it
            </span>
          </div>
          <button className="btn-secondary" style={{ padding: '4px 10px' }} onClick={onClose}>
            <X size={14} />
          </button>
        </div>

        {images.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '24px 0',
                        color: 'var(--text-secondary)', fontSize: '13px' }}>
            <ImageOff size={16} /> This design has no part photographs yet.
          </div>
        ) : (
          <div className="design-part-grid">
            {images.map((image, i) => {
              const label = partLabels[image.part] || image.part.replace(/_/g, ' ');
              return (
                <PickCard
                  key={image.id}
                  src={image.image_url}
                  alt={label}
                  height="110px"
                  picked={selection[image.part]?.id === image.id}
                  onClick={() => onChoose(image.part,
                    { ...image, design_title: design.title, part_label: label })}
                  onView={() => setViewIndex(i)}
                >
                  <div style={{ padding: '6px 8px' }}>
                    <div style={{ fontSize: '11.5px', fontWeight: 600, overflow: 'hidden',
                                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {label}
                    </div>
                    {selection[image.part]?.id === image.id && (
                      <div style={{ fontSize: '10px', fontWeight: 700, color: '#107c41' }}>
                        chosen
                      </div>
                    )}
                  </div>
                </PickCard>
              );
            })}
          </div>
        )}
      </div>

      {viewIndex !== null && images[viewIndex] && (
        <Lightbox
          items={images.map(img => ({
            image_url: img.image_url,
            label: partLabels[img.part] || img.part.replace(/_/g, ' '),
          }))}
          index={viewIndex}
          onIndexChange={setViewIndex}
          onClose={() => setViewIndex(null)}
          isSelected={selection[images[viewIndex].part]?.id === images[viewIndex].id}
          onToggle={() => onChoose(images[viewIndex].part, {
            ...images[viewIndex],
            design_title: design.title,
            part_label: partLabels[images[viewIndex].part]
                        || images[viewIndex].part.replace(/_/g, ' '),
          })}
        />
      )}
    </div>
  );
}


/** @param ownOnly  Only the customer's own references, part by part: the tabs,
 *                   what they have already given for the open part and the two
 *                   ways to give one. No catalogue browsing, because that is
 *                   what the Design Studio tab next door is for. Same component
 *                   because it is the same garment, the same parts and the same
 *                   {part: reference} slot -- only the catalogue half is off. */
export const ACCESSORY_OPTIONS = [
  { key: 'dori', label: 'Dori' },
  { key: 'tassel_latkan', label: 'Tassel/Latkan' },
  { key: 'border', label: 'Border' },
  { key: 'lace_trim', label: 'Lace/Trim' },
  { key: 'buttons', label: 'Buttons' },
  { key: 'zip', label: 'Zip' },
  { key: 'hooks', label: 'Hooks' },
  { key: 'elastic_drawstring', label: 'Elastic or Draw String' },
  { key: 'padding_cups', label: 'Padding/Cups' },
  { key: 'shoulder_pad', label: 'Shoulder Pad' },
  { key: 'decorative_motifs', label: 'Decorative Motifs' },
  { key: 'other', label: 'Other' },
];

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

export default function GarmentPartPicker({ garmentKey, garmentName, selection = {}, onChange,
                                            ownOnly = false, references = {},
                                            onReferencesChange, taxonomy = null, isFabric = false, accessoriesOnly = false }) {
  const fetchedTaxonomy = useFabricTaxonomy();
  const effectiveTaxonomy = taxonomy || fetchedTaxonomy;

  const [designs, setDesigns] = useState(null);
  const [template, setTemplate] = useState(null);
  const [error, setError] = useState(null);
  const [openDesign, setOpenDesign] = useState(null);
  const [viewIndex, setViewIndex] = useState(null);
  // Bumped by Retry, so the effect below stays the only place the fetch is made.
  const [reloadToken, setReloadToken] = useState(0);

  // Track multi-selected accessory keys when accessoriesOnly is true
  const [selectedAccessoryKeys, setSelectedAccessoryKeys] = useState(() => {
    const existing = Object.keys(references || {});
    return existing.length > 0 ? existing : [];
  });

  const toggleAccessoryKey = (key) => {
    setSelectedAccessoryKeys((prev) => {
      const isAdding = !prev.includes(key);
      const next = isAdding
        ? [...prev, key]
        : prev.filter((k) => k !== key);
      if (isAdding) {
        setPartTab(key);
      }
      return next;
    });
  };

  // Derived rather than stored: a `loading` flag would have to be set
  // synchronously at the top of the effect, which is the cascading-render
  // pattern React warns about.
  const loading = !designs && !error;

  useEffect(() => {
    if (!garmentKey) return undefined;
    let cancelled = false;
    Promise.all([
      // Nothing browses the catalogue in ownOnly mode, so it is not fetched.
      ownOnly ? [] : api.getDesignLibrary({ template: garmentKey, status: 'ACTIVE' }),
      // The garment select on the upload form defaults to no garment, so a
      // boutique's own uploads routinely carry none -- and filtering strictly
      // by this garment hid every one of them behind "no designs uploaded
      // yet". They are the boutique's designs either way, so they follow the
      // garment's designs rather than disappearing. Their photographs are
      // filed under 'overall', which every garment has.
      ownOnly ? [] : api.getDesignLibrary({ template: 'none', status: 'ACTIVE' }).catch(() => []),
      // Only for the part headings and their order; the designs carry the
      // photographs themselves.
      api.getGarmentTemplate(garmentKey).catch(() => null),
    ])
      .then(([rows, untagged, tpl]) => {
        if (cancelled) return;
        setDesigns([...(rows || []), ...(untagged || [])]);
        setTemplate(tpl);
      })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [garmentKey, reloadToken, ownOnly]);

  const partOrder = useMemo(
    () => (template?.design_parts || []).map(p => p.key), [template]);
  const partLabels = useMemo(
    () => Object.fromEntries((template?.design_parts || []).map(p => [p.key, p.label])),
    [template]);

  // Every photograph the boutique has for this garment, filed under its part
  // and carrying the design it came off. Built from the designs already
  // fetched above rather than from a second call: a design arrives with its
  // images, so grouping them is a derive, and doing it here keeps the
  // untagged uploads the fetch deliberately merges in.
  const imagesByPart = useMemo(() => {
    const map = new Map();
    (designs || []).forEach((design) => {
      (design.images || []).forEach((image) => {
        if (!map.has(image.part)) map.set(image.part, []);
        // design_id rather than the design itself: the chosen photograph is
        // written into the order draft, so it stays a flat row of scalars, and
        // it is the field the design list already reads back to mark a design
        // the customer has taken a part from.
        map.get(image.part).push({ ...image, design_id: design.id,
                                   design_title: design.title,
                                   designer_name: design.designer_name });
      });
    });
    return map;
  }, [designs]);

  const garmentsByKey = useMemo(() => Object.fromEntries(
    (effectiveTaxonomy?.garments || []).map(g => [g.key, g])), [effectiveTaxonomy]);

  // The tabs: every part the template or fabric taxonomy declares.
  const tabParts = useMemo(() => {
    if (accessoriesOnly) {
      return ACCESSORY_OPTIONS;
    }
    if (isFabric && effectiveTaxonomy && garmentKey) {
      const spec = garmentsByKey[garmentKey];
      if (spec?.sections?.length) {
        let slotsFromTaxonomy = spec.sections.flatMap(section => {
          const sectionPrefix = (spec.sections.length > 1 && section.label) ? `${section.label} - ` : '';
          return (section.slots || []).map(slot => ({
            key: slot.key,
            label: `${sectionPrefix}${slot.label}`,
          }));
        });
        if (slotsFromTaxonomy.length > 0) {
          return slotsFromTaxonomy;
        }
      }
    }

    const declared = template?.design_parts || [];
    const extra = [...imagesByPart.keys()]
      .filter(key => !declared.some(p => p.key === key))
      .map(key => ({ key, label: key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }));
    if (ownOnly && !declared.length && !extra.length) {
      return [{ key: 'overall', label: 'Overall Design' }];
    }
    return [...declared, ...extra];
  }, [template, imagesByPart, ownOnly, isFabric, accessoriesOnly, effectiveTaxonomy, garmentKey, garmentsByKey]);

  // Which tab is showing. `null` is the design list this screen has always
  // opened on, and it is the last tab; anything else is a part. Derived, so a
  // garment whose template has not loaded yet -- or a part it does not declare
  // -- falls back to its own first part rather than an empty grid.
  const [partTab, setPartTab] = useState(undefined);
  const [linkDraft, setLinkDraft] = useState('');
  const [addingLink, setAddingLink] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const ownFileRef = useRef(null);
  const ownCamRef = useRef(null);
  const videoRef = useRef(null);
  const [camStream, setCamStream] = useState(null);
  // Cleanup only -- nothing is set here, so the camera cannot be left running
  // by a customer who navigates away with the modal open.
  useEffect(() => () => camStream?.getTracks().forEach(track => track.stop()), [camStream]);

  const openPart = partTab === null ? null
    : accessoriesOnly
    ? (selectedAccessoryKeys.includes(partTab) ? partTab : (selectedAccessoryKeys[0] || null))
    : (tabParts.some(p => p.key === partTab) ? partTab : (tabParts[0]?.key ?? null));
  const openPartLabel = tabParts.find(p => p.key === openPart)?.label || '';
  const partShots = openPart ? (imagesByPart.get(openPart) || []) : [];

  // The overall shot stands for the whole garment rather than one detail of
  // it, so View on one opens that design's own gallery -- every part filed
  // under it, pallu and border and body together -- instead of a bigger copy
  // of the photograph already on screen. Every other tab is showing a single
  // part, where full size is exactly what a customer wants from View.
  //
  // startsWith, because the key is the garment's own: overall_saree_design,
  // overall_anarkali_design, overall_design on bottom wear, and a bare
  // 'overall' on anything uploaded without a garment. Same test coverOf makes
  // a few lines down. Garments whose template declares no overall part -- gown,
  // suit, sherwani -- simply never take this branch.
  const overallTab = Boolean(openPart && openPart.startsWith('overall'));

  // Everything the customer has handed over for THIS part -- a list, because
  // describing a pallu takes three photographs and a link as often as it takes
  // one, and deciding which single one of those counts is the boutique's job
  // rather than something this form should force at the moment they are given.
  //
  // Kept apart from `selection`, which stays exactly what it was: the one
  // chosen photograph per part that the summary, the modal and the board item
  // at Confirm all read.
  const ownRefs = (openPart && references[openPart]) || [];

  const putRefs = (list) => onReferencesChange?.({ ...references, [openPart]: list });

  const addRefs = (added) => putRefs([...ownRefs, ...added]);

  const removeRef = (id) => {
    const left = ownRefs.filter(r => r.id !== id);
    // The part's key goes with its last reference rather than sitting there as
    // an empty list nobody put anything in.
    const next = { ...references };
    if (left.length) next[openPart] = left; else delete next[openPart];
    onReferencesChange?.(next);
  };

  const addReferenceLink = () => {
    const typed = linkDraft.trim();
    if (!typed) return;
    // A link pasted without its scheme ("pinterest.com/pin/...") is a relative
    // path to resolveMediaUrl, which would hang it off the media host and show
    // a broken card. What the customer meant is a site.
    const url = /^https?:\/\//i.test(typed) ? typed : `https://${typed}`;
    if (ownRefs.some(r => r.source_url === url)) { setLinkDraft(''); return; }
    addRefs([{
      id: `link:${url}`, part: openPart, part_label: openPartLabel,
      image_url: url, source_url: url, source: 'customer_link',
      design_title: url.replace(/^https?:\/\//i, '').slice(0, 60),
    }]);
    setLinkDraft('');
    // The box stays open: a customer with one link usually has another.
  };

  const uploadFiles = async (files) => {
    if (!files.length) return;
    setUploading(true);
    setUploadError(null);
    try {
      // One request per file, all in flight together. Promise.all rather than a
      // loop with await, so picking eight photographs is one wait and not eight.
      const stored = await Promise.all(files.map(async (file) => {
        const { image_url } = await api.uploadReferenceImage(file);
        return {
          id: `upload:${image_url}`, part: openPart, part_label: openPartLabel,
          image_url, source: 'customer_upload', design_title: file.name,
        };
      }));
      addRefs(stored);
    } catch (err) {
      // Whatever did upload is lost with the batch. Said plainly rather than
      // leaving the customer to wonder which of the eight landed.
      setUploadError(`${err.message} — please add those pictures again.`);
    } finally {
      setUploading(false);
    }
  };

  const uploadReference = (e) => {
    const files = [...(e.target.files || [])];
    e.target.value = '';        // so re-picking the same file fires change again
    uploadFiles(files);
  };

  /** Open the camera.
   *
   *  Not the `capture` attribute on the file input, which is what this used to
   *  be: capture is honoured by mobile browsers ONLY. On a desktop it is
   *  ignored outright and the button opened the ordinary file picker -- which
   *  is exactly what a boutique on a laptop saw when they pressed Take photo.
   *
   *  getUserMedia works on both, so it is the one path. Where it cannot run --
   *  no permission, no camera, or a page served over plain HTTP, which browsers
   *  refuse outright -- it falls back to the capture input, so a phone still
   *  gets its native camera and nothing gets worse than it was.
   */
  const openCamera = async () => {
    setUploadError(null);
    if (!navigator.mediaDevices?.getUserMedia) { ownCamRef.current?.click(); return; }
    try {
      setCamStream(await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }, audio: false }));
    } catch {
      ownCamRef.current?.click();
    }
  };

  const closeCamera = () => {
    // Every track stopped, or the camera light stays on after the modal shuts.
    camStream?.getTracks().forEach(track => track.stop());
    setCamStream(null);
  };

  const capturePhoto = async () => {
    const video = videoRef.current;
    if (!video?.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const blob = await new Promise(done => canvas.toBlob(done, 'image/jpeg', 0.92));
    closeCamera();
    if (!blob) return;
    await uploadFiles([
      new File([blob], `${openPart || 'reference'}-${Date.now()}.jpg`, { type: 'image/jpeg' })]);
  };

  const chosenCount = Object.values(selection).filter(Boolean).length;
  const referencedParts = Object.values(references).filter(list => list?.length).length;
  const referenceCount = Object.values(references)
    .reduce((n, list) => n + (list?.length || 0), 0);

  // Clicking the chosen photograph again clears that part, so a customer can
  // undo without having to pick a different one instead.
  const choose = (part, image) => {
    const next = { ...selection };
    if (next[part]?.id === image.id) delete next[part];
    else next[part] = image;
    onChange?.(next);
  };

  /** The photograph that represents a whole design in the list: its overall
   *  shot where it has one, its cover otherwise. */
  const coverOf = (design) => {
    const images = design.images || [];
    const overall = images.find(i => i.part.startsWith('overall'));
    return (overall || images[0])?.image_url || design.image_url;
  };

  if (!garmentKey) return null;

  if (error) {
    return (
      <div className="content-card" style={{ color: '#c0392b', fontSize: '12.5px' }}>
        {error}
        <button className="btn-secondary" style={{ marginLeft: '10px', padding: '3px 9px', fontSize: '11px' }}
                onClick={() => { setDesigns(null); setError(null); setReloadToken(t => t + 1); }}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="content-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                    flexWrap: 'wrap', gap: '8px', marginBottom: '14px' }}>
        <div className="card-title" style={{ margin: 0 }}>{garmentName}</div>
        <span style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
          {ownOnly
            ? (referenceCount > 0
                ? `${referenceCount} reference${referenceCount === 1 ? '' : 's'} across ${referencedParts} part${referencedParts === 1 ? '' : 's'}`
                : (isFabric ? 'Add your own photos for each part' : 'Add your own photos or links for each part'))
            : chosenCount > 0
            ? `${chosenCount} part${chosenCount === 1 ? '' : 's'} chosen — parts may come from different designs`
            : (openPart ? 'Click a photograph to choose this part'
                        : 'Open a design to choose its parts')}
        </span>
      </div>

      {/* This garment's parts. Every photograph filed under the open one, taken
          across every design in the library, so choosing a pallu is one tab
          rather than opening twenty sarees. The last tab is the design list
          this screen has always opened on. */}
      {!loading && (
        accessoriesOnly ? (
          <AccessoryMultiSelectDropdown
            options={ACCESSORY_OPTIONS}
            selectedKeys={selectedAccessoryKeys}
            onToggleKey={toggleAccessoryKey}
            activeKey={openPart || tabParts[0]?.key}
            onSelectActiveKey={(key) => { setPartTab(key); setViewIndex(null); }}
          />
        ) : (
          <PartTabStrip parts={tabParts} active={openPart}
                        allLabel={ownOnly ? null : 'All Designs'}
                        onChange={(part) => { setPartTab(part); setViewIndex(null); }} />
        )
      )}

      {!loading && accessoriesOnly && selectedAccessoryKeys.length === 0 && (
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '4px 0 18px' }}>
          Select an accessory from the dropdown above to add or upload items.
        </div>
      )}

      {loading && (
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '18px 0' }}>
          Loading designs…
        </div>
      )}

      {/* The customer's own reference for THIS part -- ownOnly, so only in the
          References tab. The Design Studio tab is for picking off the
          boutique's catalogue and offers no upload of its own.
          The upload is stored on the spot because the wizard's draft is JSON
          and cannot carry a file; the link is kept as it was typed. */}
      {!loading && ownOnly && openPart && (() => {
        const isAlreadyFabric = /fabric/i.test(openPartLabel);
        const partFabricLabel = isFabric
          ? (isAlreadyFabric ? openPartLabel : `${openPartLabel} Fabric`)
          : openPartLabel;
        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px',
                        marginBottom: '14px' }}>
            <button type="button" className="btn-secondary" disabled={uploading}
                    style={{ padding: '5px 11px', fontSize: '11.5px' }}
                    onClick={() => ownFileRef.current?.click()}>
              <Upload size={12} /> {uploading ? 'Uploading…' : `Upload ${partFabricLabel} photos`}
            </button>
            <button type="button" className="btn-secondary" disabled={uploading}
                    style={{ padding: '5px 11px', fontSize: '11.5px' }}
                    onClick={openCamera}>
              <Camera size={12} /> Take photo
            </button>
            {!isFabric && (
              <button type="button" className="btn-secondary"
                      style={{ padding: '5px 11px', fontSize: '11.5px' }}
                      onClick={() => setAddingLink(v => !v)}>
                <LinkIcon size={12} /> Add reference link
              </button>
            )}
            {/* multiple, because a customer describing one part sends several
                pictures of it. Each becomes its own reference for this part. */}
            <input ref={ownFileRef} type="file" accept="image/*" multiple hidden
                   onChange={uploadReference} />
            {/* capture, so a phone opens the camera rather than the gallery. One
                shot at a time, which is what a camera gives; both land in the
                same list for this part through the same handler. */}
            <input ref={ownCamRef} type="file" accept="image/*" capture="environment" hidden
                   onChange={uploadReference} />

            {!isFabric && addingLink && (
              <>
                <input className="form-control" value={linkDraft} autoFocus
                       onChange={(e) => setLinkDraft(e.target.value)}
                       onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addReferenceLink(); } }}
                       placeholder={`Link to a ${partFabricLabel.toLowerCase()} you like — add as many as you want`}
                       style={{ flex: '1 1 240px', maxWidth: '340px', padding: '5px 9px', fontSize: '11.5px' }} />
                <button type="button" className="btn-primary" disabled={!linkDraft.trim()}
                        style={{ padding: '5px 11px', fontSize: '11.5px' }}
                        onClick={addReferenceLink}>
                  Add
                </button>
              </>
            )}

            {uploadError && (
              <span role="alert" style={{ fontSize: '11.5px', color: 'var(--danger-color, #c0392b)' }}>
                {uploadError}
              </span>
            )}
          </div>
        );
      })()}

      {!loading && ownOnly && openPart && ownRefs.length > 0 && (
        <div style={{ display: 'grid', gap: '14px', marginBottom: '16px',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
          {ownRefs.map((ref) => (
            <div key={ref.id} style={{ position: 'relative' }}>
              <PickCard
                src={ref.image_url}
                alt={openPartLabel}
                height="150px"
                picked
                // The card itself opens it; removing is the × in the corner, so
                // a mis-click looks rather than deletes.
                onClick={() => window.open(
                  ref.source_url || resolveMediaUrl(ref.image_url, FALLBACK), '_blank', 'noopener')}
              >
                <div style={{ padding: '8px 10px' }}>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, overflow: 'hidden',
                                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {ref.design_title}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                    {ref.source === 'customer_link' ? 'Your link' : 'Your photo'}
                  </div>
                </div>
              </PickCard>
              <button
                type="button"
                title="Remove this reference"
                onClick={() => removeRef(ref.id)}
                style={{ position: 'absolute', top: '6px', right: '6px', width: '20px',
                         height: '20px', borderRadius: '50%', border: 'none', cursor: 'pointer',
                         background: 'rgba(0,0,0,0.62)', color: '#fff', padding: 0,
                         display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      {!loading && !ownOnly && openPart && partShots.length === 0 && designs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
                      padding: '30px 0', color: 'var(--text-secondary)' }}>
          <ImageOff size={22} />
          <div style={{ fontSize: '13px' }}>No {openPartLabel} references available yet.</div>
        </div>
      )}

      {!loading && ownOnly && openPart && ownRefs.length === 0 && (
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '4px 0 18px' }}>
          No {(() => {
            const isAlreadyFabric = /fabric/i.test(openPartLabel);
            const partFabricLabel = isFabric
              ? (isAlreadyFabric ? openPartLabel : `${openPartLabel} Fabric`)
              : openPartLabel;
            return partFabricLabel.toLowerCase();
          })()} references yet — add as many photos{isFabric ? '' : ' and links'} as you like.
        </div>
      )}

      {!loading && openPart && partShots.length > 0 && (
        <div style={{ display: 'grid', gap: '14px',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
          {partShots.map((image, i) => (
            // The same card, the same choose() and the same View the design
            // modal uses -- this tab is another way into the one selection,
            // not a second one.
            <PickCard
              key={image.id}
              src={image.image_url}
              alt={openPartLabel}
              height="150px"
              picked={selection[openPart]?.id === image.id}
              onClick={() => choose(openPart, { ...image, design_title: image.design_title,
                                                part_label: openPartLabel })}
              onView={() => {
                const design = overallTab
                  && (designs || []).find(d => String(d.id) === String(image.design_id));
                // Falls through to the plain full-size view whenever the design
                // behind the photograph is not in hand.
                if (design) setOpenDesign(design); else setViewIndex(i);
              }}
            >
              <div style={{ padding: '8px 10px' }}>
                <div style={{ fontSize: '12.5px', fontWeight: 600, overflow: 'hidden',
                              textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {image.design_title || 'Untitled design'}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                  {image.designer_name || 'Unattributed'}
                  {selection[openPart]?.id === image.id && (
                    <span style={{ color: '#107c41', fontWeight: 700 }}> · chosen</span>
                  )}
                </div>
              </div>
            </PickCard>
          ))}
        </div>
      )}

      {!loading && !ownOnly && designs.length === 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
                      padding: '30px 0', color: 'var(--text-secondary)' }}>
          <ImageOff size={22} />
          <div style={{ fontSize: '13px', fontWeight: 600 }}>
            No {garmentName.toLowerCase()} designs uploaded yet
          </div>
          <div style={{ fontSize: '12px' }}>Add them under Manage Designs.</div>
        </div>
      )}

      {!loading && !openPart && designs.length > 0 && (
        <div style={{ display: 'grid', gap: '14px',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
          {designs.map((design, i) => {
            // How many of this customer's chosen parts came off this design --
            // so a design they have already taken something from is marked.
            const taken = Object.values(selection)
              .filter(img => img && String(img.design_id) === String(design.id)).length;
            return (
              <PickCard
                key={design.id}
                src={coverOf(design)}
                alt={design.title}
                picked={taken > 0}
                height="150px"
                onClick={() => setOpenDesign(design)}
                onView={() => setViewIndex(i)}
              >
                <div style={{ padding: '8px 10px' }}>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, overflow: 'hidden',
                                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {design.title}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                    {(design.images || []).length} photograph
                    {(design.images || []).length === 1 ? '' : 's'}
                    {taken > 0 && (
                      <span style={{ color: '#107c41', fontWeight: 700 }}> · {taken} chosen</span>
                    )}
                  </div>
                </div>
              </PickCard>
            );
          })}
        </div>
      )}

      {/* Full size, walking whichever set is on screen: the part's photographs
          under a part tab, the design covers under the design list. Selecting
          from inside it is the same choose() the card behind it calls. */}
      {camStream && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.88)', zIndex: 1100,
                      display: 'flex', flexDirection: 'column', alignItems: 'center',
                      justifyContent: 'center', gap: '14px', padding: '28px' }}
             onClick={closeCamera}>
          <video
            autoPlay playsInline muted
            // srcObject cannot be set from JSX, and a ref callback sets it the
            // moment the element exists rather than a render later.
            ref={(el) => { videoRef.current = el; if (el && el.srcObject !== camStream) el.srcObject = camStream; }}
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: '100%', maxHeight: '70vh', borderRadius: '8px', background: '#000' }}
          />
          <div style={{ display: 'flex', gap: '10px' }} onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn-primary" disabled={uploading}
                    style={{ padding: '6px 16px', fontSize: '12px' }}
                    onClick={capturePhoto}>
              <Camera size={13} /> {uploading ? 'Saving…' : `Capture ${openPartLabel}`}
            </button>
            <button type="button" className="btn-secondary"
                    style={{ padding: '6px 14px', fontSize: '12px' }} onClick={closeCamera}>
              <X size={13} /> Cancel
            </button>
          </div>
        </div>
      )}

      {viewIndex !== null && !openDesign && openPart && partShots[viewIndex] && (
        <Lightbox
          items={partShots.map(img => ({
            image_url: img.image_url,
            label: `${openPartLabel} · ${img.design_title || 'Untitled design'}`,
          }))}
          index={viewIndex}
          onIndexChange={setViewIndex}
          onClose={() => setViewIndex(null)}
          isSelected={selection[openPart]?.id === partShots[viewIndex].id}
          onToggle={() => choose(openPart, {
            ...partShots[viewIndex],
            design_title: partShots[viewIndex].design_title,
            part_label: openPartLabel,
          })}
        />
      )}

      {viewIndex !== null && !openDesign && !openPart && designs[viewIndex] && (
        <Lightbox
          items={designs.map(d => ({ image_url: coverOf(d), label: d.title }))}
          index={viewIndex}
          onIndexChange={setViewIndex}
          onClose={() => setViewIndex(null)}
        />
      )}

      {openDesign && (
        <DesignModal
          design={openDesign}
          partOrder={partOrder}
          partLabels={partLabels}
          selection={selection}
          onChoose={choose}
          onClose={() => setOpenDesign(null)}
        />
      )}
    </div>
  );
}


/**
 * What the customer has chosen so far, across every dress on the order.
 *
 * One section per garment, stacked; inside each, the chosen photographs in a
 * row. The order form is long and a choice made under Saree scrolls out of
 * sight the moment the customer opens Blouse, so this is where they see the
 * whole outfit at once before moving on.
 *
 * Reads the same `job.design.parts` the pickers write, so there is nothing to
 * keep in step -- it is a view of the selection, not a copy of it.
 */
export function SelectedDesignSummary({ garmentJobs = [], onClear }) {
  // Which picture the full-size view is showing, as an index into the flat
  // list below. Null when it is closed.
  const [viewIndex, setViewIndex] = useState(null);

  const sections = garmentJobs
    .map(job => ({
      key: job.key,
      name: job.template?.name || job.key,
      picks: Object.entries(job.design?.parts || {})
        .filter(([, image]) => image)
        .map(([part, image]) => ({ part, image })),
    }))
    .filter(section => section.picks.length > 0);

  if (sections.length === 0) return null;

  const total = sections.reduce((n, s) => n + s.picks.length, 0);

  // Every chosen photograph, in the order the sections read, so the arrows walk
  // the whole outfit rather than stopping at the end of a garment. The label
  // carries the garment too -- 'Border Design' alone is ambiguous once a saree
  // and a dupatta both have one.
  // Each entry keeps the section and part it came from, so finding the one a
  // View button belongs to is a lookup rather than a re-walk of the sections.
  const viewItems = sections.flatMap(section =>
    section.picks.map(({ part, image }) => ({
      sectionKey: section.key,
      part,
      image_url: image.image_url,
      label: `${image.part_label || part.replace(/_/g, ' ')} · ${section.name}`,
    })));

  const flatIndexOf = (sectionKey, part) =>
    viewItems.findIndex(i => i.sectionKey === sectionKey && i.part === part);

  return (
    <div className="content-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                    flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
        <div className="card-title" style={{ margin: 0 }}>Your selected designs</div>
        <span style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
          {total} design{total === 1 ? '' : 's'} across {sections.length} garment
          {sections.length === 1 ? '' : 's'}
        </span>
      </div>

      {sections.map((section) => (
        <div key={section.key} style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '10px',
                        borderBottom: '1px solid var(--border-color)', paddingBottom: '5px' }}>
            <span style={{ fontSize: '13.5px', fontWeight: 700 }}>{section.name}</span>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              {section.picks.length} chosen
            </span>
          </div>

          {/* A row that scrolls sideways rather than wrapping: an eleven-part
              anarkali would otherwise push the next garment's section off the
              bottom of the screen, which is the thing this summary exists to
              stop. */}
          <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '4px' }}>
            {section.picks.map(({ part, image }) => (
              <div key={part} style={{ width: '112px', flexShrink: 0, position: 'relative' }}>
                <div style={{ height: '104px', background: '#222', borderRadius: '8px',
                              overflow: 'hidden', border: '1px solid var(--border-color)' }}>
                  <img src={resolveMediaUrl(image.image_url, FALLBACK)}
                       alt={image.part_label || part} loading="lazy"
                       style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                </div>
                <button
                  type="button"
                  title="View full size"
                  onClick={() => setViewIndex(flatIndexOf(section.key, part))}
                  style={{ position: 'absolute', top: '5px', left: '5px', display: 'flex',
                           alignItems: 'center', gap: '3px', padding: '3px 7px', cursor: 'pointer',
                           borderRadius: '5px', border: 'none', fontSize: '10px', fontWeight: 600,
                           background: 'rgba(0,0,0,0.62)', color: '#fff' }}
                >
                  <Eye size={10} /> View
                </button>
                {onClear && (
                  <button
                    type="button"
                    title="Remove this choice"
                    onClick={() => onClear(section.key, part)}
                    style={{ position: 'absolute', top: '5px', right: '5px', width: '19px',
                             height: '19px', borderRadius: '50%', border: 'none', cursor: 'pointer',
                             background: 'rgba(0,0,0,0.62)', color: '#fff', fontSize: '11px',
                             lineHeight: '19px', padding: 0 }}
                  >
                    <X size={11} />
                  </button>
                )}
                <div style={{ fontSize: '11px', fontWeight: 600, marginTop: '5px',
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {image.part_label || part.replace(/_/g, ' ')}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--text-secondary)',
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {image.design_title || ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {viewIndex !== null && viewItems[viewIndex] && (
        <Lightbox
          items={viewItems}
          index={viewIndex}
          onIndexChange={setViewIndex}
          onClose={() => setViewIndex(null)}
        />
      )}
    </div>
  );
}
