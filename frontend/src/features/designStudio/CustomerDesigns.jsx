import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Eraser, ImageOff, PenTool, Pencil, Redo2, Save, Shirt, Trash2, Type, Undo2, Upload, User, X,
} from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';
import { Dropzone, Field, FormModal } from '../../components/ui/Atelier';

/**
 * A customer's own designs, captured in the studio.
 *
 * A customer describes a blouse; the designer either sketches it on paper and
 * photographs the page, or draws it here. Both become the same thing -- a
 * CustomerDesign with one picture -- so the list, the card and the preview
 * never ask which. The form is one form with the picture-taking half swapped:
 * a drop zone for a photograph, a canvas for a drawing.
 *
 * Reads what the wizard already holds -- the boutique's customers, orders and
 * garment templates -- rather than fetching its own copies, and starts on the
 * customer the order is being taken for.
 */

const FALLBACK =
  'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="100%" height="100%" fill="%23eeeae1"/></svg>';

const customerName = (c) => `${c.first_name || ''} ${c.last_name || ''}`.trim() || c.mobile_number || 'Customer';

// ---------------------------------------------------------------------------
// The sketch pad

const PAD_W = 1000;
const PAD_H = 700;
const INKS = ['#1b201e', '#b03a2e', '#1f5fa8', '#107c41', '#986a26'];
const SIZES = [{ key: 'fine', px: 3 }, { key: 'medium', px: 6 }, { key: 'bold', px: 12 }];

function paint(ctx, strokes) {
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, PAD_W, PAD_H);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  strokes.forEach((s) => {
    if (s.points.length === 0) return;
    ctx.strokeStyle = s.erase ? '#ffffff' : s.color;
    ctx.lineWidth = s.erase ? s.size * 3 : s.size;
    ctx.beginPath();
    ctx.moveTo(s.points[0].x, s.points[0].y);
    if (s.points.length === 1) ctx.lineTo(s.points[0].x + 0.1, s.points[0].y);
    s.points.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.stroke();
  });
}

/** Freehand on a fixed 1000x700 surface scaled to the space it has. Strokes
 *  are kept as a list rather than pixels, so undo is a pop, redo is a push
 *  back, and the picture is the same at any screen size. Pointer events, so
 *  a mouse, a finger and a stylus are one code path. */
function SketchPad({ strokes, onStrokes }) {
  const canvasRef = useRef(null);
  const current = useRef(null);
  // The strokes as of the last commit, so two strokes landing before React
  // re-renders (a quick tap-tap on a tablet) both survive: the second reads
  // the first from here rather than from a closure that predates it.
  const committed = useRef(strokes);
  const [color, setColor] = useState(INKS[0]);
  const [size, setSize] = useState(SIZES[1]);
  const [erase, setErase] = useState(false);
  const [redoStack, setRedoStack] = useState([]);

  useEffect(() => {
    committed.current = strokes;
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) paint(ctx, strokes);
  }, [strokes]);

  const commit = (next) => { committed.current = next; onStrokes(next); };

  const at = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width) * PAD_W,
             y: ((e.clientY - rect.top) / rect.height) * PAD_H };
  };

  const down = (e) => {
    e.preventDefault();
    // Capture keeps the stroke on the canvas when a finger drifts off its
    // edge. Not every pointer can be captured (a pen some tablets report
    // oddly, a synthetic event); a refusal must not lose the stroke.
    try { canvasRef.current.setPointerCapture(e.pointerId); } catch { /* draw anyway */ }
    current.current = { color, size: size.px, erase, points: [at(e)] };
    // Drawn live rather than through state on every move: a stroke is many
    // points a second, and re-rendering React for each would stutter.
    paint(canvasRef.current.getContext('2d'), [...committed.current, current.current]);
  };
  const move = (e) => {
    if (!current.current) return;
    e.preventDefault();
    current.current.points.push(at(e));
    paint(canvasRef.current.getContext('2d'), [...committed.current, current.current]);
  };
  const up = () => {
    if (!current.current) return;
    commit([...committed.current, current.current]);
    current.current = null;
    setRedoStack([]);
  };

  const undo = () => {
    const have = committed.current;
    if (!have.length) return;
    setRedoStack((r) => [have[have.length - 1], ...r]);
    commit(have.slice(0, -1));
  };
  const redo = () => {
    if (!redoStack.length) return;
    const [next, ...rest] = redoStack;
    setRedoStack(rest);
    commit([...committed.current, next]);
  };
  const clear = () => { if (committed.current.length) { setRedoStack([]); commit([]); } };

  const tool = (active) => ({
    padding: '5px 9px', fontSize: '12px', fontWeight: 600, cursor: 'pointer', borderRadius: '7px',
    border: active ? '1.5px solid #107c41' : '1px solid var(--border-color)',
    background: active ? 'rgba(16,124,65,0.10)' : 'var(--surface-color)',
    color: active ? '#107c41' : 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: '4px',
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '6px' }}>
        {/* The swatch is a span inside the button rather than the button
            itself: on a phone every button is given a 40px touch height, and
            a 22px circle stretched to it read as an egg. The button keeps the
            finger-sized target; the span stays round. */}
        {INKS.map((ink) => (
          <button key={ink} type="button" title="Ink" aria-label={`Ink ${ink}`} aria-pressed={!erase && color === ink}
                  onClick={() => { setColor(ink); setErase(false); }}
                  style={{ width: '28px', padding: 0, border: 'none', background: 'none', cursor: 'pointer',
                           display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: ink, display: 'block',
                           border: (!erase && color === ink) ? '3px solid #fff' : '2px solid transparent',
                           boxShadow: (!erase && color === ink) ? `0 0 0 2px ${ink}` : 'none' }} />
          </button>
        ))}
        <span style={{ width: '1px', height: '20px', background: 'var(--border-color)', margin: '0 4px' }} />
        {SIZES.map((s) => (
          <button key={s.key} type="button" aria-pressed={size.key === s.key} title={`${s.key} pen`}
                  onClick={() => setSize(s)} style={tool(size.key === s.key)}>
            <span style={{ width: `${s.px + 4}px`, height: `${s.px + 4}px`, borderRadius: '50%', background: 'currentColor' }} />
          </button>
        ))}
        <button type="button" aria-pressed={erase} onClick={() => setErase((v) => !v)} style={tool(erase)}>
          <Eraser size={13} /> Eraser
        </button>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: '6px' }}>
          <button type="button" onClick={undo} disabled={!strokes.length} style={tool(false)} title="Undo">
            <Undo2 size={13} /> Undo
          </button>
          <button type="button" onClick={redo} disabled={!redoStack.length} style={tool(false)} title="Redo">
            <Redo2 size={13} /> Redo
          </button>
          <button type="button" onClick={clear} disabled={!strokes.length} style={tool(false)} title="Clear">
            <Trash2 size={13} /> Clear
          </button>
        </span>
      </div>
      <div style={{ position: 'relative', borderRadius: '10px', overflow: 'hidden',
                    border: '1px solid var(--border-color)', background: '#fff' }}>
        <canvas
          ref={canvasRef} width={PAD_W} height={PAD_H}
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={up}
          style={{ display: 'block', width: '100%', aspectRatio: `${PAD_W} / ${PAD_H}`, touchAction: 'none',
                   cursor: 'crosshair' }}
        />
        {strokes.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        pointerEvents: 'none', color: 'var(--text-muted)', fontSize: '13px', gap: '6px' }}>
            <PenTool size={15} /> Draw the design here
          </div>
        )}
      </div>
    </div>
  );
}

/** The drawing as a PNG file, the way an uploaded photograph arrives. */
function strokesToFile(strokes) {
  const canvas = document.createElement('canvas');
  canvas.width = PAD_W;
  canvas.height = PAD_H;
  paint(canvas.getContext('2d'), strokes);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) { reject(new Error('The drawing could not be saved as an image.')); return; }
      resolve(new File([blob], `sketch-${Date.now()}.png`, { type: 'image/png' }));
    }, 'image/png');
  });
}

// ---------------------------------------------------------------------------
// The form: one form, two ways of taking the picture

function CustomerDesignForm({ mode, customers, orders, garmentTemplates, initialCustomerId, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: '', customer: initialCustomerId || '', order: '', template: '', notes: '',
  });
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [strokes, setStrokes] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const inFlight = useRef(false);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const customerOrders = useMemo(
    () => (orders || []).filter((o) => form.customer && String(o.customer) === String(form.customer)),
    [orders, form.customer]);

  const pick = ([chosen]) => {
    if (!chosen) return;
    if (!chosen.type?.startsWith('image/')) { setError('Please choose an image file.'); return; }
    setError(null);
    setFile(chosen);
    setPreview(URL.createObjectURL(chosen));
  };

  const submit = async () => {
    if (inFlight.current) return;
    if (!form.title.trim()) { setError('The design needs a name.'); return; }
    if (!form.customer) { setError('Choose the customer this design is for.'); return; }
    if (mode === 'upload' && !file) { setError('Add a photograph of the design.'); return; }
    if (mode === 'draw' && strokes.length === 0) { setError('Draw the design before saving.'); return; }
    inFlight.current = true;
    setSaving(true);
    setError(null);
    try {
      const image = mode === 'draw' ? await strokesToFile(strokes) : file;
      const created = await api.createCustomerDesign({
        title: form.title.trim(), customer: form.customer, order: form.order,
        template: form.template, notes: form.notes, source: mode === 'draw' ? 'drawn' : 'uploaded',
      }, image);
      onSaved?.(created);
    } catch (err) {
      setError(err.message || 'The design could not be saved.');
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  const drawing = mode === 'draw';
  return (
    <FormModal
      icon={drawing ? PenTool : Upload} tone="green" width={drawing ? '860px' : '640px'}
      title={drawing ? 'Draw Customer Design' : 'Upload Customer Design'}
      subtitle={drawing ? 'Sketch what the customer described, then save it to their designs.'
                        : 'A photograph of the paper sketch, saved to the customer\'s designs.'}
      onClose={onClose}
      footer={(
        <>
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={saving}>
            <Save size={16} /> {saving ? 'Saving…' : 'Save Design'}
          </button>
        </>
      )}
    >
      {/* min(100%, 240px): two columns where there is room, one on a phone,
          and never wider than the modal body. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: 'var(--space-4)' }}>
        <Field label="Design name" required icon={Type}>
          <input className="form-control" value={form.title} onChange={set('title')} autoFocus
                 placeholder="e.g. Bridal Blouse, Customer Neck Design" />
        </Field>
        <Field label="Customer" required icon={User}>
          <select className="form-control" value={form.customer}
                  onChange={(e) => setForm((f) => ({ ...f, customer: e.target.value, order: '' }))}>
            <option value="">Choose a customer</option>
            {(customers || []).map((c) => <option key={c.id} value={c.id}>{customerName(c)}</option>)}
          </select>
        </Field>
        <Field label="Garment" optional icon={Shirt}>
          <select className="form-control" value={form.template} onChange={set('template')}>
            <option value="">Not set</option>
            {(garmentTemplates || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </Field>
        <Field label="Order" optional icon={Shirt}
               hint={form.customer && customerOrders.length === 0 ? 'This customer has no orders yet.' : undefined}>
          <select className="form-control" value={form.order} onChange={set('order')} disabled={!customerOrders.length}>
            <option value="">Not attached to an order</option>
            {customerOrders.map((o) => (
              <option key={o.id} value={o.id}>
                {o.order_reference || o.order_number || o.order_id}{o.garment_label ? ` · ${o.garment_label}` : ''}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {drawing ? (
        <SketchPad strokes={strokes} onStrokes={setStrokes} />
      ) : file ? (
        <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ width: '220px', maxWidth: '100%', aspectRatio: '4 / 5', borderRadius: '10px', overflow: 'hidden',
                        border: '1px solid var(--border-color)', background: 'var(--surface-inset)' }}>
            <img src={preview} alt="Design preview"
                 style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary)' }}>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)', wordBreak: 'break-all' }}>{file.name}</span>
            <span>{Math.max(1, Math.round(file.size / 1024))} KB</span>
            <button type="button" className="btn-secondary at-btn-sm" style={{ alignSelf: 'flex-start' }}
                    onClick={() => { setFile(null); setPreview(''); }}>
              <X size={13} /> Choose another
            </button>
          </div>
        </div>
      ) : (
        <Dropzone onFiles={pick} camera title="Drag & drop the sketch here"
                  chooseLabel="Choose photo" cameraLabel="Take photo"
                  hint="A clear photograph of the paper drawing. JPG, PNG or any image." />
      )}

      <Field label="Notes" optional>
        <textarea className="form-control" rows={2} value={form.notes} onChange={set('notes')}
                  placeholder='e.g. "Deep back neck with embroidery on sleeves."' />
      </Field>

      {error && (
        <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--danger-color)', background: 'var(--danger-bg)',
                                   border: '1px solid var(--danger-color)', borderRadius: 'var(--radius-md)', padding: '10px 12px' }}>
          {error}
        </div>
      )}
    </FormModal>
  );
}

// ---------------------------------------------------------------------------
// The preview

function CustomerDesignView({ design, onClose }) {
  const rows = [
    ['Design', design.title], ['Customer', design.customer_name],
    ['Garment', design.garment_type || '—'], ['Order', design.order_reference || '—'],
    ['Source', design.source_display || design.source],
    ['Captured', design.created_at ? new Date(design.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'],
  ];
  return (
    <FormModal icon={design.source === 'drawn' ? PenTool : Upload} tone="green" width="820px"
               title={design.title} subtitle="Customer design" onClose={onClose}
               footer={<button type="button" className="btn-secondary" onClick={onClose}>Close</button>}>
      <div style={{ borderRadius: '10px', overflow: 'hidden', border: '1px solid var(--border-color)',
                    background: 'var(--surface-inset)', maxHeight: '60vh', display: 'flex', justifyContent: 'center' }}>
        <img src={resolveMediaUrl(design.image_url, FALLBACK)} alt={design.title}
             style={{ maxWidth: '100%', maxHeight: '60vh', objectFit: 'contain', display: 'block' }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px 18px' }}>
        {rows.map(([label, value]) => (
          <div key={label}>
            <div style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                          color: 'var(--text-secondary)' }}>{label}</div>
            <div style={{ fontSize: '13.5px', color: 'var(--text-primary)', fontWeight: 500 }}>{value}</div>
          </div>
        ))}
      </div>
      {design.notes && (
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                        color: 'var(--text-secondary)', marginBottom: '4px' }}>Notes</div>
          <div style={{ fontSize: '13.5px', color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>{design.notes}</div>
        </div>
      )}
    </FormModal>
  );
}

// ---------------------------------------------------------------------------
// The list

export default function CustomerDesigns({ customerId, customers = [], orders = [], garmentTemplates = [] }) {
  const [designs, setDesigns] = useState(null);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [mode, setMode] = useState(null);       // 'upload' | 'draw' | null
  const [viewing, setViewing] = useState(null);
  const loading = !designs && !error;

  useEffect(() => {
    let cancelled = false;
    // The order's customer where there is one, every customer otherwise.
    api.getCustomerDesigns(customerId ? { customer: customerId } : {})
      .then((rows) => { if (!cancelled) setDesigns(rows); })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [customerId, reloadToken]);

  const forName = useMemo(() => {
    const c = customers.find((x) => String(x.id) === String(customerId));
    return c ? customerName(c) : '';
  }, [customers, customerId]);

  const saved = (created) => {
    setMode(null);
    // Straight into the list, newest first, rather than waiting on a refetch.
    setDesigns((prev) => [created, ...(prev || [])]);
  };

  const actions = (
    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
      <button type="button" className="btn-secondary" style={{ padding: '7px 14px', fontSize: '12.5px' }}
              onClick={() => setMode('upload')}>
        <Upload size={14} /> Upload Design
      </button>
      <button type="button" className="btn-primary" style={{ padding: '7px 14px', fontSize: '12.5px' }}
              onClick={() => setMode('draw')}>
        <Pencil size={14} /> Draw Design
      </button>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 'var(--text-md)', fontWeight: 600, color: 'var(--text-primary)' }}>Customer Designs</div>
          <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
            {forName ? `Designs captured for ${forName}` : 'Designs customers described, captured by the studio'}
            {designs?.length ? ` · ${designs.length}` : ''}
          </div>
        </div>
        {!loading && !error && designs.length > 0 && actions}
      </div>

      {loading && (
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '18px 0' }}>Loading customer designs…</div>
      )}

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', fontSize: '13px',
                      color: 'var(--danger-color)', background: 'var(--danger-bg)', border: '1px solid var(--danger-color)',
                      borderRadius: 'var(--radius-md)', padding: '10px 12px' }}>
          <span>Customer designs could not be loaded.</span>
          <button type="button" className="btn-secondary at-btn-sm"
                  onClick={() => { setDesigns(null); setError(null); setReloadToken((t) => t + 1); }}>Retry</button>
        </div>
      )}

      {!loading && !error && designs.length === 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', textAlign: 'center',
                      padding: '34px 16px', borderRadius: '12px', border: '1px dashed var(--border-strong)',
                      color: 'var(--text-secondary)' }}>
          <ImageOff size={24} />
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>No customer designs yet</div>
          <div style={{ fontSize: '12.5px', maxWidth: '380px' }}>
            Upload a photo of a customer's sketch, or draw the design they described on the canvas.
          </div>
          {actions}
        </div>
      )}

      {!loading && !error && designs.length > 0 && (
        <div style={{ display: 'grid', gap: '14px', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))' }}>
          {designs.map((d) => (
            <div key={d.id} style={{ background: 'var(--surface-color)', borderRadius: '10px', overflow: 'hidden',
                                     border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column' }}>
              <button type="button" onClick={() => setViewing(d)} title="View design"
                      style={{ padding: 0, margin: 0, border: 'none', background: 'var(--surface-inset)', cursor: 'pointer',
                               display: 'block', width: '100%', aspectRatio: '4 / 3' }}>
                <img src={resolveMediaUrl(d.image_url, FALLBACK)} alt={d.title} loading="lazy"
                     style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
              </button>
              <div style={{ padding: '9px 10px 10px', display: 'flex', flexDirection: 'column', gap: '3px', flex: 1 }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden',
                              textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</div>
                <div style={{ fontSize: '11.5px', color: 'var(--text-secondary)', overflow: 'hidden',
                              textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {d.customer_name || 'Customer'}{d.garment_type ? ` · ${d.garment_type}` : ''}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px', marginTop: '6px' }}>
                  <span className={`ui-badge ui-badge--${d.source === 'drawn' ? 'info' : 'neutral'}`}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                    {d.source === 'drawn' ? <PenTool size={11} /> : <Upload size={11} />}
                    {d.source_display || d.source}
                  </span>
                  <button type="button" onClick={() => setViewing(d)}
                          style={{ fontSize: '11.5px', fontWeight: 600, color: '#107c41', background: 'none',
                                   border: 'none', cursor: 'pointer', padding: 0 }}>
                    View
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {mode && (
        <CustomerDesignForm
          mode={mode} customers={customers} orders={orders} garmentTemplates={garmentTemplates}
          initialCustomerId={customerId} onClose={() => setMode(null)} onSaved={saved}
        />
      )}
      {viewing && <CustomerDesignView design={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}
