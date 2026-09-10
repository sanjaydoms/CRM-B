import { AddMoreTile, Dropzone, Field, PhotoTile } from '../../components/ui/Atelier';
import { IndianRupee, Layers, Link as LinkIcon, Palette, Trash2, Type } from 'lucide-react';
import { api } from '../../services/api';


const HEX = /^#[0-9a-fA-F]{6}$/;

/** One material: its own details and photos. Placement lives on the group. */
export default function FabricEntry({
  value, onChange, onRemove, canRemove, index, number, onUploading,
}) {
  const set = (patch) => onChange({ ...value, ...patch });
  const swatchId = `fabric-colour-wheel-${index}`;
  const galleryId = `fabric-photo-gallery-${index}`;

  const addPhotos = async (files) => {
    const picked = [...(files || [])];
    if (!picked.length) return;
    onUploading(1);
    try {
      const { image_urls: uploaded } = await api.uploadFabricImages(picked);
      set({
        image_urls: [...(value.image_urls || []), ...uploaded],
        image_url: value.image_url || uploaded[0] || '',
      });
    } catch (err) {
      alert('Could not upload those photos: ' + err.message);
    } finally {
      onUploading(-1);
    }
  };

  const removePhoto = (i) => set({
    image_urls: (value.image_urls || []).filter((_, idx) => idx !== i),
  });

  return (
    <section className="at-form-subsection">
      <header className="at-form-section-head">
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="at-subsection-title">Material {number}</div>
        </div>
        {canRemove && (
          <button
            type="button"
            className="btn-secondary at-btn-sm at-btn-danger"
            onClick={onRemove}
          >
            <Trash2 size={14} /> Remove
          </button>
        )}
      </header>

      <Field label="Fabric Name" required icon={Type}>
        <input
          type="text"
          required
          className="form-control"
          placeholder="e.g. Chanderi Silk"
          value={value.name}
          onChange={(e) => set({ name: e.target.value })}
        />
      </Field>

      <div className="at-form-grid">
        <Field label="Material" required icon={Layers}>
          <input
            type="text"
            required
            className="form-control"
            placeholder="e.g. Silk Blend"
            value={value.material}
            onChange={(e) => set({ material: e.target.value })}
          />
        </Field>
        <Field label="Color" required icon={Palette}>
          <input
            type="text"
            required
            className="form-control"
            placeholder="e.g. Aqua Blue"
            value={value.color}
            onChange={(e) => set({ color: e.target.value })}
          />
        </Field>
      </div>

      <div className="at-field">
        <label className="at-field-label">Colour Code</label>
        <div className="at-field-inline">
          <label className="at-swatch" title="Colour wheel" style={{ position: 'relative', cursor: 'pointer' }}>
            <i style={{ background: HEX.test(value.color_hex) ? value.color_hex : '#c8a97e' }} />
            <input
              id={swatchId}
              type="color"
              aria-label="Colour wheel"
              value={HEX.test(value.color_hex) ? value.color_hex : '#c8a97e'}
              onChange={(e) => set({ color_hex: e.target.value })}
              style={{ position: 'absolute', width: 1, height: 1, opacity: 0, left: 0, bottom: 0 }}
            />
          </label>
          <div className="at-field-control" style={{ width: '160px' }}>
            <input
              type="text"
              className="form-control"
              aria-label="Colour Code"
              placeholder="#c8a97e"
              maxLength={7}
              pattern="#[0-9a-fA-F]{6}"
              title="#1a2b3c"
              value={value.color_hex}
              onChange={(e) => {
                const v = e.target.value.trim();
                set({ color_hex: v && !v.startsWith('#') ? `#${v}` : v });
              }}
              style={{ fontFamily: 'monospace' }}
            />
          </div>
          <button type="button" className="btn-secondary at-btn-sm" style={{ borderStyle: 'dashed' }}
                  onClick={() => document.getElementById(swatchId).click()}>
            <Palette size={14} /> Pick from color wheel
          </button>
        </div>
      </div>

      <Field label="Price per Meter (₹)" required icon={IndianRupee}>
        <input
          type="number"
          required
          min="0"
          step="0.01"
          className="form-control"
          placeholder="e.g. 1250"
          value={value.price_per_meter}
          onChange={(e) => set({ price_per_meter: e.target.value })}
        />
      </Field>

      <Field label="Photos" hint="Add as many photos of this material as you like.">
        <div className="at-stack" style={{ gap: 'var(--space-2)' }}>
          <Dropzone
            compact multiple camera
            title="Drag & drop photos here"
            subtitle="or choose an option"
            chooseLabel="Choose from gallery"
            cameraLabel="Take photo"
            onFiles={addPhotos}
          />
          {(value.image_urls || []).length > 0 && (
            <div className="at-photos" style={{ gap: '6px' }}>
              {value.image_urls.map((src, i) => (
                <PhotoTile key={src} src={src} size={64} onRemove={() => removePhoto(i)} />
              ))}
              <AddMoreTile size={64} onClick={() => document.getElementById(galleryId).click()} />
            </div>
          )}
          <input type="file" id={galleryId} accept="image/*" multiple style={{ display: 'none' }}
                 onChange={(e) => { addPhotos(e.target.files); e.target.value = ''; }} />
        </div>
      </Field>

      <Field label="Image URL" optional icon={LinkIcon}>
        <input
          type="url"
          className="form-control"
          placeholder="e.g. https://images.unsplash.com/photo-..."
          value={value.image_url}
          onChange={(e) => set({ image_url: e.target.value })}
        />
      </Field>

      <label className="at-check-card" htmlFor={`fabricAvailable-${index}`}>
        <input
          type="checkbox"
          id={`fabricAvailable-${index}`}
          checked={value.is_available}
          onChange={(e) => set({ is_available: e.target.checked })}
        />
        <span>
          <span className="at-check-card-title" style={{ display: 'block' }}>Available in Inventory</span>
          <span className="at-check-card-sub" style={{ display: 'block' }}>Make this fabric available for inventory and purchase orders.</span>
        </span>
      </label>
    </section>
  );
}
