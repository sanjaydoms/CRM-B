import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, Clock, Edit2, Eye, Plus, Search, ShoppingBag, Trash2, X } from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';
import DesignUpload from './DesignUpload';

/**
 * The boutique's design library.
 *
 * Replaces a flat grid of every design in the boutique. That works at fifty
 * designs and stops working at five hundred: the owner cannot find anything, and
 * the page loads the whole catalogue to show the first row of it.
 *
 * So the library opens on counts per garment, and only the chosen category is
 * fetched. Filters use the same vocabulary the order form does, which is what
 * makes "show me the elbow-sleeve wedding lehengas" a query rather than
 * scrolling.
 */

const CARD_IMAGE_FALLBACK =
  'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400';

const STATUS_COLOURS = {
  ACTIVE: { bg: 'rgba(52, 211, 153, 0.15)', fg: '#34d399' },
  PENDING: { bg: 'rgba(251, 191, 36, 0.15)', fg: '#fbbf24' },
  DRAFT: { bg: 'rgba(156, 163, 175, 0.15)', fg: '#9ca3af' },
  ARCHIVED: { bg: 'rgba(156, 163, 175, 0.15)', fg: '#9ca3af' },
};

// Only the boutique's own catalogue rows are editable through the catalogue
// endpoints; an imported pin or a studio upload is not a catalogue entry.
const EDITABLE_SOURCES = ['catalogue', 'suggestion'];

const formatDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '';

function Filters({ value, onChange, designers, collections }) {
  const set = (key) => (e) => onChange({ ...value, [key]: e.target.value });

  const select = (key, label, options) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
      {label}
      <select className="form-control" style={{ padding: '6px 8px', fontSize: '12px' }}
              value={value[key] || ''} onChange={set(key)}>
        <option value="">Any</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
      gap: '12px', padding: '16px', border: '1px solid var(--border-color)',
      borderRadius: '8px', marginBottom: '20px', alignItems: 'end',
    }}>
      <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
        Search
        <span style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <Search size={13} style={{ position: 'absolute', left: '8px', color: 'var(--text-muted)' }} />
          <input className="form-control" style={{ padding: '6px 8px 6px 26px', fontSize: '12px' }}
                 value={value.search || ''} onChange={set('search')} placeholder="Design name" />
        </span>
      </label>

      {select('designer', 'Designer', designers.map(d => [d.id, `${d.name} (${d.design_count})`]))}
      {select('collection', 'Collection', collections.map(c => [c.id, `${c.name} (${c.design_count})`]))}
      {select('occasion', 'Occasion', [
        ['wedding', 'Wedding'], ['reception', 'Reception'], ['festive', 'Festive'],
        ['party', 'Party'], ['daily', 'Daily'],
      ])}
      {select('sleeve_length', 'Sleeve', [
        ['sleeveless', 'Sleeveless'], ['cap', 'Cap'], ['short', 'Short'],
        ['elbow', 'Elbow'], ['three_quarter', '3/4'], ['full', 'Full'],
      ])}
      {select('status', 'Status', [
        ['ACTIVE', 'Active'], ['PENDING', 'Pending approval'],
        ['DRAFT', 'Draft'], ['ARCHIVED', 'Archived'],
      ])}
      {select('ordering', 'Sort by', [
        ['newest', 'Newest'], ['oldest', 'Oldest'], ['most_viewed', 'Most viewed'],
        ['most_ordered', 'Most ordered'], ['name', 'Name'],
      ])}

      <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
        Price
        <span style={{ display: 'flex', gap: '4px' }}>
          <input className="form-control" style={{ padding: '6px', fontSize: '12px', width: '50%' }}
                 type="number" placeholder="min" value={value.price_min || ''} onChange={set('price_min')} />
          <input className="form-control" style={{ padding: '6px', fontSize: '12px', width: '50%' }}
                 type="number" placeholder="max" value={value.price_max || ''} onChange={set('price_max')} />
        </span>
      </label>
    </div>
  );
}

function DesignDetail({ design, onClose, onEdit, onDelete, onReviewed, canReview }) {
  const editable = EDITABLE_SOURCES.includes(design.source);
  const [history, setHistory] = useState([]);
  const [note, setNote] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const isPending = design.status === 'PENDING';
  // A ref, not just the state above: two clicks in the same tick both read
  // `reviewing` as false, because React has not re-rendered between them yet.
  // That let a fast double-click on Approve write two DesignApproval rows for
  // one decision. The ref is checked synchronously, before either render.
  const inFlight = useRef(false);

  useEffect(() => {
    api.getDesignApprovalHistory(design.id).then(setHistory).catch(() => setHistory([]));
  }, [design.id]);

  const decide = async (decision) => {
    if (inFlight.current) return;   // one click, one call
    inFlight.current = true;
    setReviewing(true);
    try {
      const updated = await api.reviewDesign(design.id, decision, note);
      onReviewed?.(updated);
    } catch (err) {
      window.alert(`Could not record that decision — ${err.message}`);
    } finally {
      inFlight.current = false;
      setReviewing(false);
    }
  };

  const row = (label, content) => content ? (
    <div>
      <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block' }}>{label}</span>
      <span style={{ fontSize: '12.5px', fontWeight: 600 }}>{content}</span>
    </div>
  ) : null;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px',
    }} onClick={onClose}>
      <div className="content-card" style={{ maxWidth: '860px', width: '100%', maxHeight: '90vh', overflowY: 'auto', margin: 0 }}
           onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '20px' }}>{design.title}</h3>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {design.designer_name || 'No designer credited'} · added {formatDate(design.created_at)}
            </span>
          </div>
          <button className="btn-secondary" style={{ padding: '4px 10px' }} onClick={onClose}><X size={14} /></button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(200px, 320px) 1fr', gap: '20px' }}>
          <img src={resolveMediaUrl(design.image_url, CARD_IMAGE_FALLBACK)} alt={design.title}
               style={{ width: '100%', borderRadius: '8px', objectFit: 'cover' }} />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: '12px', alignContent: 'start' }}>
            {row('Garment', design.garment_type)}
            {row('Occasion', design.occasion)}
            {row('Price', design.estimated_price > 0 ? `₹${Number(design.estimated_price).toLocaleString('en-IN')}` : null)}
            {row('Status', design.status)}
            {row('Source', design.source_display)}
            {row('Difficulty', design.difficulty)}
            {row('Stitch time', design.stitch_hours ? `${design.stitch_hours} h` : null)}
            {row('Views', design.view_count)}
            {row('Orders', design.order_count)}
            {Object.entries(design.spec_tags || {}).map(([k, v]) => (
              <div key={k}>
                <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block' }}>
                  {k.replace(/_/g, ' ')}
                </span>
                <span style={{ fontSize: '12.5px', fontWeight: 600 }}>{String(v).replace(/_/g, ' ')}</span>
              </div>
            ))}
          </div>
        </div>

        {design.description && (
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '16px' }}>{design.description}</p>
        )}

        {canReview && isPending && (
          <div style={{ marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>
              Awaiting your review
            </div>
            <textarea className="form-control" rows={2} placeholder="Note for the designer (optional)"
                      value={note} onChange={(e) => setNote(e.target.value)}
                      style={{ fontSize: '12.5px', marginBottom: '10px' }} />
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="btn-primary" style={{ padding: '6px 14px', fontSize: '12px', opacity: reviewing ? 0.6 : 1 }}
                      disabled={reviewing} onClick={() => decide('APPROVED')}>
                <Check size={12} /> Approve
              </button>
              <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: '12px' }}
                      disabled={reviewing} onClick={() => decide('CHANGES_REQUESTED')}>
                Request changes
              </button>
              <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: '12px', color: '#ff4d4d', borderColor: 'rgba(255,77,77,0.2)' }}
                      disabled={reviewing} onClick={() => decide('REJECTED')}>
                Reject
              </button>
            </div>
          </div>
        )}

        {history.length > 0 && (
          <div style={{ marginTop: '16px', borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Review history
            </div>
            {history.map((h) => (
              <div key={h.id} style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                <strong style={{ color: 'var(--text-primary)' }}>{h.decision.replace('_', ' ')}</strong>
                {h.reviewer_name ? ` by ${h.reviewer_name}` : ''} · {formatDate(h.created_at)}
                {h.note && <div style={{ marginTop: '2px' }}>&ldquo;{h.note}&rdquo;</div>}
              </div>
            ))}
          </div>
        )}

        {editable && !isPending && (
          <div style={{ display: 'flex', gap: '8px', marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }}
                    onClick={() => onEdit(design)}><Edit2 size={12} /> Edit</button>
            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px', color: '#ff4d4d', borderColor: 'rgba(255,77,77,0.2)' }}
                    onClick={() => onDelete(design)}><Trash2 size={12} /> Delete</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function DesignLibrary({ onEditDesign, onDeleteDesign, onUploaded, refreshToken, canReview = false }) {
  const [categories, setCategories] = useState([]);
  const [total, setTotal] = useState(0);
  const [openCategory, setOpenCategory] = useState(null);   // null = section list
  const [designs, setDesigns] = useState([]);
  const [designers, setDesigners] = useState([]);
  const [collections, setCollections] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [filters, setFilters] = useState({});
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);

  const PENDING_QUEUE = { key: '__pending__', name: 'Pending Approval' };
  const isPendingQueue = openCategory?.key === PENDING_QUEUE.key;

  const loadPendingCount = useCallback(() => {
    if (!canReview) return;
    api.getDesignLibrary({ status: 'PENDING' })
      .then((rows) => setPendingCount(rows.length))
      .catch(() => setPendingCount(0));
  }, [canReview]);

  const loadCategories = useCallback(async () => {
    try {
      const data = await api.getDesignCategories();
      setCategories(data.categories || []);
      setTotal(data.total || 0);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { loadCategories(); }, [loadCategories, refreshToken]);
  useEffect(() => { loadPendingCount(); }, [loadPendingCount, refreshToken]);

  useEffect(() => {
    api.getDesigners({ active: 'true' }).then(setDesigners).catch(() => setDesigners([]));
    api.getCollections({ active: 'true' }).then(setCollections).catch(() => setCollections([]));
  }, [refreshToken]);

  // Only the open category is fetched, so the landing page never pays for the
  // whole library.
  useEffect(() => {
    if (openCategory === null) return;
    let cancelled = false;
    setLoading(true);
    const query = isPendingQueue
      ? { ...filters, status: 'PENDING', template: undefined }
      : { ...filters, template: openCategory.key || undefined };
    api.getDesignLibrary(query)
      .then((rows) => { if (!cancelled) { setDesigns(rows); setError(null); } })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [openCategory, filters, refreshToken, isPendingQueue]);

  // A design leaving PENDING (approved/rejected) must disappear from the queue
  // immediately, not on the next reload -- otherwise the owner reviews the same
  // design twice.
  const handleReviewed = (updated) => {
    setSelected(updated);
    setDesigns((prev) => (isPendingQueue
      ? prev.filter((d) => d.id !== updated.id)
      : prev.map((d) => (d.id === updated.id ? updated : d))));
    loadPendingCount();
    loadCategories();
  };

  if (error && !openCategory) {
    return (
      <div className="content-card" style={{ color: '#c0392b', fontSize: '13px' }}>
        The design library could not be loaded — {error}
        <button className="btn-secondary" style={{ marginLeft: '10px', padding: '4px 10px', fontSize: '12px' }}
                onClick={loadCategories}>Retry</button>
      </div>
    );
  }

  if (openCategory === null) {
    return (
      <div className="content-card">
        <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Boutique Designs</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 400 }}>
              {total} design{total === 1 ? '' : 's'} in the library
            </span>
            {canReview && pendingCount > 0 && (
              <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px', color: '#fbbf24', borderColor: 'rgba(251,191,36,0.3)' }}
                      onClick={() => { setFilters({}); setOpenCategory(PENDING_QUEUE); }}>
                <Clock size={13} /> {pendingCount} awaiting review
              </button>
            )}
            <button className="btn-primary" style={{ padding: '6px 12px', fontSize: '12px' }}
                    onClick={() => setUploading(true)}>
              <Plus size={13} /> Upload design
            </button>
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px' }}>
          {categories.map((category) => (
            <button
              key={category.key || 'uncategorised'}
              type="button"
              onClick={() => { setFilters({}); setOpenCategory(category); }}
              style={{
                textAlign: 'left', padding: '16px', borderRadius: '8px', cursor: 'pointer',
                border: '1px solid var(--border-color)', background: 'var(--surface-color)',
                opacity: category.count === 0 ? 0.55 : 1,
              }}
            >
              <div style={{ fontSize: '14px', fontWeight: 600 }}>{category.name}</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-color, #d4af37)' }}>
                {category.count}
              </div>
            </button>
          ))}
        </div>

        {uploading && (
          <DesignUpload
            onClose={() => setUploading(false)}
            onUploaded={() => { setUploading(false); loadCategories(); onUploaded?.(); }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="content-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }}
                onClick={() => { setOpenCategory(null); setDesigns([]); }}>
          <ArrowLeft size={13} /> All categories
        </button>
        <h3 style={{ margin: 0, fontSize: '18px' }}>{openCategory.name}</h3>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          {loading ? 'loading…' : `${designs.length} shown`}
        </span>
        <button className="btn-primary" style={{ padding: '6px 12px', fontSize: '12px', marginLeft: 'auto' }}
                onClick={() => setUploading(true)}>
          <Plus size={13} /> Upload design
        </button>
      </div>

      <Filters value={filters} onChange={setFilters} designers={designers} collections={collections} />

      {!loading && designs.length === 0 && (
        <div style={{ fontSize: '13px', color: 'var(--text-secondary)', padding: '24px 0', textAlign: 'center' }}>
          No designs match these filters.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px' }}>
        {designs.map((design) => {
          const status = STATUS_COLOURS[design.status] || STATUS_COLOURS.DRAFT;
          return (
            <div key={design.id}
                 onClick={() => api.getDesignAsset(design.id).then(setSelected).catch(() => setSelected(design))}
                 style={{
                   border: '1px solid var(--border-color)', borderRadius: '10px',
                   overflow: 'hidden', cursor: 'pointer', background: 'var(--surface-color)',
                 }}>
              <div style={{ height: '170px', background: '#222', position: 'relative' }}>
                <img src={resolveMediaUrl(design.image_url, CARD_IMAGE_FALLBACK)} alt={design.title}
                     style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                <span style={{
                  position: 'absolute', top: '10px', right: '10px', padding: '2px 8px',
                  borderRadius: '4px', fontSize: '9px', fontWeight: 700, textTransform: 'uppercase',
                  background: status.bg, color: status.fg,
                }}>{design.status}</span>
              </div>
              <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ fontSize: '14px', fontWeight: 600 }}>{design.title}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  {design.designer_name || 'Unattributed'} · {formatDate(design.created_at)}
                </div>
                <div style={{ display: 'flex', gap: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <Eye size={11} /> {design.view_count}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <ShoppingBag size={11} /> {design.order_count}
                  </span>
                  {design.estimated_price > 0 && (
                    <span style={{ marginLeft: 'auto', fontWeight: 600, color: 'var(--accent-color, #d4af37)' }}>
                      ₹{Number(design.estimated_price).toLocaleString('en-IN')}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {uploading && (
        <DesignUpload
          onClose={() => setUploading(false)}
          onUploaded={() => {
            setUploading(false);
            loadCategories();
            setFilters({ ...filters });   // refetch the open category
            onUploaded?.();
          }}
        />
      )}

      {selected && (
        <DesignDetail
          design={selected}
          onClose={() => setSelected(null)}
          onEdit={(design) => { setSelected(null); onEditDesign?.(design); }}
          onDelete={(design) => { setSelected(null); onDeleteDesign?.(design); }}
          onReviewed={handleReviewed}
          canReview={canReview}
        />
      )}
    </div>
  );
}
