import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3, Camera, Clock, FileText, Image as ImageIcon, IndianRupee, Layers, Link as LinkIcon,
  PlayCircle, Plus, Save, Shirt, Sparkles, Type, User,
} from 'lucide-react';

import { api } from '../../services/api';
import TemplateForm from '../catalog/TemplateForm';
import DesignCataloguePicker from './DesignCataloguePicker';
import { getSection, pruneHidden } from '../../services/templates';
import { AddMoreTile, Dropzone, Field, FormModal, FormSection, InfoNote, PhotoTile } from '../../components/ui/Atelier';

/**
 * Uploading a design into the library.
 *
 * The style tags are not a hand-written list of dropdowns. Picking a garment
 * loads its template and renders that garment's own style section, so a design
 * is tagged with exactly the values an order for that garment can hold. A
 * hardcoded "Half / Full" sleeve list here would tag designs with words the
 * order form never produces, and the two sides would stop matching.
 */

/** @param initialGarmentKey  The garment the library was open on, so the
 *                             form starts there rather than at Uncategorised.
 *  @param initialCatalogue    {category, subcategory, option} the owner was
 *                             looking at, so "upload here" is one click. */
export default function DesignUpload({ onClose, onUploaded, initialGarmentKey = '', initialCatalogue = {} }) {
  const [templates, setTemplates] = useState([]);
  const [designers, setDesigners] = useState([]);
  const [collections, setCollections] = useState([]);
  const [template, setTemplate] = useState(null);       // the full definition
  const [specTags, setSpecTags] = useState({});
  // { partKey: File[] } and { partKey: objectURL[] }. A design is not one
  // photograph: a saree has a pallu, a border and a body, and the boutique
  // shows a customer the part they asked about. The keys come from the chosen
  // garment's template, so the vocabulary is the catalogue's, not this form's.
  const [partFiles, setPartFiles] = useState({});
  const [partPreviews, setPartPreviews] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [newCollection, setNewCollection] = useState('');
  // Which part of the garment the next photographs are filed under.
  const [selectedPart, setSelectedPart] = useState('overall');
  const fileRef = useRef(null);
  const camRef = useRef(null);
  const [addingCollection, setAddingCollection] = useState(false);
  const inFlight = useRef(false);

  // Where in the garment's design catalogue this design is filed. Cleared
  // with the garment, because a saree's catalogue says nothing about a kurti.
  const [catalogue, setCatalogue] = useState(initialCatalogue || {});
  // The position to send: set by the picker only once the path is complete.
  const [cataloguePayload, setCataloguePayload] = useState(null);
  const [form, setForm] = useState({
    title: '', template_key: initialGarmentKey || '', designer_ref: '', collection: '',
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

  // Object URLs are revoked on unmount; without that every re-pick leaks one.
  useEffect(() => () => Object.values(partPreviews).flat().forEach(URL.revokeObjectURL),
            [partPreviews]);

  const styleSection = useMemo(
    () => (template ? getSection(template, 'style') : null), [template]);

  // A design uploaded without a garment still has to go somewhere, so every
  // garment has an implicit 'overall'. Older templates carry no design_parts
  // at all and fall back to it alone, which is the behaviour this form had
  // before parts existed.
  const designParts = useMemo(() => {
    const defined = template?.design_parts;
    return defined?.length ? defined : [{ key: 'overall', label: 'Overall Design' }];
  }, [template]);

  const totalFiles = useMemo(
    () => Object.values(partFiles).reduce((n, list) => n + list.length, 0), [partFiles]);

  // Changing garment changes the vocabulary, so photographs filed under the old
  // garment's parts would keep keys the new one does not have. Everything
  // already picked collapses into 'overall' -- the one part every garment has
  // -- rather than being silently dropped. Done in the change handler rather
  // than an effect: the boutique made the change, so this is a consequence of
  // an event, not state to be synchronised.
  const collapseToOverall = (map) => {
    const all = Object.values(map).flat();
    return all.length ? { overall: all } : {};
  };

  const changeGarment = (e) => {
    setForm({ ...form, template_key: e.target.value });
    setCatalogue({});
    setCataloguePayload(null);
    setPartFiles(collapseToOverall);
    setPartPreviews(collapseToOverall);
  };

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const pickFiles = (partKey) => (e) => {
    const chosen = [...e.target.files];
    if (!chosen.length) return;
    setPartFiles(prev => ({ ...prev, [partKey]: [...(prev[partKey] || []), ...chosen] }));
    setPartPreviews(prev => ({
      ...prev,
      [partKey]: [...(prev[partKey] || []), ...chosen.map(f => URL.createObjectURL(f))],
    }));
    e.target.value = '';   // so re-picking the same file fires change again
  };

  const removeFile = (partKey, index) => {
    setPartPreviews((prev) => {
      const list = prev[partKey] || [];
      URL.revokeObjectURL(list[index]);
      return { ...prev, [partKey]: list.filter((_, i) => i !== index) };
    });
    setPartFiles(prev => ({
      ...prev, [partKey]: (prev[partKey] || []).filter((_, i) => i !== index),
    }));
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
    if (!totalFiles && !form.source_url) {
      setError('Add at least one photograph, or a reference URL.');
      return;
    }
    // Flattened in the order the parts are displayed, so the cover photograph
    // is the first one of the first part the boutique filled in -- the overall
    // shot, for any garment that lists it first. `flatParts` runs alongside as
    // a parallel list; multipart has no nesting, and the server reads the two
    // together.
    const flatFiles = [];
    const flatParts = [];
    designParts.forEach(({ key }) => {
      (partFiles[key] || []).forEach((file) => { flatFiles.push(file); flatParts.push(key); });
    });

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
        image_url: totalFiles ? '' : form.source_url,
        spec_tags: specTags,
        catalogue: cataloguePayload || undefined,
      }, flatFiles, flatParts);
      onUploaded?.(created);
      onClose?.();
    } catch (err) {
      setError(err.message);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  // The chosen part, or the first one when the garment changed underneath it.
  const activePart = designParts.some((p) => p.key === selectedPart) ? selectedPart : designParts[0].key;
  // Every photograph in display order: the first is the cover.
  const shots = designParts.flatMap(({ key, label }) =>
    (partPreviews[key] || []).map((src, i) => ({ key, label, src, i })));

  const select = (key, options, placeholder) => (
    <select className="form-control" value={form[key] || ''} onChange={set(key)}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );

  return (
    <FormModal
      icon={ImageIcon} tone="green" width="1100px" zIndex={1000}
      title="Upload a Design"
      subtitle="Add design details, photos and references to your library."
      onClose={onClose}
      footer={(
        <>
          <InfoNote tone="amber" style={{ marginRight: 'auto', padding: '10px 14px', flex: '1 1 320px' }}>
            <strong>Tip:</strong> Clear photos and detailed information help you and your team reuse and manage designs better.
          </InfoNote>
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={saving}
                  style={{ opacity: saving ? 0.6 : 1 }}>
            <Save size={16} /> {saving ? 'Uploading…' : 'Add to library'}
          </button>
        </>
      )}
    >
      {/* Photographs are filed by part of the garment -- a saree has a pallu,
          a border and a body -- so the boutique can show a customer the part
          they asked about. The vocabulary is the chosen garment's own. */}
      <FormSection
        icon={ImageIcon} tone="green" title="Design Photographs"
        subtitle={template
          ? `${totalFiles} across ${designParts.length} part${designParts.length === 1 ? '' : 's'} of the ${template.name.toLowerCase()}.`
          : 'Pick a garment below to file photographs by part.'}
        aside={(
          <>
            <Field label="Selected Part" style={{ minWidth: '200px' }}>
              <select className="form-control" value={activePart} onChange={(e) => setSelectedPart(e.target.value)}>
                {designParts.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
              </select>
            </Field>
            <button type="button" className="btn-secondary" style={{ alignSelf: 'flex-end' }} onClick={() => camRef.current?.click()}>
              <Camera size={16} /> Take Photo
            </button>
            <button type="button" className="btn-primary" style={{ alignSelf: 'flex-end' }} onClick={() => fileRef.current?.click()}>
              <Plus size={16} /> Add Photos
            </button>
            <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={pickFiles(activePart)} />
            <input ref={camRef} type="file" accept="image/*" capture="environment" hidden onChange={pickFiles(activePart)} />
          </>
        )}
      >
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'stretch' }}>
          <div style={{ flex: '1 1 220px', maxWidth: '320px', display: 'flex' }}>
            <div style={{ flex: 1 }}>
              <Dropzone
                compact multiple
                title="Drag & drop photos here" subtitle="or click to browse" chooseLabel="Choose Photos"
                onFiles={(files) => pickFiles(activePart)({ target: { files, value: '' } })}
              />
            </div>
          </div>
          {shots.map((shot, idx) => (
            <PhotoTile
              key={shot.src} src={shot.src} alt={`${shot.label} ${shot.i + 1}`} size={110}
              label={idx === 0 ? 'Cover' : (designParts.length > 1 ? shot.label : undefined)}
              onRemove={() => removeFile(shot.key, shot.i)}
            />
          ))}
          <AddMoreTile onClick={() => fileRef.current?.click()} hint="JPG, PNG (Max 5MB each)" size={110} />
        </div>
      </FormSection>

      <FormSection icon={FileText} tone="green" title="Design Details" subtitle="Tell us more about this design.">
        <div className="at-form-grid at-form-grid--3">
          <Field label="Design Name" required icon={Type}>
            <input className="form-control" value={form.title} onChange={set('title')}
                   placeholder="e.g. Hand-embroidered bridal lehenga" />
          </Field>
          <Field label="Garment" icon={Shirt}>
            <select className="form-control" value={form.template_key} onChange={changeGarment}>
              <option value="">Uncategorised</option>
              {templates.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
            </select>
          </Field>
          <DesignCataloguePicker
            garmentKey={form.template_key}
            value={catalogue}
            onChange={(value, payload) => { setCatalogue(value); setCataloguePayload(payload); }}
          />
          <Field label="Designer" icon={User}>
            {select('designer_ref', designers.map(d => [d.id, d.name]), 'Unattributed')}
          </Field>
          <Field label="Collection" icon={Layers}>
            <select className="form-control" value={form.collection} onChange={set('collection')}
                    disabled={!form.designer_ref}>
              <option value="">{form.designer_ref ? 'None' : 'Pick a designer first'}</option>
              {collections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Price (₹)" icon={IndianRupee}>
            <input className="form-control" type="number" value={form.estimated_price}
                   onChange={set('estimated_price')} placeholder="0" />
          </Field>
          <Field label="Difficulty" icon={BarChart3}>
            {select('difficulty', [['SIMPLE', 'Simple'], ['MODERATE', 'Moderate'], ['COMPLEX', 'Complex']], 'Not set')}
          </Field>
          <Field label="Stitch Time (hours)" icon={Clock}>
            <input className="form-control" type="number" step="0.5" value={form.stitch_hours}
                   onChange={set('stitch_hours')} placeholder="e.g. 18" />
          </Field>
          <Field label="Reference URL" icon={LinkIcon}>
            <input className="form-control" value={form.source_url} onChange={set('source_url')}
                   placeholder="Pinterest / Google link" />
          </Field>
          <Field label="Video" icon={PlayCircle}>
            <input className="form-control" value={form.video_url} onChange={set('video_url')}
                   placeholder="Optional video URL" />
          </Field>
        </div>

        {form.designer_ref && (
          <div className="at-field-inline">
            <div className="at-field-control" style={{ maxWidth: '260px', flex: '1 1 200px' }}>
              <input className="form-control" value={newCollection} onChange={(e) => setNewCollection(e.target.value)}
                     placeholder="New collection name" />
            </div>
            <button type="button" className="btn-secondary at-btn-sm"
                    onClick={addCollection} disabled={!newCollection.trim() || addingCollection}>
              <Plus size={12} /> {addingCollection ? 'Adding…' : 'Add collection'}
            </button>
          </div>
        )}
      </FormSection>

      <FormSection icon={FileText} tone="green" title="Description"
                   subtitle="Add details about the design, fabric, work, or any other notes.">
        <div className="at-field-control">
          <textarea className="form-control" rows={3} value={form.description} onChange={set('description')}
                    placeholder="e.g. Hand-embroidered with gold thread, georgette base, traditional motif…" />
        </div>
        <div className="at-field-counter">{form.description.length} characters</div>
      </FormSection>

      {/* The garment's own style options, straight from its template. */}
      {styleSection && (
        <FormSection icon={Sparkles} tone="amber" title={`${template.name} style tags`}
                     subtitle="Tagged with exactly the values an order for this garment can hold.">
          <TemplateForm template={template} section="style" values={specTags}
                        onChange={(values) => setSpecTags(pruneHidden(template, values))} />
        </FormSection>
      )}

      {error && (
        <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--danger-color)', background: 'var(--danger-bg)',
                                   border: '1px solid var(--danger-color)', borderRadius: 'var(--radius-md)', padding: '10px 12px' }}>
          {error}
        </div>
      )}
    </FormModal>
  );
}
