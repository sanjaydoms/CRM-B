import { useEffect, useMemo, useState } from 'react';
import { Check, Eye, ImageOff, X } from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';

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


/** One photograph, full size. */
function Lightbox({ image, label, onClose }) {
  // Escape closes it. A lightbox opened over a modal is the top layer, so the
  // key has to be handled here rather than left to the modal underneath.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Every click here is stopped before it leaves.
  //
  // The lightbox is painted over the design modal but it is a CHILD of it in
  // the React tree, and the modal's own backdrop closes on click. So a click
  // that closed the lightbox went on bubbling into that handler and shut the
  // modal underneath as well -- one Close, both layers gone, and the customer
  // thrown back out to the design list. Closing the top layer must leave the
  // one beneath it exactly where it was.
  const close = (e) => { e.stopPropagation(); onClose(); };

  return (
    <div onClick={close}
         style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.88)', zIndex: 1100,
                  display: 'flex', flexDirection: 'column', alignItems: 'center',
                  justifyContent: 'center', gap: '14px', padding: '28px' }}>
      <img src={resolveMediaUrl(image.image_url, FALLBACK)} alt={label}
           onClick={(e) => e.stopPropagation()}
           style={{ maxWidth: '100%', maxHeight: '82vh', objectFit: 'contain',
                    borderRadius: '8px', display: 'block' }} />
      <div style={{ color: '#fff', fontSize: '13px', fontWeight: 600 }}
           onClick={(e) => e.stopPropagation()}>{label}</div>
      <button className="btn-secondary" style={{ padding: '5px 14px', fontSize: '12px' }}
              onClick={close}>
        <X size={13} /> Close
      </button>
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
  const [viewing, setViewing] = useState(null);
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
            {images.map((image) => {
              const label = partLabels[image.part] || image.part.replace(/_/g, ' ');
              return (
                <PickCard
                  key={image.id}
                  src={image.image_url}
                  alt={label}
                  height="110px"
                  picked={selection[image.part]?.id === image.id}
                  onClick={() => onChoose(image.part, { ...image, design_title: design.title })}
                  onView={() => setViewing({ image, label })}
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

      {viewing && (
        <Lightbox image={viewing.image} label={viewing.label}
                  onClose={() => setViewing(null)} />
      )}
    </div>
  );
}


export default function GarmentPartPicker({ garmentKey, garmentName, selection = {}, onChange }) {
  const [designs, setDesigns] = useState(null);
  const [template, setTemplate] = useState(null);
  const [error, setError] = useState(null);
  const [openDesign, setOpenDesign] = useState(null);
  const [viewing, setViewing] = useState(null);
  // Bumped by Retry, so the effect below stays the only place the fetch is made.
  const [reloadToken, setReloadToken] = useState(0);

  // Derived rather than stored: a `loading` flag would have to be set
  // synchronously at the top of the effect, which is the cascading-render
  // pattern React warns about.
  const loading = !designs && !error;

  useEffect(() => {
    if (!garmentKey) return undefined;
    let cancelled = false;
    Promise.all([
      api.getDesignLibrary({ template: garmentKey, status: 'ACTIVE' }),
      // Only for the part headings and their order; the designs carry the
      // photographs themselves.
      api.getGarmentTemplate(garmentKey).catch(() => null),
    ])
      .then(([rows, tpl]) => {
        if (cancelled) return;
        setDesigns(rows || []);
        setTemplate(tpl);
      })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [garmentKey, reloadToken]);

  const partOrder = useMemo(
    () => (template?.design_parts || []).map(p => p.key), [template]);
  const partLabels = useMemo(
    () => Object.fromEntries((template?.design_parts || []).map(p => [p.key, p.label])),
    [template]);

  const chosenCount = Object.values(selection).filter(Boolean).length;

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
          {chosenCount > 0
            ? `${chosenCount} part${chosenCount === 1 ? '' : 's'} chosen — parts may come from different designs`
            : 'Open a design to choose its parts'}
        </span>
      </div>

      {loading && (
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '18px 0' }}>
          Loading designs…
        </div>
      )}

      {!loading && designs.length === 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
                      padding: '30px 0', color: 'var(--text-secondary)' }}>
          <ImageOff size={22} />
          <div style={{ fontSize: '13px', fontWeight: 600 }}>
            No {garmentName.toLowerCase()} designs uploaded yet
          </div>
          <div style={{ fontSize: '12px' }}>Add them under Manage Designs.</div>
        </div>
      )}

      {!loading && designs.length > 0 && (
        <div style={{ display: 'grid', gap: '14px',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
          {designs.map((design) => {
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
                onView={() => setViewing({
                  image: { image_url: coverOf(design) }, label: design.title })}
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

      {viewing && !openDesign && (
        <Lightbox image={viewing.image} label={viewing.label}
                  onClose={() => setViewing(null)} />
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
