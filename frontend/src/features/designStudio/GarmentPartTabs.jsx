import { useEffect, useRef, useState } from 'react';
import { ImageOff } from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';

/**
 * A garment's parts as tabs, and the photographs filed under the active one.
 *
 * A boutique looking for a pallu is not looking for a saree: the pallu they
 * want is on one design and the border they want is on another. So selecting a
 * part gathers every photograph of it across the whole garment's designs,
 * rather than making them open twenty sarees to find four pallus.
 *
 * Reads the part-images endpoint, which already answers exactly this question
 * and returns the requested part's photographs only -- a garment with five
 * hundred designs has thousands of part photographs and no screen needs them
 * all. The tab labels and their order come from the garment template's own
 * `design_parts`, so they are the same words, in the same order, that the
 * upload form files photographs under. Nothing here declares a part list of
 * its own: a part the boutique adds to a template appears here by itself.
 *
 * Every declared part gets a tab whether or not anything has been uploaded for
 * it. An empty Pallu tab tells the boutique what is missing, and hiding it
 * would make the gap invisible.
 *
 * `active` is null for the caller's own view, which is the last tab.
 */

const FALLBACK =
  'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400';

/** The tab strip on its own.
 *
 *  Split out because two screens show these tabs over different things: the
 *  library shows the boutique's whole catalogue filed by part, and the order
 *  wizard shows the same parts over photographs a customer can pick. The strip
 *  is the shared half; what sits under it is not.
 */
export function PartTabStrip({ parts = [], active, onChange, allLabel = 'All Designs' }) {
  const strip = useRef(null);

  if (parts.length === 0) return null;

  /** A plain wheel over the strip scrolls it sideways.
   *
   *  A trackpad already sends deltaX and needs nothing; a mouse has only a
   *  vertical wheel, and over a one-row strip that scrolled the page instead.
   *  Claimed only while the strip actually has somewhere to go, so a wheel over
   *  tabs that all fit still scrolls the page.
   */
  const onWheel = (e) => {
    const el = strip.current;
    if (!el || e.deltaX !== 0 || el.scrollWidth <= el.clientWidth) return;
    el.scrollLeft += e.deltaY;
    e.preventDefault();
  };

  return (
    <>
      {/* One row, never wrapped: an eleven-part anarkali would otherwise stack
          three rows of tabs above the grid they filter. The strip is the only
          thing that scrolls sideways -- overscroll-behavior stops the gesture
          chaining out to the page once it reaches an end. Scoped to this
          component's own class, so the shared .tabs-header rules are untouched. */}
      <style>{`
        .at-part-tabs {
          display: flex;
          flex-wrap: nowrap;
          /* width/min-width, not width:100%. A scroll container still offers
             its full content width as its minimum contribution, so eleven
             nowrap tabs pushed the card out through .workspace-panel into the
             wizard's 1fr/360px track: the card grew to 1491px, the page
             scrolled sideways and the sidebar was shoved off screen. width:0
             is what the ancestors measure, so the card is sized by its track
             again; min-width:100% is what the strip is actually drawn at,
             resolved against that settled width. Fixing it here rather than
             putting min-width:0 on .content-card keeps it off every other
             screen those shared classes lay out. */
          width: 0;
          min-width: 100%;
          overflow-x: auto;
          overflow-y: hidden;
          overscroll-behavior-x: contain;
          -webkit-overflow-scrolling: touch;
          scrollbar-width: thin;
          border-bottom: 1px solid var(--border-color);
          margin-bottom: 16px;
        }
        .at-part-tabs::-webkit-scrollbar { height: 4px; }
        .at-part-tabs::-webkit-scrollbar-thumb {
          background: var(--border-color); border-radius: 4px;
        }
        .at-part-tabs .tab-btn {
          flex: 0 0 auto;
          white-space: nowrap;
          padding: 11px 16px;
          font-size: 12.5px;
        }
      `}</style>
      <div className="at-part-tabs" ref={strip} onWheel={onWheel} role="tablist">
        {[...parts, { key: null, label: allLabel }].map((part) => (
          <button
            key={part.key || '__all__'}
            type="button"
            role="tab"
            aria-selected={active === part.key}
            className={`tab-btn ${active === part.key ? 'active' : ''}`}
            onClick={() => onChange(part.key)}
          >
            {part.label}
          </button>
        ))}
      </div>
    </>
  );
}


export default function GarmentPartTabs({
  garmentKey, parts = [], active, onChange, onOpenDesign, allLabel = 'All Designs',
}) {
  // Stamped with the tab it answers, so "still loading" is derived from the
  // stamp not matching rather than from a flag an effect has to clear first.
  const [answer, setAnswer] = useState(null);
  const stamp = `${garmentKey}:${active}`;
  const current = answer?.stamp === stamp ? answer : null;

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    api.getGarmentPartImages({ garment_key: garmentKey, part: active })
      .then((data) => { if (!cancelled) setAnswer({ stamp, images: data.images || [] }); })
      .catch((err) => { if (!cancelled) setAnswer({ stamp, error: err.message }); });
    return () => { cancelled = true; };
  }, [garmentKey, active, stamp]);

  if (parts.length === 0) return null;

  const activeLabel = parts.find((p) => p.key === active)?.label || '';

  return (
    <>
      <PartTabStrip parts={parts} active={active} onChange={onChange} allLabel={allLabel} />

      {active && (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '12px' }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 'var(--text-lg)',
                           fontWeight: 500, color: 'var(--text-primary)' }}>
              {activeLabel}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {current?.images
                ? `${current.images.length} design${current.images.length === 1 ? '' : 's'}`
                : 'loading…'}
            </span>
          </div>

          {current?.error && (
            <div style={{ fontSize: '13px', color: 'var(--danger-color)', padding: '24px 0' }}>
              {current.error}
            </div>
          )}

          {current?.images?.length === 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
                          padding: '30px 0', color: 'var(--text-secondary)' }}>
              <ImageOff size={22} />
              <div style={{ fontSize: '13px' }}>No designs available for this part yet.</div>
            </div>
          )}

          {current?.images?.length > 0 && (
            <div style={{ display: 'grid', gap: '16px',
                          gridTemplateColumns: 'repeat(auto-fill, minmax(min(220px, 100%), 1fr))' }}>
              {current.images.map((image) => (
                // Opens the design the photograph came off, through the same
                // detail panel a card in the design grid opens -- one View,
                // not a second one written for this tab.
                <div key={image.id}
                     role="button"
                     tabIndex={0}
                     onClick={() => onOpenDesign?.(image.design_id)}
                     onKeyDown={(e) => {
                       if (e.key === 'Enter' || e.key === ' ') {
                         e.preventDefault(); onOpenDesign?.(image.design_id);
                       }
                     }}
                     style={{ border: '1px solid var(--border-color)', borderRadius: '10px',
                              overflow: 'hidden', background: 'var(--surface-color)',
                              cursor: onOpenDesign ? 'pointer' : 'default' }}>
                  <div style={{ height: '170px', background: '#222' }}>
                    <img src={resolveMediaUrl(image.image_url, FALLBACK)}
                         alt={image.caption || activeLabel} loading="lazy"
                         style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                  </div>
                  <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ fontSize: '14px', fontWeight: 600, overflow: 'hidden',
                                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {image.design_title || 'Untitled design'}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      {image.designer || 'Unattributed'}
                    </div>
                    {image.caption && (
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden',
                                    textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {image.caption}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
