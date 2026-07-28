import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, FolderOpen, Search, Sparkles, X } from 'lucide-react';
import { api } from '../../services/api';

// Seeded catalogue rows store a bare filename rather than a URL. The gallery
// has to render both those and fully-qualified external image URLs.
const MEDIA_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');

const resolveImage = (url) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url) || url.startsWith('data:')) return url;
  if (url.startsWith('/')) return `${MEDIA_BASE}${url}`;
  return `${MEDIA_BASE}/media/${url}`;
};

const SOURCE_LABELS = {
  catalogue: 'Boutique Catalogue',
  past_order: 'Previous Order',
  library: 'Saved Library',
  upload: 'Team Upload',
  favourite: 'Saved Favourite',
  pinterest: 'Pinterest',
  google: 'Google Images'
};

const ATTRIBUTE_LABELS = {
  neck_type: 'Neck Type',
  sleeve: 'Sleeve',
  fabric: 'Fabric',
  embroidery: 'Embroidery',
  occasion: 'Occasion',
  colour: 'Colour',
  fit: 'Fit',
  pattern: 'Pattern'
};

const scoreColour = (score) => {
  if (score >= 80) return { bg: '#e2f5ec', fg: '#107c41' };
  if (score >= 55) return { bg: '#fdf6ed', fg: '#c08030' };
  return { bg: '#f3f4f6', fg: '#6b7280' };
};

function MatchBadge({ score }) {
  const { bg, fg } = scoreColour(score);
  return (
    <div style={{
      position: 'absolute', top: '8px', left: '8px', backgroundColor: bg, color: fg,
      fontSize: '10px', fontWeight: 700, padding: '3px 8px', borderRadius: '99px'
    }}>
      {score}% Match
    </div>
  );
}

function NoPreview() {
  return (
    <div style={{
      height: '100%', display: 'grid', placeItems: 'center',
      color: 'var(--text-secondary)', fontSize: '11px', backgroundColor: '#f9fafb'
    }}>
      No preview
    </div>
  );
}

function DesignCard({ design, isShortlisted, onShortlist, onInspect }) {
  const image = resolveImage(design.image_url);
  // Catalogue rows and imported references both point at URLs that can rot.
  // Without this the browser renders the alt text, which escapes the tile and
  // spills across the card's badges.
  const [broken, setBroken] = useState(false);
  return (
    <div className={`fabric-card ${isShortlisted ? 'selected' : ''}`} style={{ position: 'relative' }}>
      <div className="fabric-image-container" onClick={() => onInspect(design)} style={{ cursor: 'pointer' }}>
        {image && !broken
          ? <img src={image} alt="" onError={() => setBroken(true)} />
          : <NoPreview />}
        <MatchBadge score={design.match_score} />
        {isShortlisted && (
          <div className="fabric-badge"><Check size={14} /></div>
        )}
      </div>
      <div className="fabric-details">
        <span className="fabric-title">{design.title || 'Untitled design'}</span>
        <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginTop: '2px' }}>
          {SOURCE_LABELS[design.source] || design.source}
          {design.designer ? ` • ${design.designer}` : ''}
        </span>
        {design.estimated_price > 0 && (
          <span style={{ fontWeight: 600, display: 'block', margin: '4px 0', fontSize: '12px' }}>
            ₹{Number(design.estimated_price).toLocaleString('en-IN')}
          </span>
        )}
        {design.match_reasons?.length > 0 && (
          <ul style={{ listStyle: 'none', padding: 0, margin: '6px 0 0' }}>
            {design.match_reasons.slice(0, 3).map((reason, i) => (
              <li key={i} style={{ fontSize: '10px', color: '#107c41', display: 'flex', gap: '4px', alignItems: 'flex-start' }}>
                <Check size={10} style={{ marginTop: '2px', flexShrink: 0 }} />
                <span style={{ color: 'var(--text-secondary)' }}>{reason}</span>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          className="btn-secondary"
          style={{ marginTop: '10px', width: '100%', fontSize: '11px', padding: '6px' }}
          onClick={() => onShortlist(design)}
        >
          {isShortlisted ? 'Shortlisted' : 'Add to board'}
        </button>
      </div>
    </div>
  );
}

function AttributePanel({ attributes }) {
  const entries = Object.entries(attributes || {}).filter(([, value]) => value);
  if (entries.length === 0) {
    return <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>No attributes detected for this design.</p>;
  }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '8px' }}>
      {entries.map(([key, value]) => (
        <div key={key} style={{ border: '1px solid var(--border-color)', borderRadius: '6px', padding: '8px' }}>
          <div style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '1px', color: 'var(--text-secondary)' }}>
            {ATTRIBUTE_LABELS[key] || key}
          </div>
          <div style={{ fontSize: '12px', fontWeight: 600 }}>{value}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * The AI Design Studio step of the order wizard.
 *
 * `onBoardChange` hands the parent the board id and the selected design so the
 * wizard can attach it once the order actually exists — the board is built
 * before there is an order to attach it to.
 */
export default function DesignStudio({ customerId, orderInput = {}, onBoardChange, notes, onNotesChange }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [context, setContext] = useState(null);
  const [queries, setQueries] = useState([]);
  const [sources, setSources] = useState([]);
  const [activeSources, setActiveSources] = useState([]);
  const [results, setResults] = useState([]);
  const [keyword, setKeyword] = useState('');
  const [keywords, setKeywords] = useState([]);
  const [board, setBoard] = useState(null);
  const [items, setItems] = useState([]);
  const [inspecting, setInspecting] = useState(null);

  const shortlistedRefs = useMemo(
    () => new Set(items.map((item) => `${item.source}:${item.source_ref}`)),
    [items]
  );
  const selectedItem = items.find((item) => item.is_selected) || null;

  const runSearch = useCallback(async (extraKeywords = keywords, sourceKeys = activeSources) => {
    if (!customerId) return;
    setLoading(true);
    setError('');
    try {
      const data = await api.discoverDesigns({
        customer_id: customerId,
        garment_type: orderInput.garment_type || '',
        occasion: orderInput.occasion || '',
        budget: orderInput.budget || undefined,
        delivery_timeline: orderInput.delivery_timeline || '',
        keywords: extraKeywords,
        sources: sourceKeys.length ? sourceKeys : undefined
      });
      setContext(data.context);
      setQueries(data.queries);
      setSources(data.sources);
      setResults(data.results);
    } catch (err) {
      setError(err.message || 'Design search failed');
    } finally {
      setLoading(false);
    }
  }, [customerId, orderInput.garment_type, orderInput.occasion, orderInput.budget, orderInput.delivery_timeline, keywords, activeSources]);

  useEffect(() => {
    // Deferred by a tick so the search is kicked off after the commit rather
    // than during it, and so rapid changes in the wizard above collapse into a
    // single request. Re-runs only on what the search actually depends on.
    let cancelled = false;
    const timer = setTimeout(() => { if (!cancelled) runSearch(); }, 0);
    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId, orderInput.garment_type, orderInput.occasion]);

  useEffect(() => {
    if (onBoardChange) {
      onBoardChange({ boardId: board?.id || null, selected: selectedItem, approved: board?.status === 'APPROVED' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board?.id, board?.status, selectedItem?.id]);

  const ensureBoard = async () => {
    if (board) return board;
    const created = await api.createDesignBoard(customerId, '', context || {}, queries);
    setBoard(created);
    return created;
  };

  const handleShortlist = async (design) => {
    try {
      const target = await ensureBoard();
      const existing = items.find((i) => i.source === design.source && i.source_ref === design.source_ref);
      if (existing) {
        await api.removeDesignFromBoard(target.id, existing.id);
        setItems((prev) => prev.filter((i) => i.id !== existing.id));
        return;
      }
      const item = await api.addDesignToBoard(target.id, design);
      setItems((prev) => [...prev, item]);
    } catch (err) {
      setError(err.message || 'Could not update the board');
    }
  };

  const handleSelect = async (item) => {
    try {
      const updated = await api.selectBoardDesign(board.id, item.id);
      setBoard(updated);
      setItems(updated.items || []);
    } catch (err) {
      setError(err.message || 'Could not select that design');
    }
  };

  const handleApprove = async () => {
    try {
      const updated = await api.approveDesignBoard(board.id);
      setBoard(updated);
      setItems(updated.items || []);
    } catch (err) {
      setError(err.message || 'Could not approve the board');
    }
  };

  const handleCustomise = async (item, changes) => {
    try {
      const updated = await api.customiseBoardDesign(board.id, item.id, changes);
      setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
      setInspecting(null);
    } catch (err) {
      setError(err.message || 'Could not save the customisation');
    }
  };

  const addKeyword = () => {
    const trimmed = keyword.trim();
    if (!trimmed || keywords.includes(trimmed)) return;
    const next = [...keywords, trimmed];
    setKeywords(next);
    setKeyword('');
    runSearch(next);
  };

  const toggleSource = (key) => {
    const next = activeSources.includes(key)
      ? activeSources.filter((k) => k !== key)
      : [...activeSources, key];
    setActiveSources(next);
    runSearch(keywords, next);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* What the studio knows before it searched anything */}
      {context && (
        <div className="accent-banner" style={{ backgroundColor: '#fdf6ed', borderColor: '#fbeedb', color: '#c08030', alignItems: 'flex-start', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontWeight: 600 }}>
            <Sparkles size={14} />
            <span>Personalised for {context.customer_name || 'this client'}</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
            {[
              context.garment_type,
              context.occasion,
              context.body_type && `${context.body_type} fit`,
              context.budget > 0 && `₹${Number(context.budget).toLocaleString('en-IN')} budget`,
              context.previous_order_count > 0 && `${context.previous_order_count} previous order(s)`
            ].filter(Boolean).join(' • ')}
          </div>
        </div>
      )}

      {/* Search queries the assistant generated, editable by hand */}
      <div className="content-card" style={{ padding: '16px' }}>
        <div className="card-title" style={{ marginBottom: '10px' }}>
          <Search size={16} /> Search Queries
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
          {queries.map((query) => (
            <span key={query} style={{ fontSize: '10px', backgroundColor: '#f3f4f6', padding: '4px 10px', borderRadius: '99px' }}>
              {query}
            </span>
          ))}
          {keywords.map((word) => (
            <span key={word} style={{ fontSize: '10px', backgroundColor: '#e2f5ec', color: '#107c41', padding: '4px 10px', borderRadius: '99px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              {word}
              <X size={10} style={{ cursor: 'pointer' }} onClick={() => {
                const next = keywords.filter((k) => k !== word);
                setKeywords(next);
                runSearch(next);
              }} />
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            className="form-control"
            value={keyword}
            placeholder="Add your own keyword, e.g. peacock motif"
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addKeyword(); } }}
          />
          <button type="button" className="btn-secondary" onClick={addKeyword}>Add</button>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '12px' }}>
          {sources.map((source) => {
            const isOn = activeSources.length === 0 || activeSources.includes(source.key);
            return (
              <button
                key={source.key}
                type="button"
                disabled={!source.available}
                onClick={() => toggleSource(source.key)}
                title={source.available ? '' : 'Not connected'}
                style={{
                  fontSize: '10px', padding: '5px 10px', borderRadius: '99px', cursor: source.available ? 'pointer' : 'not-allowed',
                  border: `1px solid ${isOn && source.available ? 'var(--text-primary)' : 'var(--border-color)'}`,
                  backgroundColor: source.available ? (isOn ? '#fafbfc' : '#fff') : '#f9fafb',
                  color: source.available ? 'var(--text-primary)' : 'var(--text-secondary)'
                }}
              >
                {source.label}{source.available ? '' : ' — not connected'}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div style={{ fontSize: '12px', color: '#b42318', backgroundColor: '#fef3f2', border: '1px solid #fecdca', padding: '10px 12px', borderRadius: '6px' }}>
          {error}
        </div>
      )}

      {/* Gallery */}
      <div>
        <div className="card-title" style={{ marginBottom: '12px' }}>
          <Sparkles size={18} /> Recommended Designs {results.length > 0 && `(${results.length})`}
        </div>
        {loading ? (
          <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '13px' }}>
            Searching your catalogue, past orders and saved library…
          </div>
        ) : results.length === 0 ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', border: '1px dashed var(--border-color)', borderRadius: '8px', color: 'var(--text-secondary)' }}>
            <FolderOpen size={24} style={{ marginBottom: '8px' }} />
            <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>No designs found yet</div>
            <div style={{ fontSize: '11px', marginTop: '2px' }}>Add a keyword above, or upload references to build the boutique library.</div>
          </div>
        ) : (
          <div className="fabrics-grid">
            {results.map((design) => (
              <DesignCard
                key={`${design.source}:${design.source_ref}`}
                design={design}
                isShortlisted={shortlistedRefs.has(`${design.source}:${design.source_ref}`)}
                onShortlist={handleShortlist}
                onInspect={setInspecting}
              />
            ))}
          </div>
        )}
      </div>

      {/* Design board */}
      {items.length > 0 && (
        <div className="content-card" style={{ padding: '16px' }}>
          <div className="card-title" style={{ marginBottom: '12px' }}>
            <Check size={16} /> Design Board ({items.length})
            {board?.status === 'APPROVED' && (
              <span style={{ fontSize: '10px', backgroundColor: '#e2f5ec', color: '#107c41', padding: '2px 8px', borderRadius: '99px', marginLeft: '8px' }}>
                Approved
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '8px' }}>
            {items.map((item) => (
              <div
                key={item.id}
                onClick={() => handleSelect(item)}
                style={{
                  minWidth: '140px', cursor: 'pointer', borderRadius: '8px', padding: '8px',
                  border: `2px solid ${item.is_selected ? 'var(--text-primary)' : 'var(--border-color)'}`,
                  backgroundColor: item.is_selected ? '#fafbfc' : '#fff'
                }}
              >
                {resolveImage(item.image_url) && (
                  <img src={resolveImage(item.image_url)} alt={item.title}
                       style={{ width: '100%', height: '110px', objectFit: 'cover', borderRadius: '4px' }} />
                )}
                <div style={{ fontSize: '11px', fontWeight: 600, marginTop: '6px' }}>{item.title || 'Untitled'}</div>
                <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                  {item.is_selected ? 'Selected' : 'Tap to select'}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '8px', marginTop: '12px', alignItems: 'center' }}>
            <button
              type="button"
              className="btn-primary"
              disabled={!selectedItem || board?.status === 'APPROVED'}
              onClick={handleApprove}
            >
              {board?.status === 'APPROVED' ? 'Design approved' : 'Approve selected design'}
            </button>
            {!selectedItem && (
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                Select a design on the board to approve it.
              </span>
            )}
          </div>
        </div>
      )}

      {/* Inspect + customise */}
      {inspecting && (
        <InspectPanel
          design={inspecting}
          boardItem={items.find((i) => i.source === inspecting.source && i.source_ref === inspecting.source_ref)}
          onClose={() => setInspecting(null)}
          onCustomise={handleCustomise}
        />
      )}

      <div className="form-group">
        <label className="form-label">Design Notes (Optional)</label>
        <textarea
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          className="form-control"
          placeholder="What the client liked — colour, fit, neckline, embroidery, overall vibe"
        />
      </div>
    </div>
  );
}

function InspectPanel({ design, boardItem, onClose, onCustomise }) {
  const [attributes, setAttributes] = useState(boardItem?.attributes || design.attributes || {});
  const [instructions, setInstructions] = useState(boardItem?.tailor_instructions || '');
  const [customerNotes, setCustomerNotes] = useState(boardItem?.customer_notes || '');

  return (
    <div className="content-card" style={{ padding: '16px', border: '2px solid var(--text-primary)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div className="card-title">{design.title || 'Design details'}</div>
        <button type="button" className="btn-secondary" onClick={onClose} style={{ padding: '4px 10px' }}>
          <X size={14} />
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: '16px', marginTop: '12px' }}>
        {resolveImage(design.image_url) && (
          <img src={resolveImage(design.image_url)} alt={design.title}
               style={{ width: '100%', borderRadius: '6px', objectFit: 'cover' }} />
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <AttributePanel attributes={attributes} />

          {design.source_url && (
            <a href={design.source_url} target="_blank" rel="noreferrer"
               style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              Original source ({SOURCE_LABELS[design.source] || design.source})
            </a>
          )}

          {boardItem ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '8px' }}>
                {Object.keys(ATTRIBUTE_LABELS).map((key) => (
                  <div key={key}>
                    <label className="form-label" style={{ fontSize: '10px' }}>{ATTRIBUTE_LABELS[key]}</label>
                    <input
                      className="form-control"
                      value={attributes[key] || ''}
                      onChange={(e) => setAttributes({ ...attributes, [key]: e.target.value })}
                    />
                  </div>
                ))}
              </div>
              <div className="form-group">
                <label className="form-label">Customer notes</label>
                <textarea className="form-control" value={customerNotes}
                          onChange={(e) => setCustomerNotes(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Tailor instructions</label>
                <textarea className="form-control" value={instructions}
                          onChange={(e) => setInstructions(e.target.value)} />
              </div>
              <button
                type="button"
                className="btn-primary"
                onClick={() => onCustomise(boardItem, {
                  attributes,
                  customer_notes: customerNotes,
                  tailor_instructions: instructions
                })}
              >
                Save customisation
              </button>
            </>
          ) : (
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              Add this design to the board to customise it.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
