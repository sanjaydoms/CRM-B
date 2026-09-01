import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Upload, X } from 'lucide-react';

import { api } from '../../services/api';
import TemplateForm from '../catalog/TemplateForm';
import { getSection, pruneHidden } from '../../services/templates';

/**
 * Uploading a design into the library.
 *
 * The style tags are not a hand-written list of dropdowns. Picking a garment
 * loads its template and renders that garment's own style section, so a design
 * is tagged with exactly the values an order for that garment can hold. A
 * hardcoded "Half / Full" sleeve list here would tag designs with words the
 * order form never produces, and the two sides would stop matching.
 */

export default function DesignUpload({ onClose, onUploaded }) {
  const [templates, setTemplates] = useState([]);
  const [designers, setDesigners] = useState([]);
  const [collections, setCollections] = useState([]);
  const [template, setTemplate] = useState(null);       // the full definition
  const [specTags, setSpecTags] = useState({});
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [newCollection, setNewCollection] = useState('');
  const [addingCollection, setAddingCollection] = useState(false);
  const inFlight = useRef(false);

  const [form, setForm] = useState({
    title: '', template_key: '', designer_ref: '', collection: '',
    description: '', estimated_price: '', difficulty: '', stitch_hours: '',
    video_url: '', source_url: '',
  });

  useEffect(() => {
    api.getGarmentTemplates().then(d => setTemplates(d.results || d)).catch(() => setTemplates([]));
    api.getDesigners({ active: 'true' }).then(setDesigners).catch(() => setDesigners([]));
  }, []);

  // Collections belong to a designer, so the list follows the chosen one.
  useEffect(() => {
    if (!form.designer_ref) { setCollections([]); return; }
    api.getCollections({ designer: form.designer_ref, active: 'true' })
      .then(setCollections).catch(() => setCollections([]));
  }, [form.designer_ref]);

  useEffect(() => {
    if (!form.template_key) { setTemplate(null); setSpecTags({}); return; }
    let cancelled = false;
    api.getGarmentTemplate(form.template_key)
      .then(t => { if (!cancelled) { setTemplate(t); setSpecTags({}); } })
      .catch(() => { if (!cancelled) setTemplate(null); });
    return () => { cancelled = true; };
  }, [form.template_key]);

  // Object URLs are revoked on unmount only. With append-only previews a
  // per-change cleanup would revoke URLs that are still on screen; the ref
  // keeps the latest list where the unmount closure can reach it.
  const previewsRef = useRef(previews);
  previewsRef.current = previews;
  useEffect(() => () => previewsRef.current.forEach(URL.revokeObjectURL), []);

  const styleSection = useMemo(
    () => (template ? getSection(template, 'style') : null), [template]);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const pickFiles = (e) => {
    // Append, never replace: a camera shot arriving after gallery picks used
    // to silently discard everything already chosen. Old previews stay live
    // (their object URLs are still on screen), so nothing is revoked here.
    const chosen = [...e.target.files];
    setFiles((prev) => [...prev, ...chosen]);
    setPreviews((prev) => [...prev, ...chosen.map(f => URL.createObjectURL(f))]);
    // Reset so retaking the identical photo fires change again.
    e.target.value = '';
  };

  const addCollection = async () => {
    if (addingCollection) return;
    if (!newCollection.trim() || !form.designer_ref) return;
    setAddingCollection(true);
    try {
      const created = await api.createCollection({
        designer: form.designer_ref, name: newCollection.trim(),
      });
      setCollections([...collections, created]);
      setForm({ ...form, collection: created.id });
      setNewCollection('');
    } catch (err) {
      setError(`Could not create the collection — ${err.message}`);
    } finally {
      setAddingCollection(false);
    }
  };

  const submit = async () => {
    if (inFlight.current) return;          // one click, one upload
    if (!form.title.trim()) { setError('The design needs a name.'); return; }
    if (!files.length && !form.source_url) {
      setError('Add at least one photograph, or a reference URL.');
      return;
    }
    inFlight.current = true;
    setSaving(true);
    setError(null);
    try {
      const created = await api.uploadDesign({
        title: form.title.trim(),
        template: template ? template.id : '',
        garment_type: template ? template.name : '',
        designer_ref: form.designer_ref,
        collection: form.collection,
        description: form.description,
        estimated_price: form.estimated_price || 0,
        difficulty: form.difficulty,
        stitch_hours: form.stitch_hours,
        video_url: form.video_url,
        source_url: form.source_url,
        image_url: files.length ? '' : form.source_url,
        spec_tags: specTags,
      }, files);
      onUploaded?.(created);
      onClose?.();
    } catch (err) {
      setError(err.message);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  const field = (label, node) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
      {label}
      {node}
    </label>
  );

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px',
    }} onClick={onClose}>
      <div className="content-card" style={{ maxWidth: '820px', width: '100%', maxHeight: '92vh', overflowY: 'auto', margin: 0 }}
           onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '19px' }}>Upload a design</h3>
          <button className="btn-secondary" style={{ padding: '4px 10px' }} onClick={onClose}><X size={14} /></button>
        </div>

        <div className="drag-drop-zone" onClick={(e) => { if (e.target.tagName === 'INPUT') return; document.getElementById('design-upload-input').click(); }}
             style={{ marginBottom: '16px' }}>
          <div className="drag-drop-icon"><Upload size={22} /></div>
          <div className="drag-drop-text">
            {files.length ? `${files.length} photograph${files.length === 1 ? '' : 's'} selected` : 'Choose photographs from gallery'}
          </div>
          <div className="drag-drop-subtext">The first becomes the cover; the rest form the gallery.</div>
          <button
            type="button"
            className="btn-secondary"
            style={{ marginTop: '8px', fontSize: '12px', padding: '6px 12px' }}
            onClick={(e) => { e.stopPropagation(); document.getElementById('design-upload-input-camera').click(); }}
          >
            📷 Take photo
          </button>
          <input id="design-upload-input" type="file" accept="image/*" multiple
                 style={{ display: 'none' }} onChange={pickFiles} />
          <input id="design-upload-input-camera" type="file" accept="image/*" capture="environment"
                 style={{ display: 'none' }} onChange={pickFiles} />
        </div>

        {previews.length > 0 && (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
            {previews.map((src, i) => (
              <img key={src} src={src} alt={`upload ${i + 1}`}
                   style={{ width: '72px', height: '72px', objectFit: 'cover', borderRadius: '6px',
                            border: i === 0 ? '2px solid var(--accent-text, #b07c40)' : '1px solid var(--border-color)' }} />
            ))}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
          {field('Design name *', (
            <input className="form-control" style={{ padding: '7px', fontSize: '13px' }}
                   value={form.title} onChange={set('title')} placeholder="e.g. Hand-embroidered bridal lehenga" />
          ))}
          {field('Garment', (
            <select className="form-control" style={{ padding: '7px', fontSize: '13px' }}
                    value={form.template_key} onChange={set('template_key')}>
              <option value="">Uncategorised</option>
              {templates.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
            </select>
          ))}
          {field('Designer', (
            <select className="form-control" style={{ padding: '7px', fontSize: '13px' }}
                    value={form.designer_ref} onChange={set('designer_ref')}>
              <option value="">Unattributed</option>
              {designers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          ))}
          {field('Collection', (
            <select className="form-control" style={{ padding: '7px', fontSize: '13px' }}
                    value={form.collection} onChange={set('collection')}
                    disabled={!form.designer_ref}>
              <option value="">{form.designer_ref ? 'None' : 'Pick a designer first'}</option>
              {collections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          ))}
          {field('Price', (
            <input className="form-control" style={{ padding: '7px', fontSize: '13px' }} type="number"
                   value={form.estimated_price} onChange={set('estimated_price')} placeholder="0" />
          ))}
          {field('Difficulty', (
            <select className="form-control" style={{ padding: '7px', fontSize: '13px' }}
                    value={form.difficulty} onChange={set('difficulty')}>
              <option value="">Not set</option>
              <option value="SIMPLE">Simple</option>
              <option value="MODERATE">Moderate</option>
              <option value="COMPLEX">Complex</option>
            </select>
          ))}
          {field('Stitch time (hours)', (
            <input className="form-control" style={{ padding: '7px', fontSize: '13px' }} type="number" step="0.5"
                   value={form.stitch_hours} onChange={set('stitch_hours')} placeholder="e.g. 18" />
          ))}
          {field('Reference URL', (
            <input className="form-control" style={{ padding: '7px', fontSize: '13px' }}
                   value={form.source_url} onChange={set('source_url')} placeholder="Pinterest / Google link" />
          ))}
          {field('Video', (
            <input className="form-control" style={{ padding: '7px', fontSize: '13px' }}
                   value={form.video_url} onChange={set('video_url')} placeholder="Optional video URL" />
          ))}
        </div>

        {form.designer_ref && (
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '10px' }}>
            <input className="form-control" style={{ padding: '6px', fontSize: '12px', maxWidth: '220px' }}
                   value={newCollection} onChange={(e) => setNewCollection(e.target.value)}
                   placeholder="New collection name" />
            <button type="button" className="btn-secondary" style={{ padding: '5px 10px', fontSize: '12px' }}
                    onClick={addCollection} disabled={!newCollection.trim() || addingCollection}>
              <Plus size={12} /> {addingCollection ? 'Adding…' : 'Add collection'}
            </button>
          </div>
        )}

        {field('Description', (
          <textarea className="form-control" rows={2} style={{ padding: '7px', fontSize: '13px', marginTop: '12px' }}
                    value={form.description} onChange={set('description')} />
        ))}

        {/* The garment's own style options, straight from its template. */}
        {styleSection && (
          <div style={{ marginTop: '18px' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em',
                          color: 'var(--text-secondary)', marginBottom: '10px' }}>
              {template.name} style tags
            </div>
            <TemplateForm template={template} section="style" values={specTags}
                          onChange={(values) => setSpecTags(pruneHidden(template, values))} />
          </div>
        )}

        {error && (
          <div style={{ marginTop: '14px', fontSize: '12.5px', color: '#c0392b' }}>{error}</div>
        )}

        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '20px',
                      borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={saving}
                  style={{ opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Uploading…' : 'Add to library'}
          </button>
        </div>
      </div>
    </div>
  );
}
