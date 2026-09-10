import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Eye, ImageOff, X } from 'lucide-react';

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


export default function GarmentPartPicker({ garmentKey, garmentName, selection = {}, onChange }) {
  const [designs, setDesigns] = useState(null);
  const [template, setTemplate] = useState(null);
  const [error, setError] = useState(null);
  const [openDesign, setOpenDesign] = useState(null);
  const [viewIndex, setViewIndex] = useState(null);
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
      // The garment select on the upload form defaults to no garment, so a
      // boutique's own uploads routinely carry none -- and filtering strictly
      // by this garment hid every one of them behind "no designs uploaded
      // yet". They are the boutique's designs either way, so they follow the
      // garment's designs rather than disappearing. Their photographs are
      // filed under 'overall', which every garment has.
      api.getDesignLibrary({ template: 'none', status: 'ACTIVE' }).catch(() => []),
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

      {viewIndex !== null && !openDesign && designs[viewIndex] && (
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
